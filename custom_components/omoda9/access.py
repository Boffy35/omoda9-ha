"""Account-level state shared by every vehicle on one login (the `Access` aggregate).

Why this module exists. `docs/design/domain-model.md` says `Access` 1 -- 1..* `Vehicle`:
the login, its tokens and the control-PIN lockout counter belong to the ACCOUNT, and a
vehicle is reachable only through it. Until now the code made one of everything per config
entry, which is per VIN. With one car that is the same thing; with two cars on one account
it is not, and four things break:

1. **Tokens.** Chery rotates the refresh_token on every refresh. Two per-VIN copies of the
   same account's token invalidate each other: whichever car refreshes second presents a
   refresh_token the server has already retired, and the user is asked for a new OTP over
   and over. Here: one token file per account, one lock serialising its refresh.

2. **The MQTT push channel.** The broker identifies the client as `app_<channel>_<tUserId>`,
   an account id, and the topic is the account's `msgCenter`. Two clients with the same
   client id kick each other off every few seconds (MQTT allows one session per client id).
   Here: one paho client per account, with each push routed to the car it belongs to.

3. **The control-PIN lockout.** The counter that trips the account lock is Chery's, and it is
   per account. Two per-vehicle counters would let two cars together spend twice the
   allowance before either stopped. Here: one `PinLockout` per account.

4. **Minting a taskId.** The chain is queryList -> setVecDefault(vin) -> checkPassword, and
   setVecDefault sets the account's single "active vehicle". Two cars minting at once could
   interleave and bless a taskId for the wrong car. `PinLockout.attempt()` already serialises
   a whole mint, so sharing the lockout (point 3) serialises mints across the account too.

What stays per vehicle, deliberately: the wake and probe cooldowns, their locks, the cached
taskId and its file, the certificates. Those are properties of a car, and sharing them would
make one car wait for the other for no reason.

This module imports neither Home Assistant nor the network: the paho client is built by the
coordinator and handed in, so the routing and reference counting here can be tested alone.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .core.pin_lockout import PinLockout

_LOGGER = logging.getLogger(__name__)

# Keys a push may carry the VIN under, looked up at the top level, in `content` and in
# `content.data`. Not every push has one: that case is handled in `route()`.
VIN_KEYS = ("vin", "VIN", "vehicleVin", "carVin", "vinCode")

# A push WITHOUT a VIN that arrives within this many seconds of a command sent to exactly
# one car is credited to that car. Cars push when something happened to them, and when a
# user has just sent a command that something is usually the command: its confirmation,
# the position reply to "Locate", the telemetry burst of a car that was just woken.
RECENT_COMMAND_S = 180.0


# ───────────────────────────────── token file ─────────────────────────────────
def account_token_path(config_path: Callable[[str], str], domain: str, tuserid: str) -> str:
    """The one token file shared by every vehicle of the account.

    `config_path` is `hass.config.path`, passed in so this stays free of Home Assistant."""
    return config_path(f"{domain}_account_{tuserid}_token.json")


def vehicle_token_path(config_path: Callable[[str], str], domain: str, vin: str) -> str:
    """Where the token lived before it moved to the account (one file per VIN)."""
    return config_path(f"{domain}_{vin}_token.json")


def migrate_token(config_path: Callable[[str], str], domain: str, tuserid: str,
                  vin: str) -> str:
    """Executor. Make sure the account token file exists and return its path.

    On the first start after this change it is seeded from the vehicle's old per-VIN file.
    The old file is COPIED, not moved: going back to an earlier release then still finds a
    token where it expects one. If the account file already exists it is never touched -
    it is the newest token by construction, because every refresh writes it."""
    dest = account_token_path(config_path, domain, tuserid)
    if os.path.isfile(dest):
        return dest
    src = vehicle_token_path(config_path, domain, vin)
    if os.path.isfile(src):
        try:
            shutil.copy2(src, dest)
            os.chmod(dest, 0o600)   # a credential: readable by the owner only
            _LOGGER.info("Session moved to the account-level token file")
        except OSError as err:
            # Fail open: without the copy the vehicle simply asks for a new OTP, which is
            # what would have happened anyway the next time the two copies collided.
            _LOGGER.warning("Could not create the account-level token file: %s", err)
    return dest


# ─────────────────────────────── shared state ───────────────────────────────
@dataclass
class AccountAccess:
    """What the vehicles of one account share. One instance per (account, token file)."""

    key: str
    token_path: str
    # Serialises the token refresh across ALL the account's vehicles. `wake._refresh_token`
    # double-checks inside this lock that the file has not already been renewed by somebody
    # else, which only works if everybody renewing that file takes the same lock.
    token_lock: threading.Lock = field(default_factory=threading.Lock)
    # The account's control-PIN lockout (and, through `attempt()`, its mint serialisation).
    lockout: PinLockout = field(default_factory=PinLockout)
    users: set[str] = field(default_factory=set)


# The registries below are plain dicts owned by the caller (the coordinator keeps them in
# `hass.data`), not module globals: two Home Assistant instances in one process - which is
# what the test suite is - must not share an account's lockout or MQTT session.
_REGISTRY_LOCK = threading.Lock()


def acquire_access(registry: dict, tuserid: str, token_path: str, vin: str) -> AccountAccess:
    """The shared state of `tuserid`, created on first use; `vin` is registered as a user."""
    key = f"{tuserid}|{token_path}"
    with _REGISTRY_LOCK:
        acc = registry.get(key)
        if acc is None:
            acc = AccountAccess(key=key, token_path=token_path)
            registry[key] = acc
        acc.users.add(vin)
        return acc


def release_access(registry: dict, acc: AccountAccess, vin: str) -> None:
    """Forget `vin`; drop the shared state when the last vehicle of the account leaves.

    With a single vehicle this reproduces the old lifetime exactly: the state is created
    with the entry and dropped with it, so a reload still starts from a clean lockout."""
    with _REGISTRY_LOCK:
        acc.users.discard(vin)
        if not acc.users and registry.get(acc.key) is acc:
            del registry[acc.key]


# ─────────────────────────────── push routing ───────────────────────────────
def extract_vin(obj: Any) -> str | None:
    """The VIN a decoded push carries, upper-cased, or None."""
    layers: list[dict] = []
    if isinstance(obj, dict):
        layers.append(obj)
        content = obj.get("content")
        if isinstance(content, dict):
            layers.append(content)
            data = content.get("data")
            if isinstance(data, dict):
                layers.append(data)
    for layer in layers:
        for key in VIN_KEYS:
            value = layer.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()
    return None


def route(obj: Any, vins: list[str], last_command: dict[str, float] | None = None,
          now: float | None = None) -> tuple[list[str], bool]:
    """Which vehicles a push is for. Returns `(targets, attributed)`.

    - The push names a VIN: that vehicle only, or nobody if it is not one of ours.
    - No VIN and one vehicle on the account: that vehicle. This is exactly the behaviour
      before this module existed, so a single-car installation sees no difference.
    - No VIN, several vehicles, and exactly one was sent a command in the last
      `RECENT_COMMAND_S`: that vehicle.
    - Otherwise every vehicle, with `attributed=False`. Such a push cannot be trusted as
      any particular car's state, so it is not applied; each vehicle only takes it as a
      hint to re-read its own state over REST, which is per VIN and therefore unambiguous.
    """
    vin = extract_vin(obj)
    if vin:
        return [v for v in vins if v.upper() == vin], True
    if len(vins) == 1:
        return list(vins), True
    if last_command:
        now = time.time() if now is None else now
        recent = [v for v in vins if now - float(last_command.get(v) or 0.0) < RECENT_COMMAND_S]
        if len(recent) == 1:
            return recent, True
    return list(vins), False


class PushSubscriber(Protocol):
    """What a vehicle exposes to the shared MQTT session."""

    vin: str
    last_command_ts: float

    def on_push(self, obj: Any, attributed: bool) -> None: ...
    def on_mqtt_connection(self, connected: bool, rc: str) -> None: ...


class AccountMqtt:
    """ONE MQTT session per account, shared by its vehicles.

    The paho client is created by `factory(on_connect, on_disconnect, on_message)` the first
    time a vehicle attaches, and stopped when the last one detaches. The factory raises if the
    first connect fails, which the caller turns into `ConfigEntryNotReady` exactly as before.
    """

    def __init__(self, key: str) -> None:
        self.key = key
        self.connected = False
        self._client: Any = None
        self._subs: dict[str, PushSubscriber] = {}
        self._lock = threading.Lock()
        self._warned_unattributed = False

    def subscribers(self) -> list[PushSubscriber]:
        with self._lock:
            return list(self._subs.values())

    def attach(self, sub: PushSubscriber, factory: Callable[..., Any]) -> None:
        """Executor. Join the session, opening it if this is the first vehicle."""
        with self._lock:
            self._subs[sub.vin] = sub
            need_client = self._client is None
        if not need_client:
            sub.on_mqtt_connection(self.connected, "shared")
            return
        try:
            client = factory(self._on_connect, self._on_disconnect, self._on_message)
        except Exception:
            with self._lock:
                self._subs.pop(sub.vin, None)
            raise
        with self._lock:
            self._client = client

    def detach(self, sub: PushSubscriber) -> Any:
        """Executor. Leave the session. Returns the client to stop if this was the last
        vehicle, else None; the caller stops it (disconnect, then loop_stop)."""
        with self._lock:
            if self._subs.get(sub.vin) is sub:
                del self._subs[sub.vin]
            if self._subs:
                return None
            client, self._client = self._client, None
        self.connected = False
        return client

    # paho callbacks (paho thread)
    def _on_connect(self, ok: bool, rc: str) -> None:
        self.connected = ok
        for sub in self.subscribers():
            sub.on_mqtt_connection(ok, rc)

    def _on_disconnect(self, rc: str) -> None:
        self.connected = False
        for sub in self.subscribers():
            sub.on_mqtt_connection(False, rc)

    def _on_message(self, obj: Any) -> None:
        subs = {s.vin: s for s in self.subscribers()}
        last = {vin: float(getattr(s, "last_command_ts", 0.0) or 0.0) for vin, s in subs.items()}
        targets, attributed = route(obj, list(subs), last)
        if not attributed and not self._warned_unattributed:
            self._warned_unattributed = True
            _LOGGER.info(
                "A push arrived without a VIN while %d vehicles share this account. Pushes "
                "like this cannot be assigned to a vehicle, so they only trigger a REST "
                "refresh of each vehicle's state.", len(subs))
        for vin in targets:
            sub = subs.get(vin)
            if sub is None:
                continue
            try:
                sub.on_push(obj, attributed)
            except Exception as err:  # noqa: BLE001 - one vehicle must not starve the other
                _LOGGER.warning("Error handling a push for vehicle …%s: %s", vin[-4:], err)


def mqtt_session(registry: dict, host: str, port: int, channel_id: str,
                 tuserid: str) -> AccountMqtt:
    """The account's shared MQTT session object (not yet connected)."""
    key = f"{host}:{port}/{channel_id}/{tuserid}"
    with _REGISTRY_LOCK:
        session = registry.get(key)
        if session is None:
            session = AccountMqtt(key)
            registry[key] = session
        return session


def forget_mqtt_session(registry: dict, session: AccountMqtt) -> None:
    """Drop the session object once nobody uses it."""
    with _REGISTRY_LOCK:
        if not session.subscribers() and registry.get(session.key) is session:
            del registry[session.key]
