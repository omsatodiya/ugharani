"""Run the app with Gnani faked, to test the phone page's audio wiring for free.

    uv run python scripts/fake_voice_server.py      # then open http://localhost:8000/phone.html

- live STT: checks the browser's frames (exactly 1024 bytes, about 31 per second) and, every
  few seconds of audio, "hears" the next line of a scripted customer
- Timbre: a short tone per sentence (the opening and fixed lines too), so playback can be heard
- Gemini is real (free tier) unless FAKE_LLM=1
"""

import asyncio
import math
import os
import struct
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")  # Gujarati in a Windows console
sys.stderr.reconfigure(encoding="utf-8")
os.environ.setdefault("LEDGER_DB", "out/fake_voice.db")
os.environ.setdefault("AUDIO_CACHE", "out/fake_tts")  # tones only: never mix them with real clips
os.environ.setdefault("DEMO_SEED", "1")
os.environ.setdefault("GNANI_API_KEY", "fake")

import uvicorn  # noqa: E402

from ugharani import gnani, llm, main, speech  # noqa: E402

CUSTOMER = ["હા બોલો", "હા, 10 તારીખે RTGS કરી દઈશ", "હા બરાબર", "આવજો"]
SECONDS_PER_LINE = 4.0


def tone(seconds: float, freq: float = 440.0) -> bytes:
    n = int(16000 * seconds)
    return b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / 16000))) for i in range(n))


async def synthesize_stream(text: str):
    seconds = min(2.5, 0.4 + len(text) / 40)
    pcm = tone(seconds, 330 + (hash(text) % 300))
    for i in range(0, len(pcm), 3200):  # 100 ms chunks, like Timbre's stream
        await asyncio.sleep(0.02)
        yield pcm[i:i + 3200]


async def synthesize(text: str) -> bytes:
    return gnani._wav(b"".join([c async for c in synthesize_stream(text)]))


class FakeLiveSTT:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.bytes = 0
        self.frames = 0
        self.bad = 0
        self.started = time.monotonic()
        self.said = 0

    async def send(self, pcm: bytes) -> None:
        self.frames += 1
        self.bad += len(pcm) != 1024
        self.bytes += len(pcm)
        heard = self.bytes / 32000
        if self.frames % 155 == 0:  # ~every 5 s
            rate = self.frames / (time.monotonic() - self.started)
            print(f"[fake stt] {self.frames} frames, {heard:.1f}s audio, {rate:.1f} frames/s, "
                  f"{self.bad} not 1024 bytes", flush=True)
        if self.said < len(CUSTOMER) and heard >= SECONDS_PER_LINE * (self.said + 1):
            text = CUSTOMER[self.said]
            self.said += 1
            print(f"[fake stt] customer says: {text}", flush=True)
            await self.queue.put({"type": "speech_start"})
            await self.queue.put({"type": "transcript", "text": text})

    async def events(self):
        while True:
            yield await self.queue.get()


@asynccontextmanager
async def live_stt(keyterms=None):
    print(f"[fake stt] session opened, keyterms={keyterms}", flush=True)
    yield FakeLiveSTT()


async def fake_llm(system, history, max_tokens=400):
    turns = sum(h["who"] == "agent" for h in history)
    yield ["₹1,00,000 બાકી છે, ક્યારે આવશે?", "તો 10 તારીખે RTGS, બરાબર ને?", "સારું, આભાર. આવજો. <END>"][min(turns - 1, 2)]


gnani.synthesize_stream = synthesize_stream
gnani.synthesize = synthesize
gnani.live_stt = live_stt
if os.getenv("FAKE_LLM") == "1":
    llm.stream = fake_llm
assert speech  # (imported so its gnani reference is the patched module)

if __name__ == "__main__":
    uvicorn.run(main.app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
