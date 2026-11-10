"""Several vehicles on one account: what they share, what they keep apart.

`docs/design/domain-model.md` has `Access` 1 -- 1..* `Vehicle`: the session token and the
control-PIN lockout belong to the account. These tests pin that down, together with the
two consequences that only show up with a second car on the same login:

* one MQTT session per account (the broker allows one connection per client id, and the
  client id is the account's), with pushes routed to the vehicle they belong to;
* entity_ids that keep two cars apart without moving the first car's ids.

Everything here is synthetic: no VIN, account or token belongs to anybody.
"""
from __future__ import annotations

import os

import pytest
from homeassistant import config_entries, data_entry_flow

import fixtures as FX
from custom_components.omoda9 import access as ACC
from custom_components.omoda9.const import (
    CONF_EMAIL, CONF_ENTITY_TAG, CONF_PIN, CONF_TUSERID, CONF_VIN, DOMAIN,
)
from custom_components.omoda9.naming import tag_entity_id, tag_object_id

VIN_2 = "LZZBBBBBB9Z8Y7X6W"     # VIN_PLACEHOLDER: synthetic, not a real VIN
OTHER_TUSERID = "100000000000000002"


# ───────────────────────── routing a push to its vehicle ─────────────────────────
def test_a_push_that_names_a_vin_goes_to_that_vehicle_only():
    push = {"content": {"serviceType": "5A02", "data": {"vin": VIN_2.lower()}}}
    assert ACC.route(push, [FX.VIN, VIN_2]) == ([VIN_2], True)


def test_a_push_for_a_vin_that_is_not_ours_goes_nowhere():
    push = {"content": {"vin": "LZZCCCCCC0000000X"}}   # VIN_PLACEHOLDER: synthetic
    assert ACC.route(push, [FX.VIN, VIN_2]) == ([], True)


def test_one_vehicle_behaves_exactly_as_before():
    """No VIN, one car: the push is that car's. This is the only case that existed before."""
    push = {"content": {"serviceType": "5A02", "data": {"doorLock": "1"}}}
    assert ACC.route(push, [FX.VIN]) == ([FX.VIN], True)


def test_no_vin_and_two_vehicles_is_credited_to_the_one_just_commanded():
    push = {"content": {"serviceType": "1301", "data": {"lat": "1", "lon": "2"}}}
    now = 10_000.0
    recent = {FX.VIN: now - 5, VIN_2: 0.0}
    assert ACC.route(push, [FX.VIN, VIN_2], recent, now) == ([FX.VIN], True)


def test_no_vin_and_no_way_to_tell_is_never_applied_as_state():
    """Both commanded recently, or neither: the push is a refresh hint for both, never state."""
    push = {"content": {"serviceType": "5A02", "data": {"doorLock": "1"}}}
    now = 10_000.0
    both = {FX.VIN: now - 5, VIN_2: now - 9}
    assert ACC.route(push, [FX.VIN, VIN_2], both, now) == ([FX.VIN, VIN_2], False)
    stale = {FX.VIN: now - ACC.RECENT_COMMAND_S - 1}
    assert ACC.route(push, [FX.VIN, VIN_2], stale, now) == ([FX.VIN, VIN_2], False)


# ───────────────────────── one MQTT session per account ─────────────────────────
class _Vehicle:
    def __init__(self, vin: str) -> None:
        self.vin = vin
        self.last_command_ts = 0.0
        self.pushes: list[tuple[dict, bool]] = []
        self.connection: list[bool] = []

    def on_push(self, obj, attributed):
        self.pushes.append((obj, attributed))

    def on_mqtt_connection(self, connected, rc):
        self.connection.append(connected)


def test_two_vehicles_open_one_client_and_the_last_one_closes_it():
    built: list[object] = []

    def factory(on_connect, on_disconnect, on_message):
        client = object()
        built.append(client)
        return client

    registry: dict = {}
    session = ACC.mqtt_session(registry, "broker", 8883, "1", FX.TUSERID)
    assert ACC.mqtt_session(registry, "broker", 8883, "1", FX.TUSERID) is session

    first, second = _Vehicle(FX.VIN), _Vehicle(VIN_2)
    session.attach(first, factory)
    session.attach(second, factory)
    assert len(built) == 1, "a second client with the account's client id kicks the first off"

    assert session.detach(first) is None, "unloading one car must not cut the other off"
    assert session.detach(second) is built[0]
    ACC.forget_mqtt_session(registry, session)
    assert registry == {}


def test_a_failed_first_connect_leaves_nobody_attached():
    def factory(*_):
        raise RuntimeError("broker unreachable")

    session = ACC.mqtt_session({}, "broker", 8883, "1", FX.TUSERID)
    with pytest.raises(RuntimeError):
        session.attach(_Vehicle(FX.VIN), factory)
    assert session.subscribers() == []


def test_the_session_delivers_each_push_to_its_vehicle():
    session = ACC.mqtt_session({}, "broker", 8883, "1", FX.TUSERID)
    first, second = _Vehicle(FX.VIN), _Vehicle(VIN_2)
    callbacks = {}

    def factory(on_connect, on_disconnect, on_message):
        callbacks.update(connect=on_connect, message=on_message)
        return object()

    session.attach(first, factory)
    session.attach(second, factory)
    # the second vehicle is told the session's state as it joins (not connected yet)
    assert second.connection == [False]
    callbacks["connect"](True, "0")
    assert first.connection[-1] is True and second.connection[-1] is True

    callbacks["message"]({"content": {"vin": VIN_2, "data": {"doorLock": "1"}}})
    assert first.pushes == []
    assert second.pushes == [({"content": {"vin": VIN_2, "data": {"doorLock": "1"}}}, True)]

    callbacks["message"]({"content": {"data": {"doorLock": "0"}}})
    assert [a for _, a in first.pushes] == [False]
    assert [a for _, a in second.pushes][-1] is False


# ───────────────────────── the session token is the account's ─────────────────────────
def test_the_old_per_vehicle_token_seeds_the_account_file_once(tmp_path):
    path = lambda name: str(tmp_path / name)  # noqa: E731
    old = tmp_path / f"{DOMAIN}_{FX.VIN}_token.json"
    old.write_text(FX.token_json(), encoding="utf-8")

    dest = ACC.migrate_token(path, DOMAIN, FX.TUSERID, FX.VIN)
    assert dest == path(f"{DOMAIN}_account_{FX.TUSERID}_token.json")
    assert os.path.isfile(dest)
    assert old.exists(), "copied, not moved: an older release must still find its token"

    # once the account file exists it is the newest token by construction: never overwritten
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("newer")
    ACC.migrate_token(path, DOMAIN, FX.TUSERID, VIN_2)
    with open(dest, encoding="utf-8") as fh:
        assert fh.read() == "newer"


def _coordinator(hass, vin, tuserid=FX.TUSERID, **extra):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.omoda9.coordinator import Omoda9Coordinator

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=vin,
        data={CONF_VIN: vin, CONF_TUSERID: tuserid, CONF_EMAIL: FX.EMAIL,
              CONF_PIN: FX.PIN, **extra})
    entry.add_to_hass(hass)
    return Omoda9Coordinator(hass, entry)


def test_vehicles_of_one_account_share_token_lock_and_pin_lockout(hass):
    first, second = _coordinator(hass, FX.VIN), _coordinator(hass, VIN_2)

    assert first.ctx.token_path == second.ctx.token_path
    assert first.ctx.stato.lock_token is second.ctx.stato.lock_token
    assert first.ctx.lockout is second.ctx.lockout, (
        "the lockout counter is Chery's and per account: two counters would spend twice "
        "the allowance before either stopped")
    # what is a property of the CAR stays per car
    assert first.ctx.taskid_file != second.ctx.taskid_file
    assert first.ctx.stato.lock_sveglia is not second.ctx.stato.lock_sveglia


def test_vehicles_of_different_accounts_share_nothing(hass):
    first = _coordinator(hass, FX.VIN)
    other = _coordinator(hass, VIN_2, tuserid=OTHER_TUSERID)

    assert first.ctx.token_path != other.ctx.token_path
    assert first.ctx.stato.lock_token is not other.ctx.stato.lock_token
    assert first.ctx.lockout is not other.ctx.lockout


def test_the_account_state_goes_with_its_last_vehicle(hass):
    first, second = _coordinator(hass, FX.VIN), _coordinator(hass, VIN_2)
    shared = first.ctx.lockout
    second.ctx  # noqa: B018 - building the context registers the vehicle

    first.async_stop()
    assert second.ctx.lockout is shared, "the other car still uses the account state"
    second.async_stop()

    again = _coordinator(hass, FX.VIN)
    assert again.ctx.lockout is not shared, "a reload starts from a clean lockout, as before"


# ───────────────────────── entity ids of a second vehicle ─────────────────────────
def test_the_tag_goes_after_the_prefix_and_an_empty_tag_changes_nothing():
    assert tag_object_id("chery_connect_battery", "") == "chery_connect_battery"
    assert tag_object_id("chery_connect_battery", "car2") == "chery_connect_car2_battery"
    assert tag_object_id("omoda9_custom", "car2") == "omoda9_custom_car2"
    assert tag_entity_id("sensor.chery_connect_battery", "car2") == \
        "sensor.chery_connect_car2_battery"


def test_a_tagged_vehicle_gets_tagged_entity_ids(hass):
    from homeassistant.components.sensor import ENTITY_ID_FORMAT

    from custom_components.omoda9.entity import Omoda9Entity

    first = _coordinator(hass, FX.VIN)
    second = _coordinator(hass, VIN_2, **{CONF_ENTITY_TAG: "car2"})

    a = Omoda9Entity(first, "Battery", "battery", object_id="chery_connect_battery",
                     entity_id_format=ENTITY_ID_FORMAT, translation_key="battery")
    b = Omoda9Entity(second, "Battery", "battery", object_id="chery_connect_battery",
                     entity_id_format=ENTITY_ID_FORMAT, translation_key="battery")
    assert a.entity_id == "sensor.chery_connect_battery"
    assert b.entity_id == "sensor.chery_connect_car2_battery"
    assert a.translation_key == b.translation_key == "battery"
    assert a.unique_id != b.unique_id


# ───────────────────────── adding a second vehicle without a new login ─────────────────────────
async def test_a_second_vehicle_is_added_from_the_signed_in_account(
        hass, config_entry, monkeypatch):
    """No OTP: the account is already signed in, its token lists the other vehicle."""
    import custom_components.omoda9 as integration
    from custom_components.omoda9 import config_flow as cf

    async def _no_setup(hass, entry):   # the new entry is not started: no cloud in a test
        return True

    monkeypatch.setattr(integration, "async_setup_entry", _no_setup)
    monkeypatch.setattr(cf, "_discover_on_account", lambda hass, data: (
        "ok", [{"vin": FX.VIN, "nickname": "First"},
               {"vin": VIN_2, "nickname": "Second"}], "ok"))
    sent = []
    monkeypatch.setattr(cf, "_send_otp", lambda *a: sent.append(a) or (True, ""))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert "add_vehicle" in result["menu_options"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "add_vehicle"})
    assert result["step_id"] == "add_vehicle_pick"
    offered = result["data_schema"].schema[CONF_VIN].container
    assert list(offered) == [VIN_2], "the vehicle already configured is not offered again"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VIN: VIN_2, CONF_ENTITY_TAG: "Car 2"})
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_VIN] == VIN_2
    assert data[CONF_TUSERID] == FX.TUSERID
    assert data[CONF_EMAIL] == FX.EMAIL and data[CONF_PIN] == FX.PIN
    assert data[CONF_ENTITY_TAG] == "car_2"
    assert sent == [], "no code is sent when the account is already signed in"


async def test_the_first_vehicle_is_not_offered_the_shortcut(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert "add_vehicle" not in result["menu_options"]


async def test_an_expired_account_says_so_instead_of_asking_for_a_code(
        hass, config_entry, monkeypatch):
    from custom_components.omoda9 import config_flow as cf

    monkeypatch.setattr(cf, "_discover_on_account",
                        lambda hass, data: ("reauth", [], "session expired"))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "add_vehicle"})
    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "account_reauth_needed"
