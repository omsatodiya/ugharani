"""A real end-to-end call without a microphone: this script is the customer's phone.

    uv run uvicorn ugharani.main:app            # the server, with real Gnani + Gemini keys
    uv run python scripts/live_call.py [customer]

The customer's lines are spoken by a second Timbre voice (made once, cached in out/customer_voice),
streamed to /calls/{id}/live at real-time pace like the phone page does. Prints the conversation and
how long each reply took; saves the call as out/live_call.wav.

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
LINES = [
    "હા, બોલો.",
    "હા, ખબર છે. 10 તારીખે RTGS કરી દઈશ.",
    "હા, બરાબર.",
]
RATE = 16000
FRAME = 1024
FRAME_SECONDS = FRAME / 2 / RATE  # 32 ms
VOICE_DIR = Path("out/customer_voice")


async def customer_audio(text: str) -> bytes:
    """The line in the customer's voice, as raw PCM (cached: costs Timbre credits once)."""
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    path = VOICE_DIR / f"{CUSTOMER_VOICE}-{hashlib.sha256(text.encode()).hexdigest()[:12]}.pcm"
    if not path.exists():
        os.environ["TTS_VOICE"] = CUSTOMER_VOICE
        path.write_bytes(b"".join([c async for c in gnani.synthesize_stream(text)]))
    return path.read_bytes()


async def main(customer: str) -> None:
    voices = [await customer_audio(t) for t in LINES]
    async with httpx.AsyncClient(base_url=SERVER, timeout=30) as http:
        call = (await http.post("/calls", json={"customer": customer})).json()
        print(f"calling {customer} (call {call['id']}); answering in 3 s while the opening warms up")
        await asyncio.sleep(3)
        await http.post(f"/calls/{call['id']}/status", json={"status": "in_progress"})

    ws_url = SERVER.replace("http", "ws", 1) + f"/calls/{call['id']}/live"
    start = time.monotonic()
    agent_until = 0.0  # when the agent's audio received so far finishes playing
    mix = bytearray()  # the call as heard: both sides on one track
    turn_ended_at: float | None = None
    delays: list[float] = []
    said = 0
    done = asyncio.Event()

    def at(t: float) -> int:
        return int(t * RATE) * 2

    def place(pcm: bytes, t: float) -> None:
        i = at(t)
        if len(mix) < i + len(pcm):
            mix.extend(bytes(i + len(pcm) - len(mix)))
        for k in range(0, len(pcm) - 1, 2):  # add the samples (two people can talk at once)
            a = int.from_bytes(mix[i + k:i + k + 2], "little", signed=True)
            b = int.from_bytes(pcm[k:k + 2], "little", signed=True)
            mix[i + k:i + k + 2] = max(-32768, min(32767, a + b)).to_bytes(2, "little", signed=True)

    async with websockets.connect(ws_url, max_size=2**22) as ws:
        async def receive():
            nonlocal agent_until, turn_ended_at
            async for msg in ws:
                now = time.monotonic() - start
                if isinstance(msg, bytes):
                    if turn_ended_at is not None:
                        delays.append(now - turn_ended_at)
                        print(f"      (reply started {now - turn_ended_at:.1f}s after the customer stopped)")
                        turn_ended_at = None
                    begin = max(now, agent_until)
                    place(msg, begin)
                    agent_until = begin + len(msg) / 2 / RATE
                    continue
                event = json.loads(msg)
                if event["type"] == "line":
                    print(f"{now:5.1f}s {'AGENT   ' if event['who'] == 'agent' else 'CUSTOMER'} {event['text']}")
                elif event["type"] == "end":
                    print(f"{now:5.1f}s (agent hung up)")
                    done.set()
                    return

        async def send():
            """Silence at real-time pace; after the agent finishes talking, say the next line."""
            nonlocal said, turn_ended_at
            queue = bytearray()
            next_frame = time.monotonic()
            while not done.is_set():
                now = time.monotonic() - start
                if not queue and said < len(LINES) and agent_until and now > agent_until + 0.7 \
                        and turn_ended_at is None:
                    queue += voices[said]
                    place(voices[said], now)
                    said += 1
                frame = bytes(queue[:FRAME]) if queue else bytes(FRAME)
                del queue[:FRAME]
                if len(frame) < FRAME:
                    frame += bytes(FRAME - len(frame))
                await ws.send(frame)
                if not queue and said and turn_ended_at is None and frame != bytes(FRAME):
                    turn_ended_at = time.monotonic() - start  # the customer just stopped talking
                next_frame += FRAME_SECONDS
                await asyncio.sleep(max(0.0, next_frame - time.monotonic()))
                if time.monotonic() - start > 120:
                    print("giving up after 2 minutes")
                    done.set()

        receiver = asyncio.create_task(receive())
        await send()
        receiver.cancel()

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
    if delays:
        print("reply delays (customer stops -> agent audio): " + ", ".join(f"{d:.1f}s" for d in delays))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "રમેશભાઈ"))
