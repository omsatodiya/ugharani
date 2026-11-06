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
GREETING = "હેલો રમેશભાઈ?"
INTRO = "હા નમસ્તે. હું કાવ્યા બોલું છું જીનિયસ પોલીપ્લાસ્ટમાંથી. કૉલ રેકોર્ડ થાય છે હં."
INTRO_NO = "નમસ્તે. હું કાવ્યા બોલું છું જીનિયસ પોલીપ્લાસ્ટમાંથી. કૉલ રેકોર્ડ થાય છે હં."  # after "કોણ?" etc.


class FakeSTT:
    """Frames starting with b'SAY:' become a speech_start + transcript, as if spoken; b'START' only
    the speech_start (VAD heard voice), b'TEXT:' only the transcript that ends it."""

    def __init__(self):
        self.queue = asyncio.Queue()
        self.audio = bytearray()

    async def send(self, pcm):
        if pcm.startswith(b"SAY:"):
            await self.queue.put({"type": "speech_start"})
            await self.queue.put({"type": "transcript", "text": pcm[4:].decode()})
        elif pcm.startswith(b"START"):
            await self.queue.put({"type": "speech_start"})
        elif pcm.startswith(b"TEXT:"):
            await self.queue.put({"type": "transcript", "text": pcm[5:].decode()})
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
        reply = rec["replies"].pop(0) if rec["replies"] else "સારું. આવજો. <END>"
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

    async def generate_json(system, history, schema):  # the notes after a call
        rec["notes_asked"].append(history[0]["text"])
        return rec["notes"]

    rec["notes_asked"] = []
    rec["notes"] = {"outcome": "promised", "summary": "10 તારીખે RTGS કરશે.", "promised_amount": 100000,
                    "promised_date": "2026-11-10", "payment_mode": "RTGS", "owner_action": None}
    monkeypatch.setattr(llm, "generate_json", generate_json)
    for name, value in {"GREETING_WAIT": 0.05, "GREETING_REPLY": 0.3, "FILLER_AFTER": 5, "NO_REPLY": 5, "AFTER_LAST_WORD": 0,
                        "ECHO_MARGIN": 0.5, "ECHO_DELAY": 0.05}.items():  # (fake audio is 0.1 s)
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
        assert lines(events) == [("agent", GREETING)] and audio > 0  # then she waits
        assert rec["histories"] == []

        say(ws, "હા બોલો")
        events, _ = until(ws, {"text": "પેમેન્ટ ક્યારે આવશે?"})
        # who she is (a bundled clip), then the reason Gemini wrote meanwhile; its "જી." is dropped
        assert lines(events) == [("customer", "હા બોલો"), ("agent", INTRO),
                                 ("agent", "₹1,00,000 બાકી છે."), ("agent", "પેમેન્ટ ક્યારે આવશે?")]
        time.sleep(0.7)  # (listens until she has finished)
        say(ws, "10 તારીખે RTGS કરી દઈશ")
        events, _ = until(ws, {"text": "તો 10 નવેમ્બરે RTGS, બરાબર ને?"})
        assert ("agent", "સારું.") in lines(events)  # (later replies keep their acknowledgement)
        time.sleep(0.7)
        say(ws, "હા")
        events, _ = until(ws, {"type": "end"})
        assert lines(events)[-2:] == [("agent", "સારું, આભાર રમેશભાઈ."), ("agent", "આવજો.")]

    call = client.get(f"/calls/{call_id}").json()
    assert call["status"] == "completed" and call["ended_at"]
    assert [t["who"] for t in call["transcript"]] == ["agent", "customer"] * 3 + ["agent"]
    assert call["transcript"][2]["text"] == f"{INTRO} ₹1,00,000 બાકી છે. પેમેન્ટ ક્યારે આવશે?"
    assert call["transcript"][-1]["text"] == "સારું, આભાર રમેશભાઈ. આવજો."
    # Gemini saw the whole conversation so far each time
    assert rec["histories"][1][-1] == {"who": "customer", "text": "10 તારીખે RTGS કરી દઈશ"}
    assert "રમેશભાઈ" in rec["keyterms"] and "મનીષભાઈ" in rec["keyterms"]


def test_the_opening_was_made_while_ringing(phone):
    _, _, rec = phone
    assert rec["tts"][:3] == [GREETING, INTRO, INTRO_NO]  # warm-up on POST /calls
    assert set(live.FIXED_LINES) <= set(rec["tts"])


def test_customer_hello_is_answered_by_the_greeting(phone, monkeypatch):
    client, call_id, rec = phone
    monkeypatch.setattr(live, "GREETING_WAIT", 1.0)
    rec["replies"] = ["આભાર. આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        say(ws, "હેલો")
        events, _ = until(ws, {"who": "agent"})
        assert lines(events) == [("customer", "હેલો"), ("agent", GREETING)]
        assert rec["histories"] == []  # the hello itself needs no Gemini reply
        say(ws, "હા, બોલો")
        events, _ = until(ws, {"type": "end"})
        assert ("agent", INTRO) in lines(events)
    assert [t["who"] for t in client.get(f"/calls/{call_id}").json()["transcript"]] == ["customer", "agent"] * 2


def test_who_is_it_gets_an_intro_without_ha(phone):
    client, call_id, rec = phone
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "કોણ બોલો?")
        events, _ = until(ws, {"type": "end"})
    assert ("agent", INTRO_NO) in lines(events)


def test_no_answer_to_the_greeting_gets_one_hello_then_the_intro(phone):
    client, call_id, rec = phone
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        events, _ = until(ws, {"type": "end"})
    said = [t for who, t in lines(events) if who == "agent"]
    assert said[:3] == [GREETING, live.HELLO_SHORT, INTRO_NO]


def test_speech_over_the_agent_is_treated_as_echo(phone):
    client, call_id, rec = phone
    speech._save(speech.clip_key(GREETING), LOUD * 16000)  # the greeting plays for a second
    rec["replies"] = ["આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હેલો રમેશભાઈ")  # the phone's speaker, picked up by its own mic
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
    assert call["status"] == "completed" and call["transcript"] == [{"who": "agent", "text": GREETING}]
    assert client.post(f"/calls/{call_id}/status", json={"status": "completed"}).status_code == 409


def test_silence_gets_a_hello_then_a_goodbye(phone, monkeypatch):
    client, call_id, rec = phone
    monkeypatch.setattr(live, "NO_REPLY", 0.2)
    rec["replies"] = ["₹1,00,000 બાકી છે, ક્યારે મોકલશો?"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        events, _ = until(ws, {"type": "end"})
    said = [t for _, t in lines(events)]
    assert said[:3] == [GREETING, live.HELLO_SHORT, INTRO_NO]
    assert said[-2:] == [live.HELLO, live.NO_ANSWER_BYE]
    assert client.get(f"/calls/{call_id}").json()["status"] == "completed"


def test_slow_reply_gets_a_filler_without_a_double_ack(phone, monkeypatch):
    client, call_id, rec = phone
    monkeypatch.setattr(live, "FILLER_AFTER", 0.05)
    rec["replies"] = ["₹1,00,000 બાકી છે.", (0.4, "જી. 10 તારીખે બરાબર. આવજો. <END>")]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")  # (the intro covers Gemini's first reply: no filler there)
        until(ws, {"text": "₹1,00,000 બાકી છે."})
        time.sleep(0.6)  # she has finished: a filler only plays into silence
        say(ws, "10 તારીખે આપી દઈશ")
        events, audio = until(ws, {"type": "end"})
    said = [t for who, t in lines(events) if who == "agent"]
    assert said == ["10 તારીખે બરાબર.", "આવજો."] and audio > 0  # the filler replaced the reply's own "જી."


def test_more_speech_before_the_reply_restarts_it(phone):
    client, call_id, rec = phone
    rec["replies"] = ["₹1,00,000 બાકી છે.", (0.5, "ખોટો જવાબ."), "આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")
        until(ws, {"text": "₹1,00,000 બાકી છે."})
        time.sleep(0.6)
        say(ws, "હા")
        say(ws, "15 તારીખે")  # ...a breath later, before she answered the "હા"
        events, _ = until(ws, {"type": "end"})
    assert ("agent", "ખોટો જવાબ.") not in lines(events)
    assert rec["histories"][-1][-1] == {"who": "customer", "text": "હા 15 તારીખે"}


def test_both_answers_to_the_greeting_are_heard(phone):
    client, call_id, rec = phone
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા")
        say(ws, "બોલો શું કામ છે")
        until(ws, {"type": "end"})
    assert rec["histories"][0][-1] == {"who": "customer", "text": "હા બોલો શું કામ છે"}


def test_gemini_failure_is_covered_by_a_sorry(phone, monkeypatch):
    client, call_id, rec = phone

    async def broken(system, history, max_tokens=400):
        raise llm.LLMError("HTTP 500")
        yield

    monkeypatch.setattr(llm, "stream", broken)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")
        until(ws, {"text": "તમારું ₹1,00,000 નું પેમેન્ટ બાકી છે, એ ક્યારે મોકલશો?"})  # after the intro
        time.sleep(0.6)
        say(ws, "10 તારીખે")
        until(ws, {"text": live.SORRY})  # later turns: sorry, say again
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

    # the acknowledgement alone, then the first sentence alone (it starts fast), then the rest together
    assert asyncio.run(collect("જી.", "₹50,000 મળી ગયા.", "બાકી ક્યારે?", "કહેજો.")) ==         ["જી.", "₹50,000 મળી ગયા.", "બાકી ક્યારે? કહેજો."]
    # no acknowledgement: all one piece
    assert asyncio.run(collect("તો 10 તારીખે.", "બરાબર ને?", "કહેજો.")) == ["તો 10 તારીખે.", "બરાબર ને? કહેજો."]
    # a long reply is split at a sentence end
    long = "ક" * 100 + "."
    assert asyncio.run(collect("જી.", "હા.", long, long)) == ["જી.", "હા.", long, long]


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
        until(ws, {"text": INTRO})  # (a cached clip: sent whole)
        while True:
            msg = ws.receive()
            if msg.get("bytes") is not None:
                sizes.append(len(msg["bytes"]))
            elif json.loads(msg["text"])["type"] == "end":
                break
    assert sizes[0] >= live.PREBUFFER * live.BYTES_PER_SECOND  # first send: 0.4 s at once
    assert sum(sizes) == 2 * 10 * 3200  # (two segments: the first sentence, then the rest)


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
    with pytest.raises(llm.LLMError, match="no reply: .*429.*429"):
        _collect(llm.stream("sys", []))
    assert tried == [llm.model(), llm.fallback_model()]  # the second is asked at once, not after a wait


def test_a_slow_model_is_overtaken_by_the_other(monkeypatch):
    """Hedging: the first model hasn't started after HEDGE_AFTER, so the other is asked too."""
    monkeypatch.setattr(llm, "HEDGE_AFTER", 0.1)
    tried = []

    async def handler(request):
        name = request.url.path.split("/")[-1].split(":")[0]
        tried.append(name)
        if name == llm.model():
            await asyncio.sleep(1.0)  # overloaded
            return llm.httpx.Response(200, text=SSE % "મોડું.")
        return llm.httpx.Response(200, text=SSE % "જી.")

    _gemini(monkeypatch, handler)
    t = time.monotonic()
    assert _collect(llm.stream("sys", [])) == ["જી."]
    assert tried == [llm.model(), llm.fallback_model()] and time.monotonic() - t < 0.8


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


# ---------- talked over ----------

LONG_LINE = "₹1,00,000 નું પેમેન્ટ બાકી છે, એ ક્યારે મોકલશો?"


def _long_reply(rec, seconds=3.0):
    """The agent's first reply: 'જી.' then a line that plays for `seconds` on the phone."""
    rec["speech_seconds"][LONG_LINE] = seconds
    rec["replies"].insert(0, f"જી. {LONG_LINE}")


def _start_long_reply(ws):
    until(ws, {"who": "agent"})  # the opening
    time.sleep(0.6)  # (finished playing)
    say(ws, "હા બોલો")
    until(ws, {"text": LONG_LINE})  # all its audio is sent; the phone plays it for the next few seconds
    time.sleep(live.ECHO_ONSET + 0.1)  # past the moment her own echo would start: now it's someone else


def test_talking_over_her_stops_her_and_gets_an_answer(phone):
    client, call_id, rec = phone
    rec["replies"] = ["અચ્છા. તો UTR નંબર મોકલી દેશો? <END>"]
    _long_reply(rec)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        _start_long_reply(ws)
        time.sleep(1.0)  # about a third of her line has played
        ws.send_bytes(b"START")
        until(ws, {"type": "duck"})  # her voice dips at once
        ws.send_bytes("TEXT:મેં તો ગયા અઠવાડિયે પેમેન્ટ કરી દીધું છે".encode())
        events, _ = until(ws, {"type": "clear"})  # the phone drops the rest of her line
        events, _ = until(ws, {"type": "end"})
        assert ("customer", "મેં તો ગયા અઠવાડિયે પેમેન્ટ કરી દીધું છે") in lines(events)
        assert ("agent", "અચ્છા.") in lines(events)

    # Gemini was told she got cut off, and what the customer actually heard
    agent_line = rec["histories"][1][-2]
    assert agent_line["who"] == "agent" and agent_line["text"].startswith(f"{INTRO} ₹1,00,000")
    assert agent_line["text"].endswith("…") and "મોકલશો?" not in agent_line["text"]
    assert rec["histories"][1][-1] == {"who": "customer", "text": "મેં તો ગયા અઠવાડિયે પેમેન્ટ કરી દીધું છે"}
    transcript = client.get(f"/calls/{call_id}").json()["transcript"]
    assert transcript[2]["text"].endswith("…") and transcript[3]["who"] == "customer"


def test_her_own_echo_does_not_stop_her(phone):
    client, call_id, rec = phone
    rec["replies"] = ["સારું, આભાર. આવજો. <END>"]
    _long_reply(rec, seconds=1.5)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        _start_long_reply(ws)
        ws.send_bytes(b"START")
        until(ws, {"type": "duck"})
        ws.send_bytes("TEXT:1,00,000 નું પેમેન્ટ બાકી છે એ ક્યારે મોકલશો".encode())  # her words, heard back
        events, _ = until(ws, {"type": "unduck"})
        assert all(e["type"] != "clear" for e in events)
        time.sleep(1.6)
        say(ws, "10 તારીખે")
        until(ws, {"type": "end"})
    assert len(rec["histories"]) == 2  # the echo got no reply
    assert rec["histories"][1][-2]["text"] == f"{INTRO} {LONG_LINE}"  # her line, whole


def test_listening_noises_do_not_stop_her(phone):
    client, call_id, rec = phone
    rec["replies"] = ["સારું. આવજો. <END>"]
    _long_reply(rec, seconds=1.5)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        _start_long_reply(ws)
        say(ws, "હા હા")
        events, _ = until(ws, {"type": "unduck"})
        assert all(e["type"] != "clear" for e in events)
        time.sleep(1.6)
        say(ws, "હા, 10 તારીખે")
        until(ws, {"type": "end"})
    assert len(rec["histories"]) == 2


def test_her_voice_comes_back_if_no_words_follow(phone, monkeypatch):
    client, call_id, rec = phone
    monkeypatch.setattr(live, "DUCK_MAX", 0.2)
    _long_reply(rec)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        _start_long_reply(ws)
        ws.send_bytes(b"START")  # a cough, a door: VAD fires, no words come
        until(ws, {"type": "duck"})
        until(ws, {"type": "unduck"})
        ws.send_text(json.dumps({"type": "hangup"}))


def test_similarity_and_listening_words():
    said = "જી. ₹1,20,000 નું પેમેન્ટ બાકી છે, એ ક્યારે મોકલશો?"
    assert live.similarity("1,20,000 નું પેમેન્ટ બાકી છે", said) > 0.9
    assert live.similarity("મેં તો ગયા અઠવાડિયે પેમેન્ટ કરી દીધું", said) < 0.5
    assert live.similarity("", said) == 0.0
    for noise in ["હા", "હા હા", "હા જી.", "हाँ", "ઓકે", "હં"]:
        assert live.is_backchannel(noise), noise
    for words in ["હા, 10 તારીખે", "ના", "હા બોલો શું કામ છે", ""]:
        assert not live.is_backchannel(words), words


def test_short_phrases_are_echo_only_if_she_said_them_in_that_order():
    said = "નમસ્તે, રમેશભાઈ બોલો છો? હું કાવ્યા, જીનિયસ પોલીપ્લાસ્ટ, ગોંડલથી બોલું છું."
    assert not live.echoes("હા બોલો", said)  # shares letters with "...બોલો છો?", but isn't hers
    assert live.echoes("બોલો છો", said)
    assert live.echoes("જીનિયસ પોલીપ્લાસ્ટ ગોંડલથી બોલું છું", said)
    assert not live.echoes("હા, બોલો ને શું કામ છે", said)


def test_the_intro_is_never_cut_short(phone):
    """It carries the "this call is recorded" notice; words said over it are answered after it."""
    client, call_id, rec = phone
    speech._save(speech.clip_key(INTRO), LOUD * 32000)  # the intro plays for two seconds
    rec["replies"] = ["₹1,00,000 બાકી છે.", "સારું. આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા")
        until(ws, {"text": INTRO})
        time.sleep(live.ECHO_ONSET + 0.1)
        ws.send_bytes(b"START")
        ws.send_bytes("TEXT:હા બોલો, શું કામ છે".encode())
        events, _ = until(ws, {"type": "end"})
    kinds = [e["type"] for e in events]
    assert "clear" not in kinds and "duck" not in kinds
    assert ("customer", "હા બોલો, શું કામ છે") in lines(events)
    transcript = client.get(f"/calls/{call_id}").json()["transcript"]
    assert transcript[2]["text"].startswith(INTRO) and "…" not in transcript[2]["text"]  # whole


def test_her_filler_coming_back_is_not_taken_for_the_customer(phone, monkeypatch):
    """Found on a real call: the filler leaked into the mic, was heard as the customer saying
    'જી', restarted the reply, which played another filler... and she never answered."""
    client, call_id, rec = phone
    monkeypatch.setattr(live, "FILLER_AFTER", 0.05)
    monkeypatch.setattr(live, "FILLERS", ["જી,"])
    rec["replies"] = ["₹1,00,000 બાકી છે.", (0.6, "સારું. આવજો. <END>")]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")
        until(ws, {"text": "₹1,00,000 બાકી છે."})
        time.sleep(0.6)  # she has finished; the next reply is slow, so a filler plays
        say(ws, "10 તારીખે આપીશ")
        while ws.receive().get("bytes") is None:  # the filler's audio
            pass
        say(ws, "જી")  # ...heard back through the mic
        events, _ = until(ws, {"type": "end"})
    assert len(rec["histories"]) == 2  # the second reply was not restarted
    assert [t["who"] for t in client.get(f"/calls/{call_id}").json()["transcript"]] == \
        ["agent", "customer"] * 2 + ["agent"]


def test_ha_said_as_she_finishes_a_question_is_its_answer(phone):
    client, call_id, rec = phone
    question = "તો 10 તારીખે ₹1,00,000 RTGS, બરાબર ને?"
    rec["speech_seconds"][question] = 1.2
    rec["replies"] = [f"જી. {question}", "સારું, આભાર. આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        time.sleep(0.6)
        say(ws, "10 તારીખે કરી દઈશ")
        until(ws, {"text": question})
        time.sleep(0.7)  # past her echo's onset, ~0.5 s of the question still to play
        say(ws, "હા")
        events, _ = until(ws, {"type": "end"})
    assert "clear" not in [e["type"] for e in events]  # no need to stop her
    assert rec["histories"][-1][-1] == {"who": "customer", "text": "હા"}  # answered, not ignored


def test_long_pauses_inside_her_speech_are_shortened():
    """Timbre pauses ~0.6 s at every full stop; a person on the phone pauses ~0.25 s."""
    word = bytes([0, 16]) * 320 * 10  # 200 ms of speech

    async def chunks():
        yield word + bytes(640) * 30 + word  # a 600 ms pause between two words

    async def collect():
        return b"".join([c async for c in speech.trimmed(chunks())])

    out = asyncio.run(collect())
    assert len(out) == len(word) + speech.MAX_PAUSE + len(word)  # (no silence before the first word)


def test_words_during_a_slow_first_reply_keep_the_history_in_order(phone, monkeypatch):
    """Found on a real call: Gemini stalled after the intro, the customer spoke again, and the intro
    was written into the history after their words, so Gemini got a conversation ending on her
    turn and refused it (HTTP 400)."""
    client, call_id, rec = phone
    monkeypatch.setattr(live, "LEAD_IN_GRACE", 5.0)  # (this test is about the order, not the timer)
    rec["replies"] = [(1.0, "ખોટો જવાબ."), "સારું. આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")
        until(ws, {"text": INTRO})
        time.sleep(0.3)
        say(ws, "10 તારીખે RTGS કરી દઈશ")  # while the first reply is still being written
        events, _ = until(ws, {"type": "end"})
    assert [h["who"] for h in rec["histories"][-1]] == ["agent", "customer", "agent", "customer"]
    assert rec["histories"][-1][2]["text"] == INTRO and ("agent", "ખોટો જવાબ.") not in lines(events)


def test_a_stalled_gemini_after_the_intro_gets_the_fixed_ask(phone, monkeypatch):
    client, call_id, rec = phone
    monkeypatch.setattr(live, "LEAD_IN_GRACE", 0.2)
    rec["replies"] = [(3.0, "ખૂબ મોડો જવાબ.")]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")
        events, _ = until(ws, {"text": "તમારું ₹1,00,000 નું પેમેન્ટ બાકી છે, એ ક્યારે મોકલશો?"})
        ws.send_text(json.dumps({"type": "hangup"}))
    assert ("agent", "ખૂબ મોડો જવાબ.") not in lines(events)


def test_timbre_requests_never_overlap(monkeypatch):
    """Timbre allows one active request per key (a real call got 429 when the next sentence was
    fetched while the current one was still streaming)."""
    active, most = 0, 0

    async def one_request(text, voice, speed):
        nonlocal active, most
        active += 1
        most = max(most, active)
        await asyncio.sleep(0.05)
        yield b"\x00\x01"
        active -= 1

    monkeypatch.setattr(gnani, "_synthesize_stream", one_request)

    async def go():
        async def say(t):
            return [c async for c in gnani.synthesize_stream(t)]
        await asyncio.gather(say("a"), say("b"), say("c"))

    asyncio.run(go())
    assert most == 1


def test_the_model_that_answered_last_goes_first(monkeypatch):
    monkeypatch.setattr(llm, "HEDGE_AFTER", 0.05)
    monkeypatch.setattr(llm, "_last_winner", None)
    tried = []

    async def handler(request):
        name = request.url.path.split("/")[-1].split(":")[0]
        tried.append(name)
        if name == llm.model():
            await asyncio.sleep(0.5)  # flash-lite overloaded today
        return llm.httpx.Response(200, text=SSE % "જી.")

    _gemini(monkeypatch, handler)
    _collect(llm.stream("sys", []))
    tried.clear()
    _collect(llm.stream("sys", []))
    assert tried == [llm.fallback_model()]  # asked first, answered at once: no hedge needed


# ---------- paused when talked over (our own speech detector) ----------

FRAME = 1024  # bytes per message from the phone page: 32 ms


def talk(ws, seconds, level=LOUD):
    """The customer's voice reaching the mic (loud PCM), as the phone page sends it."""
    for _ in range(round(seconds * 16000 * 2 / FRAME)):
        ws.send_bytes(level * (FRAME // 2))


def hush(ws, seconds):
    talk(ws, seconds, level=b"\0\0")


def test_talked_over_she_pauses_at_once_then_stops_for_real_words(phone):
    client, call_id, rec = phone
    rec["replies"] = ["અચ્છા. તો UTR નંબર મોકલી દેશો? <END>"]
    _long_reply(rec)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        _start_long_reply(ws)
        time.sleep(0.4)
        talk(ws, 0.3)  # ~0.25 s of voice is enough
        events, _ = until(ws, {"type": "pause"})
        ws.send_bytes(b"START")
        talk(ws, 1.0)  # (still talking: stays paused, whatever the time)
        hush(ws, 0.4)
        ws.send_bytes("TEXT:મેં તો ગયા અઠવાડિયે પેમેન્ટ કરી દીધું છે".encode())
        events, _ = until(ws, {"type": "clear"})
        assert "resume" not in [e["type"] for e in events]
        events, _ = until(ws, {"type": "end"})
        assert ("agent", "અચ્છા.") in lines(events)
    agent_line = rec["histories"][1][-2]["text"]
    assert agent_line.endswith("…") and "મોકલશો?" not in agent_line  # cut where it paused


def test_a_cough_pauses_her_briefly_then_she_goes_on(phone):
    client, call_id, rec = phone
    rec["replies"] = ["સારું. આવજો. <END>"]
    _long_reply(rec, seconds=2.0)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        _start_long_reply(ws)
        talk(ws, 0.3)  # a cough: Gnani hears no speech
        until(ws, {"type": "pause"})
        t = time.monotonic()
        hush(ws, 0.4)
        events, _ = until(ws, {"type": "resume"})
        assert time.monotonic() - t < live.RESUME_AFTER + 0.6
        assert "clear" not in [e["type"] for e in events]
        time.sleep(2.2)  # (the rest of her line, played later by the pause's length)
        say(ws, "હા, 10 તારીખે")
        until(ws, {"type": "end"})
    assert rec["histories"][1][-2]["text"] == f"{INTRO} {LONG_LINE}"  # said in full, no "…"


def test_listening_noise_or_her_echo_resumes_her(phone):
    client, call_id, rec = phone
    rec["replies"] = ["સારું. આવજો. <END>"]
    _long_reply(rec, seconds=3.0)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        _start_long_reply(ws)
        talk(ws, 0.3)
        until(ws, {"type": "pause"})
        say(ws, "હા હા")
        events, _ = until(ws, {"type": "resume"})
        assert "clear" not in [e["type"] for e in events]
        hush(ws, 1.0)  # (they stopped)
        time.sleep(live.ECHO_ONSET + 0.1)
        talk(ws, 0.3)
        until(ws, {"type": "pause"})
        say(ws, "1,00,000 નું પેમેન્ટ બાકી છે")  # her own words coming back
        events, _ = until(ws, {"type": "resume"})
        assert "clear" not in [e["type"] for e in events]
        ws.send_text(json.dumps({"type": "hangup"}))
    assert len(rec["histories"]) == 1  # neither got a reply


def test_no_pause_during_the_intro_or_as_her_echo_starts(phone):
    client, call_id, rec = phone
    speech._save(speech.clip_key(INTRO), LOUD * 32000)  # the intro plays for two seconds
    rec["replies"] = ["₹1,00,000 બાકી છે.", "સારું. આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા")
        until(ws, {"text": INTRO})
        time.sleep(live.ECHO_ONSET + 0.1)
        talk(ws, 0.5)  # over the recording notice
        hush(ws, 0.4)
        say(ws, "હા બોલો")
        events, _ = until(ws, {"type": "end"})
    assert {"pause", "clear"}.isdisjoint(e["type"] for e in events)


def test_talking_on_and_on_stops_her(phone, monkeypatch):
    client, call_id, rec = phone
    monkeypatch.setattr(live, "PAUSE_MAX", 0.3)
    _long_reply(rec, seconds=3.0)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        _start_long_reply(ws)
        talk(ws, 0.3)
        until(ws, {"type": "pause"})
        for _ in range(8):  # still talking past PAUSE_MAX (no words from Gnani yet): she stops
            talk(ws, 0.1)
            time.sleep(0.1)
        until(ws, {"type": "clear"})
        ws.send_text(json.dumps({"type": "hangup"}))
    assert client.get(f"/calls/{call_id}").json()["transcript"][-1]["text"].endswith("…")


def test_time_up_while_paused_says_goodbye(phone, monkeypatch):
    client, call_id, rec = phone
    _long_reply(rec, seconds=3.0)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        _start_long_reply(ws)
        talk(ws, 0.3)
        until(ws, {"type": "pause"})
        monkeypatch.setattr(live, "MAX_CALL", 0.0)
        events, _ = until(ws, {"type": "end"})
        assert "resume" in [e["type"] for e in events]  # (she finishes, then the goodbye)
        assert lines(events)[-1][1] == live.time_up_bye({"owner_name": "શેઠ"})


# ---------- the speech detector itself ----------

def _pcm(level, seconds):
    return (int(level).to_bytes(2, "little", signed=True)) * int(16000 * seconds)


def test_voice_starts_after_a_quarter_second_and_stops_after_quiet():
    from ugharani import vad
    v = vad.Voice()
    assert v.feed(_pcm(0, 1.0), echo=None) == []
    assert v.feed(_pcm(3000, 0.1), echo=None) == []  # a click, a short "હં"
    assert v.feed(_pcm(0, 0.5), echo=None) == []
    assert v.feed(_pcm(3000, 0.25), echo=None) == ["start"]
    assert v.feed(_pcm(0, 0.2), echo=None) == []  # a gap between words
    assert v.feed(_pcm(3000, 0.5), echo=None) == []
    assert v.feed(_pcm(0, 0.35), echo=None) == ["stop"]


def test_voice_ignores_her_echo_and_steady_noise():
    from ugharani import vad
    v = vad.Voice()
    assert v.feed(_pcm(1200, 0.5), echo=0.0) == []  # her voice leaking back as she starts: learned
    assert v.feed(_pcm(1500, 1.0), echo=1.0) == []  # a bit louder echo: still not speech
    assert v.feed(_pcm(5000, 0.3), echo=2.0) == ["start"]  # someone much louder than the echo
    n = vad.Voice()
    assert n.feed(_pcm(300, 1.0), echo=None) == []  # hiss below speech level
    assert n.feed(_pcm(0, 0.1) + _pcm(700, 30), echo=None).count("start") <= 1


def test_words_begun_as_the_intro_ends_still_stop_her_reply(phone):
    """Found by the browser check: they started talking just as the intro ended; she paused (the
    reply had begun), but their words counted as 'said over the intro', so she went on."""
    client, call_id, rec = phone
    rec["replies"] = ["અચ્છા. UTR મોકલી દેશો? <END>"]
    _long_reply(rec)
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        time.sleep(0.6)
        say(ws, "હા બોલો")
        until(ws, {"text": INTRO})
        ws.send_bytes(b"START")  # (Gnani: speech starts while the intro is still playing)
        until(ws, {"text": LONG_LINE})
        time.sleep(live.ECHO_ONSET + 0.1)
        talk(ws, 0.3)
        until(ws, {"type": "pause"})
        ws.send_bytes("TEXT:મેં તો પેમેન્ટ કરી દીધું છે".encode())
        t = time.monotonic()
        events, _ = until(ws, {"type": "clear"})
        assert time.monotonic() - t < 0.5 and "resume" not in [e["type"] for e in events]
        until(ws, {"type": "end"})


# ---------- the owner's limits, and holding the line ----------

def test_a_sentence_past_the_owners_limits_is_never_said(phone):
    client, call_id, rec = phone
    rec["replies"] = ["જી. ₹1,00,000 બાકી છે, ક્યારે આવશે?",
                      "અચ્છા. તો 2% ડિસ્કાઉન્ટ આપી દઈએ. 30 દિવસમાં આપી દેજો.", "સારું. આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")
        until(ws, {"text": "₹1,00,000 બાકી છે, ક્યારે આવશે?"})
        time.sleep(0.6)
        say(ws, "થોડું ડિસ્કાઉન્ટ આપો તો એક મહિનામાં આપી દઉં")
        events, _ = until(ws, {"type": "end"})
    said = [t for who, t in lines(events) if who == "agent"]
    assert "એ બાબતે હું શેઠને વાત કરી દઉં છું, એ તમને ફોન કરશે." in said
    assert not any("ડિસ્કાઉન્ટ" in t or "30 દિવસ" in t for t in said)
    call = client.get(f"/calls/{call_id}").json()
    assert len(call["flags"]) == 1 and "discount" in call["flags"][0]  # the owner is told


def test_ek_minute_gets_an_instant_ok_and_a_long_wait(phone, monkeypatch):
    client, call_id, rec = phone
    monkeypatch.setattr(live, "NO_REPLY", 0.3)
    monkeypatch.setattr(live, "HOLD_WAIT", 1.5)
    rec["replies"] = ["જી. ₹1,00,000 બાકી છે, ક્યારે આવશે?", "સારું. આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")
        until(ws, {"text": "₹1,00,000 બાકી છે, ક્યારે આવશે?"})
        time.sleep(0.6)
        say(ws, "એક મિનિટ, હું બિલ જોઈ લઉં")
        until(ws, {"text": "હા જી, વાંધો નહીં."})
        t = time.monotonic()
        until(ws, {"text": live.HELLO})  # only after the hold wait, not the usual silence
        assert time.monotonic() - t > 1.4
        say(ws, "હા, શુક્રવારે આપી દઈશ")
        until(ws, {"type": "end"})
    assert len(rec["histories"]) == 2  # the hold itself didn't go to Gemini


def test_asks_to_hold():
    for text in ["એક મિનિટ", "એક મિનીટ હં", "હોલ્ડ કરો", "ઊભા રહો", "एक मिनट", "એક મિનિટ, હું બિલ જોઈ લઉં"]:
        assert live.asks_to_hold(text), text
    for text in ["એક મહિનામાં આપીશ", "2 મિનિટ પહેલાં જ મોકલ્યા, એક મિનિટ પણ મોડું નહીં થાય એની ગેરંટી આપું છું", "ના"]:
        assert not live.asks_to_hold(text), text


def test_an_overloaded_model_falls_back_for_the_notes_too(monkeypatch):
    tried = []

    def handler(request):
        name = request.url.path.split("/")[-1].split(":")[0]
        tried.append(name)
        if name == llm.model():
            return llm.httpx.Response(503, text="high demand")
        return llm.httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    _gemini(monkeypatch, handler)
    assert asyncio.run(llm.generate("sys", [])) == "ok"
    assert tried == [llm.model(), llm.fallback_model()]



def _saved(client, call_id, key, seconds=3.0):
    """The call as saved, once `key` is filled in (the notes are written just after the call)."""
    deadline = time.monotonic() + seconds
    while True:
        call = client.get(f"/calls/{call_id}").json()
        if call.get(key) or time.monotonic() > deadline:
            return call
        time.sleep(0.05)


def test_the_notes_are_written_after_the_call(phone):
    client, call_id, rec = phone
    rec["notes"] = {**rec["notes"], "owner_action": "WhatsApp પર સ્ટેટમેન્ટ મોકલવું"}
    rec["replies"] = ["જી. ₹1,00,000 બાકી છે, ક્યારે આવશે?", "સારું, આભાર. આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")
        until(ws, {"text": "₹1,00,000 બાકી છે, ક્યારે આવશે?"})
        time.sleep(0.6)
        say(ws, "10 તારીખે RTGS, સ્ટેટમેન્ટ મોકલજો")
        until(ws, {"type": "end"})
    call = _saved(client, call_id, "outcome")
    assert call["outcome"] == "promised" and call["promised_date"] == "2026-11-10"
    assert call["owner_action"] == "WhatsApp પર સ્ટેટમેન્ટ મોકલવું" and call["payment_mode"] == "RTGS"
    assert call["status"] == "completed" and len(call["transcript"]) == 5  # (kept as said)
    assert "Customer: 10 તારીખે RTGS, સ્ટેટમેન્ટ મોકલજો" in rec["notes_asked"][0]


def test_no_notes_when_nobody_answered_and_a_failure_keeps_the_call(phone, monkeypatch):
    client, call_id, rec = phone
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:
        until(ws, {"type": "end"})  # silence throughout
    assert rec["notes_asked"] == [] and client.get(f"/calls/{call_id}").json()["outcome"] is None

    async def broken(*a):
        raise llm.LLMError("503")

    monkeypatch.setattr(llm, "generate_json", broken)
    call = client.post("/calls", json={"customer": "રમેશભાઈ"}).json()
    client.post(f"/calls/{call['id']}/status", json={"status": "in_progress"})
    with client.websocket_connect(f"/calls/{call['id']}/live") as ws:
        until(ws, {"who": "agent"})
        say(ws, "હા બોલો")
        until(ws, {"type": "end"})
    time.sleep(0.3)
    saved = client.get(f"/calls/{call['id']}").json()
    assert saved["status"] == "completed" and saved["transcript"] and saved["outcome"] is None


def test_the_public_demo_gets_a_few_calls_a_day_the_owner_always(phone, monkeypatch):
    client, call_id, rec = phone
    monkeypatch.setenv("LIVE_CALLS_PER_DAY", "1")
    monkeypatch.setenv("DEMO_KEY", "owner-secret")
    rec["replies"] = ["સારું. આવજો. <END>"]
    with client.websocket_connect(f"/calls/{call_id}/live") as ws:  # the day's one public call
        until(ws, {"type": "end"})
    assert client.get("/calls/hours").json()["demo_left"] == 0
    refused = client.post("/calls", json={"customer": "રમેશભાઈ"})
    assert refused.status_code == 429 and "used up" in refused.json()["detail"]

    owner = client.post("/calls", params={"k": "owner-secret"}, json={"customer": "રમેશભાઈ"}).json()
    client.post(f"/calls/{owner['id']}/status", json={"status": "in_progress"})
    with client.websocket_connect(f"/calls/{owner['id']}/live?k=owner-secret") as ws:
        until(ws, {"type": "end"})  # never refused
    assert client.get("/calls/hours", params={"k": "owner-secret"}).json()["demo_left"] is None

    stranger = client.post("/calls", params={"k": "owner-secret"}, json={"customer": "રમેશભાઈ"}).json()
    client.post(f"/calls/{stranger['id']}/status", json={"status": "in_progress"})
    with pytest.raises(WebSocketDisconnect) as closed:  # a ringing call answered without the key
        with client.websocket_connect(f"/calls/{stranger['id']}/live") as ws:
            ws.receive()
    assert closed.value.code == 4429
