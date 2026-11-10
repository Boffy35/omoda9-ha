"""English for the free-text status sensors, for entries whose language is English.

What this is for. Four diagnostic sensors - command result, wake result, location probe
result and session status - show progress text written by `core/` and the coordinator.
That text is Italian. The `omoda_jaecoo` line had translated it to English (most of the
wording below is that line's, by @JackRonan); the merge into this repository brought the
Italian back, so an English-speaking user now reads "Sonda: ancora niente posizione ad
auto sveglia" where they used to read "No live data yet".

How. The text is translated where it becomes an entity state, not where it is written:
`core/` keeps producing exactly what it produces today, and nothing in the protocol layer
changes. A sentence is matched whole (EXACT), then by shape (PATTERNS, for sentences with
values in them), then the pieces that recur inside other sentences are swapped
(FRAGMENTS: command names, backend code meanings).

Fail open. A sentence nobody has listed here comes out exactly as it went in. Adding one
is a line in a table; forgetting one costs an Italian message, never a lost one.

Only entries whose language is English are affected (`wants_english`). An Italian entry,
and every entry created before the language field existed, sees no difference at all.
"""
from __future__ import annotations

import re

# ─────────────────────────────── whole sentences ───────────────────────────────
EXACT: dict[str, str] = {
    # coordinator: wake fallback and "refresh full status"
    "Sveglia SMS non efficace → ripiego su Localizza (vehicleLocation)…":
        "SMS wake unsuccessful → falling back to Locate (vehicleLocation)…",
    "Stato aggiornato — alta tensione già accesa ✅":
        "Status updated — high voltage already on ✅",
    "Accendo il clima per ~1 min per leggere i dati reali (odometro/batteria)…":
        "Turning on climate for ~1 min to read real data (odometer/battery)…",
    "Stato aggiornato con dati reali ✅": "Status updated with real data ✅",
    "L'auto non si è accesa in tempo — riprova, o si aggiornerà al prossimo viaggio":
        "The car did not wake in time — try again, or it will update on the next drive",
    "inviato": "sent",
    "richiesta inviata": "request sent",
    "invio non riuscito": "sending failed",
    # core/wake.py
    "⏳ Sveglia già in corso, attendi…": "⏳ Wake-up already in progress, please wait…",
    "🟢 Auto già sveglia (sta inviando dati) — sveglia non necessaria":
        "🟢 Car already awake (sending data) — no wake-up needed",
    "🔑 Accesso in corso…": "🔑 Signing in…",
    "🔑 Sessione scaduta (token vecchio o app ufficiale aperta): rifai il login OTP":
        "🔑 Session expired (old token, or the official app was opened): sign in again "
        "with a code",
    "✅ Sveglia inviata — attendo che l'auto si connetta…":
        "✅ Wake-up sent — waiting for the car to connect…",
    "🚫 Rate-limit sveglia (A07312): l'auto rifiuta altre sveglie ora. Riprova più tardi":
        "🚫 Wake-up rate limit (A07312): the car is refusing more wake-ups right now. "
        "Try again later",
    "🧪 (test) smsAwaken NON inviato; passo solo al poll":
        "🧪 (test) smsAwaken NOT sent; polling only",
    "🟢 Auto ONLINE — sta inviando dati in tempo reale": "🟢 Car ONLINE — sending live data",
    "🟢 Auto ONLINE — dati realtime ricevuti": "🟢 Car ONLINE — live data received",
    "⌛ Auto ancora a riposo (A07900). Riprova quando è stata usata di recente o ha buon "
    "segnale":
        "⌛ Car still asleep (A07900). Try again once it has been used recently or has "
        "good signal",
    # core/commands.py
    "conio taskId (checkPassword)…": "getting a command token (checkPassword)…",
    "login fallito (token scaduto? rifare OTP ad app chiusa)":
        "sign-in failed (session expired? sign in again with a code, official app closed)",
    "nessun taskId disponibile (conio disattivato)":
        "no command token available (minting disabled)",
    "taskId non più valido → lo rinnovo e riprovo…":
        "command token no longer valid → renewing it and retrying…",
    # core/session.py
    "timeout invio OTP — riprova": "timed out sending the code — try again",
    "conio il token col codice…": "signing in with the code…",
    "conio il token con la password…": "signing in with the password…",
    "Sessione attiva ✅": "Session active ✅",
    "Sessione ripristinata ✅": "Session restored ✅",
    "Sessione scaduta ❌ — riautentica da Home Assistant e chiedi un codice nuovo":
        "Session expired ❌ — re-authenticate in Home Assistant and ask for a new code",
    "nessun codice inserito": "no code entered",
    "nessuna password inserita": "no password entered",
    "timeout conio token": "timed out signing in",
    # core/probe.py
    "🛰️ Sonda posizione: l'auto è sveglia, provo a leggere GPS/realtime…":
        "🛰️ Location probe: reading GPS and live data…",
    "🔑 Sonda: sessione scaduta (rifai login OTP). Riprovo al prossimo risveglio":
        "🔑 Probe: session expired (sign in again with a code). Will retry at the next wake-up",
    "🟢🛰️ Sonda: dati ricevuti ad auto sveglia": "🟢🛰️ Live data received from the vehicle",
}

# ─────────────────────────────── sentences with values ───────────────────────────────
# Matched against the whole text; `\1`, `\2` carry the values across unchanged.
PATTERNS: list[tuple[re.Pattern, str]] = [(re.compile(rx, re.S), en) for rx, en in (
    (r"^fallback Localizza fallito: (.*)$", r"Locate fallback failed: \1"),
    (r"^Non riesco ad accendere il clima: (.*)$", r"Failed to turn on climate: \1"),
    (r"^⚠️ Errore sveglia: (.*)$", r"⚠️ Wake-up error: \1"),
    (r"^⏳ Anti rate-limit: aspetta ancora (\S+) prima di risvegliare di nuovo$",
     r"⏳ Rate-limit guard: wait another \1 before waking the car again"),
    (r"^⚠️ Sveglia non accettata \((.*)\)\. Provo comunque ad ascoltare…$",
     r"⚠️ Wake-up not accepted (\1). Listening anyway…"),
    (r"^… in attesa risveglio \((.*)\) — ancora ~(\d+)s$",
     r"… waiting for the car to wake (\1) — about \2s left"),
    (r"^checkPassword fallito: (.*)$", r"checkPassword failed: \1"),
    (r"^durata (\S+) non ammessa da questa vettura \((.*)\) → uso (\S+)$",
     r"duration \1 not supported by this car (\2) → using \3"),
    (r"^comando sconosciuto: (.*)$", r"unknown command: \1"),
    (r"^invio (.+) \(taskId:(.*)\)…$", r"sending \1 (taskId: \2)…"),
    (r"^errore rete: (.*)$", r"network error: \1"),
    (r"^invio codice OTP via SMS …$", "sending a code by SMS…"),
    (r"^invio codice OTP …$", "sending a code…"),
    (r"^(📱|📧) Codice inviato (.*) — inseriscilo nel campo «Codice OTP» e premi «Conferma»$",
     r"\1 Code sent \2 — enter it in the «OTP code» field and press «Confirm OTP»"),
    (r"^invio OTP fallito: (.*)$", r"sending the code failed: \1"),
    (r"^rinnovo non riuscito per la rete \((.*)\)$",
     r"session renewal failed: network problem (\1)"),
    (r"^codice accettato, ma il login al gateway e' fallito: (.*)$",
     r"code accepted, but signing in to the gateway failed: \1"),
    (r"^codice rifiutato: (.*)$", r"code rejected: \1"),
    (r"^password accettata, ma il login al gateway e' fallito: (.*)$",
     r"password accepted, but signing in to the gateway failed: \1"),
    (r"^password rifiutata: (.*)$", r"password rejected: \1"),
    (r"^⚠️ Sonda: errore pubblicazione dati \((.*)\)$",
     r"⚠️ Probe: error processing vehicle data (\1)"),
    (r"^🟢🛰️ SVOLTA: dati realtime ricevuti ad auto sveglia! (.*)$",
     r"🟢🛰️ Live data received from the vehicle — \1"),
    # The probe prints this whether or not the car is awake; it means "no live data".
    (r"^🟡 Sonda: ancora niente posizione ad auto sveglia \((.*)\)\. Confermato: serve un "
     r"altro passo$",
     r"🟡 No live data — the car isn't reporting right now, probably asleep (\1). It will "
     r"update when it is driven, charged or woken"),
    (r"^⚠️ Sonda errore: (.*)$", r"⚠️ Probe error: \1"),
    (r"^PIN bloccato dopo (\d+) tentativi errati$",
     r"PIN locked after \1 wrong attempts"),
)]

# ─────────────────────────────── recurring pieces ───────────────────────────────
# Command names (core/commands.py COMMANDS) and backend code meanings (core/codes.py), which
# appear inside other sentences: "Clima acceso: HTTP 200 A00079 — comando accettato ✅".
# Replaced longest first, so "Clima acceso" never eats part of a longer name.
FRAGMENTS: dict[str, str] = {
    # command names
    "Clima acceso": "Climate on",
    "Clima spento": "Climate off",
    "Sbrina parabrezza OFF": "Windshield defrost off",
    "Sbrina parabrezza": "Windshield defrost",
    "Disappanna parabrezza OFF": "Windshield demist off",
    "Disappanna parabrezza": "Windshield demist",
    "Sbrina lunotto OFF": "Rear window defrost off",
    "Sbrina lunotto": "Rear window defrost",
    "Volante riscaldato OFF": "Steering wheel heating off",
    "Volante riscaldato": "Steering wheel heating",
    "Sedile guida riscaldato OFF": "Driver seat heating off",
    "Sedile guida riscaldato": "Driver seat heating",
    "Sedile guida ventilato OFF": "Driver seat ventilation off",
    "Sedile guida ventilato": "Driver seat ventilation",
    "Sedile passeggero riscaldato OFF": "Passenger seat heating off",
    "Sedile passeggero riscaldato": "Passenger seat heating",
    "Sedile passeggero ventilato OFF": "Passenger seat ventilation off",
    "Sedile passeggero ventilato": "Passenger seat ventilation",
    "Sedile post. SX riscaldato OFF": "Rear left seat heating off",
    "Sedile post. SX riscaldato": "Rear left seat heating",
    "Sedile post. SX ventilato OFF": "Rear left seat ventilation off",
    "Sedile post. SX ventilato": "Rear left seat ventilation",
    "Sedile post. DX riscaldato OFF": "Rear right seat heating off",
    "Sedile post. DX riscaldato": "Rear right seat heating",
    "Sedile post. DX ventilato OFF": "Rear right seat ventilation off",
    "Sedile post. DX ventilato": "Rear right seat ventilation",
    "Raffredda tutto OFF": "Cool everything off",
    "Raffredda tutto": "Cool everything",
    "Riscalda tutto OFF": "Heat everything off",
    "Riscalda tutto": "Heat everything",
    "Sblocca porte": "Unlock doors",
    "Blocca porte": "Lock doors",
    "Apri baule": "Open trunk",
    "Chiudi baule": "Close trunk",
    "Apri finestrini": "Open windows",
    "Chiudi finestrini": "Close windows",
    "Ventila finestrini": "Vent windows",
    "Apri tetto": "Open sunroof",
    "Chiudi tetto": "Close sunroof",
    "Ventila tetto": "Vent sunroof",
    "Avvia ricarica": "Start charging",
    "Ferma ricarica": "Stop charging",
    "Ricarica programmata ON": "Scheduled charging on",
    "Ricarica programmata OFF": "Scheduled charging off",
    "Trova auto (lampeggio)": "Find car (flash lights)",
    "Localizza auto (GPS)": "Locate car (GPS)",
    "Antifurto acceso": "Alarm on",
    "Antifurto spento": "Alarm off",
    # backend code meanings (core/codes.py CODE_MEANING)
    "comando accettato ✅": "command accepted ✅",
    "auto occupata ⏳ (un altro comando è in corso) — riprova tra qualche secondo":
        "car busy ⏳ (another command is in progress) — retry in a few seconds",
    "funzione non autorizzata su questa auto 🚫 (non è il PIN) · "
    "not authorised on this vehicle (this is not your PIN)":
        "not authorised on this vehicle 🚫 (this is not your PIN)",
    "taskId non valido ❌ (serve un taskId benedetto da checkPassword)":
        "invalid command token ❌ (needs one issued by checkPassword)",
    "taskId non valido ❌ (scene errato in checkPassword)":
        "invalid command token ❌ (wrong scene in checkPassword)",
    "parametri checkPassword incompleti ❌": "incomplete checkPassword parameters ❌",
    "token scaduto/non valido ❌ (rifai il login OTP)":
        "session expired/invalid ❌ (sign in again with a code)",
    "rate-limit sveglia 🚫 (l'auto rifiuta altre sveglie ora, riprova più tardi)":
        "wake-up rate limit 🚫 (the car is refusing more wake-ups right now, try again later)",
    "auto a riposo / non raggiungibile (o firma/car_token non validi) ⌛":
        "car asleep / unreachable (or signature/car token invalid) ⌛",
    "nessun codice": "no code",
    # where a code was sent (core/session.py)
    "alla mail ": "to ",
    "al numero ": "to ",
}
_FRAGMENTS_ORDERED = sorted(FRAGMENTS.items(), key=lambda kv: len(kv[0]), reverse=True)

# Pieces that need a pattern because they carry a value.
FRAGMENT_PATTERNS: list[tuple[re.Pattern, str]] = [(re.compile(rx), en) for rx, en in (
    (r"\[codice ([A-Za-z0-9]+)\]", r"[code \1]"),
    (r"\bcodice ([A-Z][A-Z0-9]{3,})\b", r"code \1"),
    (r" · saltate (\d+) funzioni non autorizzate su questa auto · \d+ skipped "
     r"\(not authorised\)", r" · \1 skipped (not authorised on this car)"),
)]

# ─────────────────────────────── sensor values ───────────────────────────────
# The value maps of the enum-like sensors (sensor.py) and the lock / seat-level fields.
VALUES: dict[str, str] = {
    "Non in ricarica": "Not charging",
    "In ricarica": "Charging",
    "Ricarica completata": "Charging completed",
    "Disattivata": "Disabled",
    "Attiva": "Active",
    "In esecuzione": "Running",
    "Scollegata": "Disconnected",
    "Collegata": "Connected",
    "Collegata (ricarica rapida)": "Connected (fast charging)",
    "Bloccata": "Locked",
    "Sbloccata": "Unlocked",
}
_VALUE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^Livello (.+)$"), r"Level \1"),
    (re.compile(r"^Sconosciuto \((.*)\)$"), r"Unknown (\1)"),
]


def wants_english(language: str | None) -> bool:
    """True for an entry whose call language is English (`en-GB`, `en-US`, ...)."""
    return str(language or "").strip().lower().startswith("en")


def _fragments(text: str) -> str:
    for it, en in _FRAGMENTS_ORDERED:
        if it in text:
            text = text.replace(it, en)
    for rx, en in FRAGMENT_PATTERNS:
        text = rx.sub(en, text)
    return text


def to_english(text):
    """The English for a status sentence, or the sentence unchanged if it is not listed."""
    if not isinstance(text, str) or not text:
        return text
    exact = EXACT.get(text)
    if exact is not None:
        return exact
    for rx, en in PATTERNS:
        m = rx.match(text)
        if m:
            return _fragments(m.expand(en))
    return _fragments(text)


def value_to_english(value):
    """The English for an enum-like sensor value, or the value unchanged."""
    if not isinstance(value, str):
        return value
    if value in VALUES:
        return VALUES[value]
    for rx, en in _VALUE_PATTERNS:
        m = rx.match(value)
        if m:
            return m.expand(en)
    return value
