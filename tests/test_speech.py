"""Timbre clip cache, with Timbre mocked out so it costs no Gnani credits."""

import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient

from ugharani import gnani, main, speech
from ugharani.extract import parse


@pytest.fixture
def calls(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_CACHE", str(tmp_path / "tts"))
    calls = []

    async def synthesize(text):
        calls.append(text)
        return b"RIFF" + text.encode()

    monkeypatch.setattr(gnani, "synthesize", synthesize)
    return calls


def test_same_sentence_is_synthesised_once(calls):
    first = asyncio.run(speech.speak("રમેશભાઈ, ₹2,40,000"))
    second = asyncio.run(speech.speak("રમેશભાઈ, ₹2,40,000"))
    other = asyncio.run(speech.speak("કાંતાબેન, ₹75,000"))

    assert first == second != other
    assert calls == ["રમેશભાઈ, ₹2,40,000", "કાંતાબેન, ₹75,000"]


def test_voice_change_gets_a_new_clip(calls, monkeypatch):
    first = asyncio.run(speech.speak("બરાબર?"))
    monkeypatch.setenv("TTS_VOICE", "Other")
    assert asyncio.run(speech.speak("બરાબર?")) != first
    assert len(calls) == 2


def test_audio_endpoint_serves_cached_clips_only(calls):
    key = asyncio.run(speech.speak("બરાબર?"))
    client = TestClient(main.app)

    resp = client.get(f"/audio/{key}.wav")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content == "RIFFબરાબર?".encode()

    assert client.get("/audio/0123456789abcdef.wav").status_code == 404
    assert client.get("/audio/..%2F..%2Fugharani.wav").status_code == 404


@pytest.mark.parametrize("amount, text", [
    (500, "₹500"), (75000, "₹75,000"), (240000, "₹2,40,000"), (12345678, "₹1,23,45,678"),
])
def test_rupees_use_indian_grouping(amount, text):
    assert speech.rupees(amount) == text


def test_latin_buyer_name_gets_a_space_before_the_suffix():
    entry = parse("Rameshbhai ne 2,40,000 nu maal aapyu, 60 divas", today=date(2026, 10, 27))
    assert speech.readback(entry, date(2026, 10, 27)) == "Rameshbhai ને ₹2,40,000નો માલ, 60 દિવસની મુદત. બરાબર?"
