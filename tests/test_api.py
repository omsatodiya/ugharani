"""API tests with Prisma mocked out, so they cost no Gnani credits."""

import pytest
from fastapi.testclient import TestClient

from ugharani import gnani, main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_DB", str(tmp_path / "ledger.db"))
    return TestClient(main.app)


def fake_stt(transcript, calls=None):
    async def transcribe(audio, filename, bias=None):
        if calls is not None:
            calls.append(bias)
        return {"success": True, "transcript": transcript, "request_id": "req_test"}
    return transcribe


def post_audio(client):
    return client.post("/entries/voice", files={"audio": ("clip.wav", b"RIFF....", "audio/wav")})


def test_complete_entry_is_saved(client, monkeypatch):
    monkeypatch.setattr(gnani, "transcribe", fake_stt("રમેશભાઈ ને ₹2,40,000 નું માલ આપ્યું, 60 દિવસ"))
    body = post_audio(client).json()
    assert (body["kind"], body["buyer"], body["amount"], body["missing"]) == ("credit", "રમેશભાઈ", 240000, [])
    assert body["entry_id"] == 1
    assert client.get("/balances").json()[0]["balance"] == 240000


def test_incomplete_entry_is_not_saved(client, monkeypatch):
    monkeypatch.setattr(gnani, "transcribe", fake_stt("રમેશભાઈ ને ₹2,40,000 નું માલ આપ્યું"))
    body = post_audio(client).json()
    assert (body["entry_id"], body["missing"]) == (None, ["due_date"])
    assert client.get("/entries").json() == []


def test_known_buyers_are_sent_as_bias_and_matched(client, monkeypatch):
    calls = []
    monkeypatch.setattr(gnani, "transcribe", fake_stt("રમેશભાઈ ને ₹1,00,000 નો માલ, 30 દિવસ", calls))
    post_audio(client)
    monkeypatch.setattr(gnani, "transcribe", fake_stt("રામેશભાઈએ ₹40,000 જમા કરાવ્યા", calls))
    body = post_audio(client).json()

    assert calls == [[], ["રમેશભાઈ"]]
    assert body["buyer"] == "રમેશભાઈ"
    assert [(b["buyer"], b["balance"]) for b in client.get("/balances").json()] == [("રમેશભાઈ", 60000)]


def test_stt_failure_returns_502(client, monkeypatch):
    async def failing(*args, **kwargs):
        raise gnani.GnaniError("HTTP 403: credits exhausted")
    monkeypatch.setattr(gnani, "transcribe", failing)
    resp = post_audio(client)
    assert resp.status_code == 502
    assert "credits exhausted" in resp.json()["detail"]
