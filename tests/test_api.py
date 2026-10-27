"""API tests with Prisma and Timbre mocked out, so they cost no Gnani credits."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from ugharani import gnani, main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_DB", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("AUDIO_CACHE", str(tmp_path / "tts"))

    async def synthesize(text):
        return b"RIFF" + text.encode()

    monkeypatch.setattr(gnani, "synthesize", synthesize)
    return TestClient(main.app)


def fake_stt(transcript, calls=None):
    async def transcribe(audio, filename, bias=None):
        if calls is not None:
            calls.append(bias)
        return {"success": True, "transcript": transcript, "request_id": "req_test"}
    return transcribe


def post_audio(client, draft=None):
    data = {"draft": json.dumps(draft)} if draft else None
    return client.post("/entries/voice", data=data, files={"audio": ("clip.wav", b"RIFF....", "audio/wav")})


def test_complete_entry_is_read_back_then_saved_on_confirm(client, monkeypatch):
    monkeypatch.setattr(gnani, "transcribe", fake_stt("રમેશભાઈ ને ₹2,40,000 નું માલ આપ્યું, 60 દિવસ"))
    body = post_audio(client).json()

    draft = body["draft"]
    assert (draft["kind"], draft["buyer"], draft["amount"], body["missing"]) == ("credit", "રમેશભાઈ", 240000, [])
    assert draft["due_date"] == (date.today() + timedelta(days=60)).isoformat()
    assert body["say"] == "રમેશભાઈને ₹2,40,000નો માલ, 60 દિવસની મુદત. બરાબર?"
    assert client.get(body["audio"]).content == ("RIFF" + body["say"]).encode()
    assert client.get("/entries").json() == []  # nothing saved until the trader confirms

    assert client.post("/entries", json=draft).json() == {"entry_id": 1}
    assert client.get("/balances").json()[0]["balance"] == 240000


def test_missing_field_is_asked_for_and_filled_by_follow_up(client, monkeypatch):
    monkeypatch.setattr(gnani, "transcribe", fake_stt("રમેશભાઈ ને ₹2,40,000 નું માલ આપ્યું"))
    first = post_audio(client).json()
    assert (first["missing"], first["say"]) == (["due_date"], "કેટલા દિવસની મુદત?")

    monkeypatch.setattr(gnani, "transcribe", fake_stt("60 દિવસ"))
    second = post_audio(client, draft=first["draft"]).json()
    assert second["missing"] == []
    assert (second["draft"]["buyer"], second["draft"]["amount"]) == ("રમેશભાઈ", 240000)
    assert second["draft"]["transcript"] == "રમેશભાઈ ને ₹2,40,000 નું માલ આપ્યું | 60 દિવસ"
    assert second["say"].endswith("બરાબર?")


def test_payment_draft_keeps_its_kind_through_follow_up(client, monkeypatch):
    monkeypatch.setattr(gnani, "transcribe", fake_stt("રમેશભાઈએ પૈસા જમા કરાવ્યા"))
    first = post_audio(client).json()
    assert (first["draft"]["kind"], first["say"]) == ("payment", "કેટલા રૂપિયા જમા થયા?")

    monkeypatch.setattr(gnani, "transcribe", fake_stt("₹50,000"))
    second = post_audio(client, draft=first["draft"]).json()
    assert (second["draft"]["kind"], second["draft"]["amount"], second["missing"]) == ("payment", 50000, [])
    assert second["say"] == "રમેશભાઈ પાસેથી ₹50,000 જમા. બરાબર?"


def test_incomplete_draft_cannot_be_saved(client):
    resp = client.post("/entries", json={"kind": "credit", "buyer": "રમેશભાઈ", "amount": 240000})
    assert resp.status_code == 422
    assert resp.json()["detail"] == {"missing": ["due_date"]}


def test_bad_draft_is_rejected_before_calling_prisma(client, monkeypatch):
    calls = []
    monkeypatch.setattr(gnani, "transcribe", fake_stt("60 દિવસ", calls))
    resp = client.post("/entries/voice", data={"draft": "{not json"}, files={"audio": ("clip.wav", b"RIFF", "audio/wav")})
    assert resp.status_code == 422
    assert calls == []


def test_known_buyers_are_sent_as_bias_and_matched(client, monkeypatch):
    calls = []
    monkeypatch.setattr(gnani, "transcribe", fake_stt("રમેશભાઈ ને ₹1,00,000 નો માલ, 30 દિવસ", calls))
    client.post("/entries", json=post_audio(client).json()["draft"])
    monkeypatch.setattr(gnani, "transcribe", fake_stt("રામેશભાઈએ ₹40,000 જમા કરાવ્યા", calls))
    body = post_audio(client).json()
    client.post("/entries", json=body["draft"])

    assert calls == [[], ["રમેશભાઈ"]]
    assert body["draft"]["buyer"] == "રમેશભાઈ"
    assert [(b["buyer"], b["balance"]) for b in client.get("/balances").json()] == [("રમેશભાઈ", 60000)]


def test_stt_failure_returns_502(client, monkeypatch):
    async def failing(*args, **kwargs):
        raise gnani.GnaniError("HTTP 403: credits exhausted")
    monkeypatch.setattr(gnani, "transcribe", failing)
    resp = post_audio(client)
    assert resp.status_code == 502
    assert "credits exhausted" in resp.json()["detail"]


def test_tts_failure_still_returns_the_draft(client, monkeypatch):
    async def failing(text):
        raise gnani.GnaniError("HTTP 403: credits exhausted")
    monkeypatch.setattr(gnani, "transcribe", fake_stt("રમેશભાઈ ને ₹2,40,000 નું માલ આપ્યું, 60 દિવસ"))
    monkeypatch.setattr(gnani, "synthesize", failing)
    body = post_audio(client).json()
    assert (body["audio"], body["missing"]) == (None, [])
    assert body["say"].endswith("બરાબર?")
