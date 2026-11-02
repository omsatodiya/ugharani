"""Live calls with Gnani (live STT, Timbre) and Gemini faked: no credits, no network."""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ugharani import gnani, live, llm, main, speech

LOUD = bytes([0, 16])  # one PCM16 sample of 4096: speech, not the silence the trimmer drops
OPENING = "નમસ્તે, રમેશભાઈ બોલો છો? હું કાવ્યા, જીનિયસ પોલીપ્લાસ્ટ, ગોંડલથી બોલું છું. આ કૉલ રેકોર્ડ થાય છે."


class FakeSTT:
    """Audio frames starting with b'SAY:' become a speech_start + transcript, as if spoken."""

    def __init__(self):
        self.queue = asyncio.Queue()
        self.audio = bytearray()

    async def send(self, pcm):
        if pcm.startswith(b"SAY:"):
            await self.queue.put({"type": "speech_start"})
            await self.queue.put({"type": "transcript", "text": pcm[4:].decode()})
        else:
            self.audio += pcm

    async def events(self):
        while (event := await self.queue.get()) is not None:
            yield event


@pytest.fixture
def phone(tmp_path, monkeypatch):
    """A client with a ringing-then-answered call to રમેશભાઈ, and the fakes' records."""
    monkeypatch.setenv("LEDGER_DB", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("AUDIO_CACHE", str(tmp_path / "tts"))
    rec = {"replies": [], "histories": [], "tts": [], "speech_seconds": {}}

    async def synthesize_stream(text):
        rec["tts"].append(text)
        yield LOUD * int(16000 * rec["speech_seconds"].get(text, 0.1))

    async def synthesize(text):
        return gnani._wav(b"".join([c async for c in synthesize_stream(text)]))

    async def stream(system, history, max_tokens=400):
        rec["histories"].append([dict(h) for h in history])
        reply = rec["replies"].pop(0)
        if isinstance(reply, tuple):  # (delay, text): a slow Gemini
            await asyncio.sleep(reply[0])
            reply = reply[1]
        for word in reply.split(" "):  # token by token, like the real stream
            yield word + " "

    @asynccontextmanager
    async def live_stt(keyterms=None):
        rec["keyterms"] = keyterms
        rec["stt"] = FakeSTT()
        yield rec["stt"]

    monkeypatch.setattr(gnani, "synthesize_stream", synthesize_stream)
    monkeypatch.setattr(gnani, "synthesize", synthesize)
    monkeypatch.setattr(gnani, "live_stt", live_stt)
    monkeypatch.setattr(llm, "stream", stream)
    for name, value in {"GREETING_WAIT": 0.05, "FILLER_AFTER": 5, "NO_REPLY": 5, "AFTER_LAST_WORD": 0,
                        "ECHO_MARGIN": 0.5}.items():
        monkeypatch.setattr(live, name, value)

    client = TestClient(main.app)
    client.post("/entries", json={"kind": "credit", "buyer": "રમેશભાઈ", "amount": 100000,
                                  "due_date": date.today().isoformat()})
    client.put("/customers/રમેશભાઈ", json={"phone": "9800000001", "deals_with": "મનીષભાઈ",
                                           "firm": "શ્રીજી હાર્ડવેર", "city": "જેતપુર"})
    call = client.post("/calls", json={"customer": "રમેશભાઈ"}).json()
    client.post(f"/calls/{call['id']}/status", json={"status": "in_progress"})
    return client, call["id"], rec


def say(ws, text):
    ws.send_bytes(f"SAY:{text}".encode())


def until(ws, want):
    """Read messages until a JSON event matching `want` (a dict subset); return (events, audio bytes)."""
    events, audio = [], 0
    while True:
        msg = ws.receive()
        if msg.get("bytes") is not None:
            audio += len(msg["bytes"])
            continue
        assert "text" in msg, (msg, events, audio)
        event = json.loads(msg["text"])
        events.append(event)
        if all(event.get(k) == v for k, v in want.items()):
            return events, audio


def lines(events):
    return [(e["who"], e["text"]) for e in events if e["type"] == "line"]


def test_a_whole_call_from_hello_to_goodbye(phone):
    client, call_id, rec = phone
    rec["replies"] = [
        "જી. ₹1,00,000 બાકી છે. પેમેન્ટ ક્યારે આવશે?",
        "સારું. તો 10 નવેમ્બરે RTGS, બરાબર ને?",
        "સારું, આભાર રમેશભાઈ. આવજો. <END>",
    ]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        events, audio = until(ws, {"who": "agent"})
        assert lines(events) == [("agent", OPENING)] and audio > 0

        say(ws, "હા બોલો")
        events, _ = until(ws, {"text": "₹1,00,000 બાકી છે. પેમેન્ટ ક્યારે આવશે?"})
        # the acknowledgement alone (a bundled clip), then the rest of the reply in one piece
        assert lines(events) == [("customer", "હા બોલો"), ("agent", "જી."),
                                 ("agent", "₹1,00,000 બાકી છે. પેમેન્ટ ક્યારે આવશે?")]
        say(ws, "10 તારીખે RTGS કરી દઈશ")
        until(ws, {"text": "તો 10 નવેમ્બરે RTGS, બરાબર ને?"})
        say(ws, "હા")
        events, _ = until(ws, {"type": "end"})
        assert lines(events)[-1] == ("agent", "સારું, આભાર રમેશભાઈ. આવજો.")  # not split: one intonation

    call = client.get(f"/calls/{call_id}").json()
    assert call["status"] == "completed" and call["ended_at"]
    assert [t["who"] for t in call["transcript"]] == ["agent", "customer"] * 3 + ["agent"]
    assert call["transcript"][2]["text"] == "જી. ₹1,00,000 બાકી છે. પેમેન્ટ ક્યારે આવશે?"
    assert call["transcript"][-1]["text"] == "સારું, આભાર રમેશભાઈ. આવજો."
    # Gemini saw the whole conversation so far each time
    assert rec["histories"][1][-1] == {"who": "customer", "text": "10 તારીખે RTGS કરી દઈશ"}
    assert "રમેશભાઈ" in rec["keyterms"] and "મનીષભાઈ" in rec["keyterms"]


def test_the_opening_was_made_while_ringing(phone):
    _, _, rec = phone
    assert rec["tts"][0] == OPENING and set(live.FIXED_LINES) <= set(rec["tts"])  # warm-up on POST /calls


def test_customer_hello_is_answered_by_the_opening(phone, monkeypatch):
    client, call_id, rec = phone
    monkeypatch.setattr(live, "GREETING_WAIT", 1.0)
    rec["replies"] = ["આભાર. આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        say(ws, "હેલો")
        events, _ = until(ws, {"who": "agent"})
        assert lines(events) == [("customer", "હેલો"), ("agent", OPENING)]
        assert rec["histories"] == []  # the hello itself needs no Gemini reply
        say(ws, "હા, બોલો")
        until(ws, {"type": "end"})
    assert [t["who"] for t in client.get(f"/calls/{call_id}").json()["transcript"]] == ["customer", "agent"] * 2


def test_speech_over_the_agent_is_treated_as_echo(phone):
    client, call_id, rec = phone
    speech._save(speech.clip_key(OPENING), LOUD * 16000)  # the opening plays for a second
    rec["replies"] = ["આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "નમસ્તે રમેશભાઈ બોલો છો")  # the phone's speaker, picked up by its own mic
        say(ws, "")  # (nothing heard: ignored)
        time.sleep(1.1)
        say(ws, "હા બોલો")
        until(ws, {"type": "end"})
    assert rec["histories"][0][1:] == [{"who": "customer", "text": "હા બોલો"}]


def test_customer_hangs_up(phone):
    client, call_id, rec = phone
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        ws.send_text(json.dumps({"type": "hangup"}))
    call = client.get(f"/calls/{call_id}").json()
    assert call["status"] == "completed" and call["transcript"] == [{"who": "agent", "text": OPENING}]
    assert client.post(f"/calls/{call_id}/status", json={"status": "completed"}).status_code == 409


def test_silence_gets_a_hello_then_a_goodbye(phone, monkeypatch):
    client, call_id, _ = phone
    monkeypatch.setattr(live, "NO_REPLY", 0.2)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        events, _ = until(ws, {"type": "end"})
    assert [t for _, t in lines(events)] == [OPENING, live.HELLO, live.NO_ANSWER_BYE]
    assert client.get(f"/calls/{call_id}").json()["status"] == "completed"


def test_slow_reply_gets_a_filler_without_a_double_ack(phone, monkeypatch):
    client, call_id, rec = phone
    monkeypatch.setattr(live, "FILLER_AFTER", 0.05)
    rec["replies"] = [(0.4, "જી. 10 તારીખે બરાબર. આવજો. <END>")]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        time.sleep(0.2)  # the opening has finished playing: a filler only plays into silence
        say(ws, "10 તારીખે આપી દઈશ")
        events, audio = until(ws, {"type": "end"})
    said = [t for who, t in lines(events) if who == "agent"]
    assert said == ["10 તારીખે બરાબર. આવજો."] and audio > 0  # the filler replaced the reply's own "જી."


def test_more_speech_before_the_reply_restarts_it(phone):
    client, call_id, rec = phone
    rec["replies"] = [(0.5, "ખોટો જવાબ."), "આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા")
        say(ws, "15 તારીખે")
        events, _ = until(ws, {"type": "end"})
    assert ("agent", "ખોટો જવાબ.") not in lines(events)
    assert rec["histories"][-1][-1] == {"who": "customer", "text": "હા 15 તારીખે"}


def test_gemini_failure_is_covered_by_a_sorry(phone, monkeypatch):
    client, call_id, rec = phone

    async def broken(system, history, max_tokens=400):
        raise llm.LLMError("HTTP 500")
        yield

    monkeypatch.setattr(llm, "stream", broken)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")
        until(ws, {"text": live.SORRY})
        ws.send_text(json.dumps({"type": "hangup"}))


def test_only_an_answered_call_can_go_live(phone):
    client, call_id, _ = phone
    client.post(f"/calls/{call_id}/status", json={"status": "completed"})
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/calls/{call_id}/live") as ws:
            ws.receive()
    assert e.value.code == 4409
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/calls/999/live") as ws:
            ws.receive()
    assert e.value.code == 4404


# ---------- pieces ----------

def test_sentences_are_cut_from_the_token_stream():
    async def tokens():
        for t in ["હા, ₹50,", "000 મળી", " ગયા. હવે બાકી", " ક્યારે? આવજો.", " <END>"]:
            yield t

    async def collect():
        return [s async for s in live.sentences(tokens())]

    assert asyncio.run(collect()) == ["હા, ₹50,000 મળી ગયા.", "હવે બાકી ક્યારે?", "આવજો.", "<END>"]


def test_segments_keep_a_reply_in_one_piece():
    async def sents(*items):
        for s in items:
            yield s

    async def collect(*items):
        return [s async for s in live.segments(sents(*items))]

    # the acknowledgement alone, the rest together
    assert asyncio.run(collect("જી.", "₹50,000 મળી ગયા.", "બાકી ક્યારે?")) == ["જી.", "₹50,000 મળી ગયા. બાકી ક્યારે?"]
    # no acknowledgement: all one piece
    assert asyncio.run(collect("તો 10 તારીખે.", "બરાબર ને?")) == ["તો 10 તારીખે. બરાબર ને?"]
    # a long reply is split at a sentence end
    long = "ક" * 100 + "."
    assert asyncio.run(collect(long, long)) == [long, long]


def test_a_segment_starts_only_with_enough_audio_held_back(phone):
    """Timbre's small chunks are held until PREBUFFER is ready, so the phone never runs dry mid-word."""
    client, call_id, rec = phone

    async def trickle(text):  # 100 ms chunks, arriving a little slower than real time
        for _ in range(10):
            await asyncio.sleep(0.01)
            yield LOUD * 1600

    rec["replies"] = ["₹1,00,000 બાકી છે. આવજો. <END>"]
    sizes = []
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        gnani.synthesize_stream = trickle  # (restored by monkeypatch after the test)
        say(ws, "હા બોલો")
        while True:
            msg = ws.receive()
            if msg.get("bytes") is not None:
                sizes.append(len(msg["bytes"]))
            elif json.loads(msg["text"])["type"] == "end":
                break
    assert sizes[0] >= live.PREBUFFER * live.BYTES_PER_SECOND  # first send: 0.4 s at once
    assert sum(sizes) == 10 * 3200


def test_drop_ack():
    assert live.drop_ack("હા, 10 તારીખે બરાબર.") == "10 તારીખે બરાબર."
    assert live.drop_ack("જી.") == "જી."  # nothing left: keep it
    assert live.drop_ack("હાલ તો નહીં.") == "હાલ તો નહીં."


def test_live_stt_sends_exact_frames():
    class WS:
        def __init__(self):
            self.sent = []

        async def send(self, frame):
            self.sent.append(frame)

    async def go():
        ws = WS()
        stt = gnani.LiveSTT(ws)
        await stt.send(b"a" * 700)
        await stt.send(b"b" * 700)
        await stt.send(b"c" * 700)
        return ws.sent

    sent = asyncio.run(go())
    assert [len(f) for f in sent] == [1024, 1024] and sent[0] == b"a" * 700 + b"b" * 324


def test_live_headers_are_ascii(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "k")
    headers = gnani.live_headers(["રમેશભાઈ", "Genius"])
    assert all(v.isascii() for v in headers.values())
    assert json.loads(headers["keyterms"]) == ["રમેશભાઈ", "Genius"]
    assert headers["model"] == "prisma-v3.0" and headers["x-sample-rate"] == "16000"


def _gemini(monkeypatch, handler):
    """Route llm's httpx calls to `handler` (a MockTransport function)."""
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    real = llm.httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient",
                        lambda **kw: real(transport=llm.httpx.MockTransport(handler), **kw))


def _collect(gen):
    async def go():
        return [c async for c in gen]
    return asyncio.run(go())


SSE = 'data: {"candidates": [{"content": {"parts": [{"text": "%s"}]}}]}\n\n'


def test_a_stalled_gemini_reply_is_asked_again(monkeypatch):
    tried = []

    def handler(request):
        tried.append(request.url.path.split("/")[-1])
        if len(tried) == 1:
            raise llm.httpx.ReadTimeout("stalled", request=request)
        return llm.httpx.Response(200, text=SSE % "હા જી.")

    _gemini(monkeypatch, handler)
    assert _collect(llm.stream("sys", [])) == ["હા જી."]
    assert len(tried) == 2


def test_rate_limited_gemini_falls_back_then_gives_up(monkeypatch):
    tried = []

    def handler(request):
        tried.append(request.url.path.split("/")[-1].split(":")[0])
        return llm.httpx.Response(429, text="quota")

    _gemini(monkeypatch, handler)
    with pytest.raises(llm.LLMError, match="no reply after 3 tries"):
        _collect(llm.stream("sys", []))
    assert tried == [llm.model(), llm.model(), llm.fallback_model()]


class FakeGnaniWS:
    def __init__(self, first, closes_after=False):
        self.first, self.closes_after, self.closed = first, closes_after, False

    async def recv(self):
        return json.dumps(self.first)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.closes_after:
            from websockets.frames import Close
            raise gnani.websockets.ConnectionClosedError(Close(1008, "policy"), None)
        raise StopAsyncIteration

    async def close(self):
        self.closed = True


def _open(monkeypatch, ws):
    monkeypatch.setenv("GNANI_API_KEY", "k")
    monkeypatch.setattr(gnani, "_calls", {})

    async def connect(url, **kw):
        assert url == "wss://api.vachana.ai/stt/v3/stream" and kw["additional_headers"]["language_code"] == "gu-IN"
        return ws
    monkeypatch.setattr(gnani.websockets, "connect", connect)


def test_a_refused_live_stt_session_fails_fast(monkeypatch):
    ws = FakeGnaniWS({"type": "error", "message": "Invalid language_code"})
    _open(monkeypatch, ws)

    async def go():
        async with gnani.live_stt():
            pass

    with pytest.raises(gnani.GnaniError, match="Invalid language_code"):
        asyncio.run(go())
    assert ws.closed


def test_a_dropped_live_stt_session_just_ends_the_events(monkeypatch):
    _open(monkeypatch, FakeGnaniWS({"type": "connected", "config": {}}, closes_after=True))

    async def go():
        async with gnani.live_stt() as stt:
            return [e async for e in stt.events()]

    assert asyncio.run(go()) == []


def test_fixed_call_lines_ship_with_the_app():
    """Fillers and goodbyes play from bundled clips: instant, and no Timbre credits on a fresh server."""
    shipped = Path(speech.__file__).parent / "clips"  # (conftest hides it from the other tests)
    for text in live.FIXED_LINES:
        assert (shipped / f"{speech.clip_key(text)}.wav").exists(), text


def test_timbre_silence_is_trimmed_but_pauses_inside_are_kept():
    silence, word, click = bytes(640) * 30, bytes([0, 16]) * 320 * 10, bytes([0, 16]) * 320

    async def chunks():
        audio = silence + word + bytes(640) * 10 + word + silence + click + silence
        for i in range(0, len(audio), 1000):  # odd-sized chunks, like the network
            yield audio[i:i + 1000]

    async def collect():
        return b"".join([c async for c in speech.trimmed(chunks())])

    out = asyncio.run(collect())
    lead, inner, tail = speech.LEAD_KEEP, 640 * 10, speech.TAIL_KEEP
    assert len(out) == lead + len(word) + inner + len(word) + tail  # the click after the silence is gone
