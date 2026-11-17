"""English status text for entries whose language is English (status_text.py).

The free-text diagnostic sensors carry sentences written in Italian by core/ and the
coordinator. For an English entry they are shown in English; for an Italian entry, and for
any sentence not listed, nothing changes. These tests pin both halves, and ratchet the two
lists that grow with the code: a new command or a new backend code without an English name
fails here instead of reaching an English user in Italian.
"""
from __future__ import annotations

import pytest

from custom_components.omoda9.core import codes
from custom_components.omoda9.core.commands import COMMANDS
from custom_components.omoda9.status_text import (
    to_english,
    value_to_english,
    wants_english,
)


@pytest.mark.parametrize("language,expected", [
    ("en-GB", True), ("en-US", True), ("EN", True),
    ("it-IT", False), ("", False), (None, False),
])
def test_only_english_entries_are_translated(language, expected):
    assert wants_english(language) is expected


def test_the_probe_sentence_users_actually_see():
    """Seen on a Jaecoo 8 on 2026-11-10, with the car parked and asleep."""
    italian = ("🟡 Sonda: ancora niente posizione ad auto sveglia (realtime=S0500 "
               "[codice S0500], location=None, travel=None). Confermato: serve un altro passo")
    english = to_english(italian)
    assert english.startswith("🟡 No live data")
    assert "realtime=S0500 [code S0500], location=None, travel=None" in english
    assert "Sonda" not in english and "codice" not in english


def test_a_command_result_is_translated_piece_by_piece():
    name = dict(COMMANDS)["clima_on"]["name"]
    italian = f"{name}: HTTP 200 A00079 — {codes.meaning('A00079')}"
    assert to_english(italian) == "Climate on: HTTP 200 A00079 — command accepted ✅"


def test_values_carry_through_a_pattern():
    assert to_english("⏳ Anti rate-limit: aspetta ancora 3m05s prima di risvegliare di nuovo") \
        == "⏳ Rate-limit guard: wait another 3m05s before waking the car again"
    assert to_english("invio Blocca porte (taskId:cache)…") == \
        "sending Lock doors (taskId: cache)…"


def test_an_unlisted_sentence_comes_out_unchanged():
    """Fail open: forgetting a sentence costs an Italian message, never a lost one."""
    text = "una frase che nessuno ha ancora elencato"
    assert to_english(text) == text
    assert to_english("") == ""
    assert to_english(None) is None


def test_enum_values():
    assert value_to_english("In ricarica") == "Charging"
    assert value_to_english("Non in ricarica") == "Not charging"
    assert value_to_english("Disattivata") == "Disabled"
    assert value_to_english("Bloccata") == "Locked"
    assert value_to_english("Livello 2") == "Level 2"
    assert value_to_english("Sconosciuto (7)") == "Unknown (7)"
    assert value_to_english("qualcos'altro") == "qualcos'altro"
    assert value_to_english(42) == 42


@pytest.mark.parametrize("key,spec", COMMANDS, ids=[k for k, _ in COMMANDS])
def test_every_command_has_an_english_name(key, spec):
    """Ratchet: a command added to core/commands.py needs a line in FRAGMENTS."""
    assert to_english(spec["name"]) != spec["name"], (
        f"command {key!r} ({spec['name']!r}) has no English name in status_text.FRAGMENTS")


@pytest.mark.parametrize("code", sorted(codes.CODE_MEANING))
def test_every_backend_code_has_an_english_meaning(code):
    """Ratchet: a code added to core/codes.py needs a line in FRAGMENTS (except "ok")."""
    meaning = codes.CODE_MEANING[code]
    if meaning == "ok ✅":
        return
    assert to_english(meaning) != meaning, (
        f"code {code} ({meaning!r}) has no English meaning in status_text.FRAGMENTS")


# ─────────────────────── the car's confirmations and the errors users see ───────────────────────
def test_the_cars_confirmation_messages():
    """Seen on a Jaecoo 7 on 2026-11-10: the confirmation stayed Italian on an English entry."""
    from custom_components.omoda9.coordinator import Omoda9Coordinator

    assert to_english(Omoda9Coordinator._format_cmd_result({"result": "1"})) == \
        "Command carried out and confirmed by the car ✅"
    assert to_english(Omoda9Coordinator._format_cmd_result({"result": "5"})) == \
        "Command running on the car… ⏳"
    assert to_english(Omoda9Coordinator._format_cmd_result({"result": "9"})) == \
        "Confirmation received from the car (result code 9)"


def test_a_refused_command_error_reads_in_english():
    """The error raised when Chery refuses a command (A00084), as seen on 2026-11-10."""
    name = dict(COMMANDS)["ricarica_start"]["name"]
    italian = (f"Comando «ricarica_start» non riuscito: {name}: HTTP 200 A00084 — "
               f"{codes.meaning('A00084')}")
    assert to_english(italian) == ("Command «ricarica_start» failed: Start charging: HTTP 200 "
                                   "A00084 — not authorised on this vehicle 🚫 (this is not your PIN)")


def _text_sensor(hass, language):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    import fixtures as FX
    from custom_components.omoda9.const import (
        CONF_EMAIL, CONF_LANGUAGE, CONF_PIN, CONF_TUSERID, CONF_VIN, DOMAIN,
    )
    from custom_components.omoda9.coordinator import Omoda9Coordinator
    from custom_components.omoda9.sensor import Omoda9TextSensor

    entry = MockConfigEntry(domain=DOMAIN, unique_id=FX.VIN, data={
        CONF_VIN: FX.VIN, CONF_TUSERID: FX.TUSERID, CONF_EMAIL: FX.EMAIL, CONF_PIN: FX.PIN,
        CONF_LANGUAGE: language})
    entry.add_to_hass(hass)
    coord = Omoda9Coordinator(hass, entry)
    coord.data = {**coord.data, "cmd_status": "Comando eseguito e confermato dall'auto ✅"}
    return Omoda9TextSensor(coord, "Omoda9 Esito comando", "cmd_status", "cmd_status", "mdi:car-cog")


def test_the_status_sensors_themselves_show_english(hass):
    """Pins the sensor, not only the table: Omoda9TextSensor overrides native_value, and that
    override skipped the translation until this test existed."""
    assert _text_sensor(hass, "en-GB").native_value == \
        "Command carried out and confirmed by the car ✅"


def test_an_italian_entry_is_left_alone(hass):
    assert _text_sensor(hass, "it-IT").native_value == "Comando eseguito e confermato dall'auto ✅"


# ─────────────────────── results with the warnings joined to them ───────────────────────
_ROUTED_OFF = ("questa funzione non è autorizzata sulla sua via abituale su questo veicolo: "
               "inviata tramite il clima, che quindi si spegne insieme a lei")


def test_a_result_with_a_joined_warning_reads_in_english():
    """Seen on a Jaecoo 7 on 2026-11-17: the confirmation and the routing note, joined with
    « · », both stayed Italian because the whole line matched nothing."""
    name = "Sedile guida riscaldato OFF"
    line = f"Comando eseguito e confermato dall'auto ✅ · {name}: {_ROUTED_OFF}"
    assert to_english(line) == (
        "Command carried out and confirmed by the car ✅ · Driver seat heating off: this "
        "function is not allowed by its usual route on this car: sent through the climate "
        "control, which turns off with it")


@pytest.mark.parametrize("acceso", [True, False])
def test_every_permission_note_has_english(acceso):
    """Ratchet: the notes core/permessi.py shows before sending, built by the code itself."""
    from custom_components.omoda9.core import permessi

    notes = [permessi.MSG_RICOMPOSTA, permessi.MSG_CATEGORIA_NEGATA, permessi.MSG_BASE_NEGATA]
    for (endpoint, campo) in permessi.RIPIEGO:
        _, _, nota = permessi.instrada(endpoint, {campo: "1" if acceso else "0"},
                                       _all_allowed_but(permessi, endpoint, campo))
        assert nota, f"no routing note for {endpoint}/{campo}: the test lost its premise"
        notes.append(nota)
    for note in notes:
        assert to_english(note) != note, f"no English for permission note {note!r}"


def _all_allowed_but(permessi, endpoint, campo):
    """A permission list where the field's usual route is closed and the climate one open."""
    dedicata, _ = permessi.RIPIEGO[(endpoint, campo)]
    return {dedicata: 0}


def test_skipped_parts_and_the_log_tail():
    assert to_english("Clima acceso: non autorizzate su questa auto, salto sedile guida, "
                      "aria sedile post. DX") == \
        "Climate on: not allowed on this car, skipping driver seat, rear right seat ventilation"
    assert to_english("Clima acceso: HTTP 200 A00079 — comando accettato ✅ · (+2 nel registro)") \
        == "Climate on: HTTP 200 A00079 — command accepted ✅ · (+2 more in the log)"


def test_the_bilingual_wake_message_keeps_only_english():
    assert to_english("Sveglio l'auto: il comando parte fra ~25 s · Waking the car: command "
                      "goes out in ~25 s") == "Waking the car: command goes out in ~25 s"
