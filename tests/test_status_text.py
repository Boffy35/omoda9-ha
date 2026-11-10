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
