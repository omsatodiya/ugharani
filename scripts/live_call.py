"""A real end-to-end call without a microphone: this script is the customer's phone.

    uv run uvicorn ugharani.main:app                     # the server, with real Gnani + Gemini keys
    uv run python scripts/live_call.py [scenario] [customer]

Scenarios: promise (default), interrupt (cuts in mid-reply, with the agent's voice leaking back
into the mic), hindi (the customer speaks Hindi). ECHO=0.3 adds the leak to any scenario.

The customer's lines are spoken by a second Timbre voice (made once, cached in out/customer_voice),
streamed to /calls/{id}/live at real-time pace like the phone page does. Prints the conversation,
interruptions and reply delays; saves the call as out/live_call.wav.

Costs Gnani credits: one live STT session, plus Timbre for any agent sentence not cached yet.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import wave
from pathlib import Path

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from ugharani import gnani  # noqa: E402

SERVER = os.getenv("SERVER", "http://localhost:8000")
CUSTOMER_VOICE = os.getenv("CUSTOMER_VOICE", "Avinash")

# Each line: (text, language, when). when=None: after the agent finishes and a short pause;
# when=1.5: 1.5 s into the agent's current reply, talking over her.
SCENARIOS = {
    "promise": {"echo": 0.0, "lines": [
        ("હા, બોલો.", "gu-IN", None),
        ("હા, ખબર છે. 10 તારીખે RTGS કરી દઈશ.", "gu-IN", None),
        ("હા, બરાબર.", "gu-IN", None),
    ]},
    "interrupt": {"echo": 0.3, "lines": [
        ("હા, બોલો.", "gu-IN", None),
        ("અરે, મેં તો ગયા અઠવાડિયે જ પેમેન્ટ કરી દીધું છે.", "gu-IN", 1.5),
        ("UTR હું સાંજે મોકલી દઈશ.", "gu-IN", None),
        ("હા, બરાબર.", "gu-IN", None),
    ]},
    "hindi": {"echo": 0.0, "lines": [
        ("हाँ, बोलिए।", "hi-IN", None),
        ("अभी थोड़ा टाइट चल रहा है। अगले सोमवार को पचास हज़ार भेज दूँगा।", "hi-IN", None),
        ("बाकी का महीने के आखिर तक कर दूँगा।", "hi-IN", 1.5),  # cuts in while she confirms
        ("हाँ, ठीक है।", "hi-IN", None),
        ("हाँ जी, ठीक है।", "hi-IN", None),
    ]},
}
RATE = 16000
FRAME = 1024
FRAME_SECONDS = FRAME / 2 / RATE  # 32 ms
ECHO_DELAY = 0.15  # the agent's voice reaches the mic this late (speaker, room, device buffers)
VOICE_DIR = Path("out/customer_voice")


async def customer_audio(text: str, language: str) -> bytes:
    """The line in the customer's voice, as raw PCM (cached: costs Timbre credits once)."""
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(text.encode()).hexdigest()[:12]
    suffix = "" if language == "gu-IN" else f"-{language}"  # (Gujarati lines cached before this)
    path = VOICE_DIR / f"{CUSTOMER_VOICE}-{key}{suffix}.pcm"
    if not path.exists():
        os.environ["TTS_VOICE"] = CUSTOMER_VOICE
        os.environ["LANGUAGE"] = language
        path.write_bytes(b"".join([c async for c in gnani.synthesize_stream(text)]))
    return path.read_bytes()


def at(t: float) -> int:
    return max(0, int(t * RATE)) * 2


def place(track: bytearray, pcm: bytes, t: float) -> None:
    """Add `pcm` into `track` at time t (two voices can overlap)."""
    i = at(t)
    if len(track) < i + len(pcm):
        track.extend(bytes(i + len(pcm) - len(track)))
    a = memoryview(track)[i:i + len(pcm)].cast("h")
    b = memoryview(pcm).cast("h")
    for k in range(len(b)):
        a[k] = max(-32768, min(32767, a[k] + b[k]))


def scaled(pcm: bytes, gain: float) -> bytes:
    samples = memoryview(pcm).cast("h")
    return b"".join(int(s * gain).to_bytes(2, "little", signed=True) for s in samples)


async def main(scenario: str, customer: str) -> None:
    plan = SCENARIOS[scenario]
    echo = float(os.getenv("ECHO", plan["echo"]))
    lines = plan["lines"]
    voices = [await customer_audio(text, lang) for text, lang, _ in lines]
    async with httpx.AsyncClient(base_url=SERVER, timeout=30) as http:
        call = (await http.post("/calls", json={"customer": customer})).json()
        print(f"[{scenario}] calling {customer} (call {call['id']}), echo leak {echo}; "
              "answering in 3 s while the opening warms up")
        await asyncio.sleep(3)
        await http.post(f"/calls/{call['id']}/status", json={"status": "in_progress"})

    ws_url = SERVER.replace("http", "ws", 1) + f"/calls/{call['id']}/live"
    start = time.monotonic()
    agent = bytearray()     # the agent's voice as the phone plays it
    customer_track = bytearray()
    agent_until = 0.0       # when the agent's audio received so far finishes playing
    reply_start = 0.0       # when her current stretch of speech started playing
    ducked = False
    turn_ended_at: float | None = None
    delays: list[float] = []
    events: list[str] = []
    said = 0
    done = asyncio.Event()

    def clock() -> float:
        return time.monotonic() - start

    async with websockets.connect(ws_url, max_size=2**22) as ws:
        async def receive():
            nonlocal agent_until, reply_start, turn_ended_at, ducked
            async for msg in ws:
                now = clock()
                if isinstance(msg, bytes):
                    if turn_ended_at is not None:
                        delays.append(now - turn_ended_at)
                        print(f"      (reply started {now - turn_ended_at:.1f}s after the customer stopped)")
                        turn_ended_at = None
                    begin = max(now, agent_until)
                    if begin > agent_until + 0.3:
                        reply_start = begin  # she starts talking again after a pause
                    place(agent, msg, begin)
                    agent_until = begin + len(msg) / 2 / RATE
                    continue
                event = json.loads(msg)
                kind = event["type"]
                if kind == "line":
                    print(f"{now:5.1f}s {'AGENT   ' if event['who'] == 'agent' else 'CUSTOMER'} {event['text']}")
                    continue
                events.append(kind)
                print(f"{now:5.1f}s   [{kind}]")
                if kind == "duck":
                    ducked = True
                elif kind == "unduck":
                    ducked = False
                elif kind == "clear":  # the phone drops what she hasn't said yet
                    del agent[at(now):]
                    agent_until, ducked = now, False
                elif kind == "end":
                    done.set()
                    return

        async def send():
            """Real-time frames: the customer's voice when they talk, plus her voice leaking back."""
            nonlocal said, turn_ended_at
            queue = bytearray()
            talking = False
            next_frame = time.monotonic()
            while not done.is_set():
                now = clock()
                if not queue and said < len(lines) and agent_until:
                    when = lines[said][2]
                    talking_over = when is not None and now < agent_until and now - reply_start >= when
                    after_her = when is None and now > agent_until + 0.7 and turn_ended_at is None
                    if talking_over or after_her:
                        if talking_over:
                            print(f"{now:5.1f}s   (customer talks over her)")
                        queue += voices[said]
                        place(customer_track, voices[said], now)
                        said += 1
                        talking, turn_ended_at = True, None
                frame = bytes(queue[:FRAME])
                del queue[:FRAME]
                frame += bytes(FRAME - len(frame))
                if echo:
                    leak = bytes(agent[at(now - ECHO_DELAY):at(now - ECHO_DELAY) + FRAME])
                    if leak:
                        leak += bytes(FRAME - len(leak))
                        mixed = bytearray(frame)
                        place(mixed, scaled(leak, echo * (0.25 if ducked else 1.0)), 0)
                        frame = bytes(mixed)
                await ws.send(frame)
                if talking and not queue:  # the line has been said: the customer just stopped
                    talking = False
                    turn_ended_at = clock()
                next_frame += FRAME_SECONDS
                await asyncio.sleep(max(0.0, next_frame - time.monotonic()))
                if clock() > 150:
                    print("giving up after 2.5 minutes")
                    done.set()

        receiver = asyncio.create_task(receive())
        await send()
        receiver.cancel()

    mix = bytearray(agent)
    place(mix, bytes(customer_track), 0)
    out = Path("out/live_call.wav")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(mix))
    async with httpx.AsyncClient(base_url=SERVER) as http:
        for _ in range(20):  # the server saves the call once its side has closed
            saved = (await http.get(f"/calls/{call['id']}")).json()
            if saved["status"] != "in_progress":
                break
            await asyncio.sleep(0.5)
    print(f"\nsaved call: {saved['status']}, {len(saved['transcript'])} turns; recording: {out}")
    for t in saved["transcript"]:
        print(f"  {t['who']:8s} {t['text']}")
    print("events: " + (", ".join(events) or "none"))
    if delays:
        print("reply delays (customer stops -> agent audio): " + ", ".join(f"{d:.1f}s" for d in delays))


if __name__ == "__main__":
    args = sys.argv[1:]
    scenario = args.pop(0) if args and args[0] in SCENARIOS else "promise"
    asyncio.run(main(scenario, args[0] if args else "રમેશભાઈ"))
