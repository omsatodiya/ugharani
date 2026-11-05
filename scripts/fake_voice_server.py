"""Run the app with Gnani faked, to test the phone page's audio wiring for free.

    uv run python scripts/fake_voice_server.py      # then open http://localhost:8000/phone.html

- live STT: checks the browser's frames (exactly 1024 bytes, about 31 per second) and "hears" a
  scripted customer at fixed times into the call, one line cutting in while the agent talks
- Timbre: a short tone per sentence (the opening and fixed lines too), so playback can be heard
- Gemini is real (free tier) unless FAKE_LLM=1
- writes out/fake_mic.wav: the same customer as sound (plus a cough the STT doesn't "hear"), for
  Chrome's fake microphone (browser_check.py uses it), so the server's own speech detector pauses her
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

# (seconds of call audio when they start talking, what they say). The greeting plays at about
# 1.2 s and she waits; the intro and her first reply follow the answer (~4-11 s), so line 2 cuts in.
CUSTOMER = [(3.0, "હા બોલો"), (9.6, "અરે, મેં તો ગયા અઠવાડિયે પેમેન્ટ કરી દીધું છે"), (16.5, "હા બરાબર")]
SPEAKING = 0.6  # each line lasts this long; the transcript comes when it ends
COUGH = 12.6    # a short noise while she talks, no words: she pauses, then goes on
MIC_WAV = Path("out/fake_mic.wav")


def mic_audio() -> bytes:
    """The customer as the phone's microphone hears them: voice-like sound while they speak."""
    pcm = bytearray(32000 * 22)  # (Chrome loops the file; the call is over by then)
    bursts = [(at, SPEAKING) for at, _ in CUSTOMER] + [(COUGH, 0.35)]
    for at, seconds in bursts:
        for i in range(int(16000 * seconds)):
            t = i / 16000
            v = 5000 * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * t)) * (
                math.sin(2 * math.pi * 180 * t) + 0.5 * math.sin(2 * math.pi * 720 * t))
            struct.pack_into("<h", pcm, 2 * (int(16000 * at) + i), int(max(-32767, min(32767, v))))
    return bytes(pcm)


def tone(seconds: float, freq: float = 440.0) -> bytes:
    n = int(16000 * seconds)
    return b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / 16000))) for i in range(n))


async def synthesize_stream(text: str):
    seconds = min(4.0, 0.4 + len(text) / 12)
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
        if self.said < len(CUSTOMER) and heard >= CUSTOMER[self.said][0]:
            text = CUSTOMER[self.said][1]
            self.said += 1
            print(f"[fake stt] customer says: {text}", flush=True)
            await self.queue.put({"type": "speech_start"})

            async def finish():  # like real VAD: voice heard now, the transcript once they stop
                await asyncio.sleep(SPEAKING)
                await self.queue.put({"type": "transcript", "text": text})

            self.pending = asyncio.create_task(finish())

    async def events(self):
        while True:
            yield await self.queue.get()


@asynccontextmanager
async def live_stt(keyterms=None):
    print(f"[fake stt] session opened, keyterms={keyterms}", flush=True)
    yield FakeLiveSTT()


async def fake_llm(system, history, max_tokens=400):
    turns = sum(h["who"] == "agent" for h in history)
    yield ["₹1,20,000 બાકી છે, ક્યારે આવશે?", "અચ્છા. તો UTR નંબર મોકલી દેશો?",
           "સારું, આભાર. આવજો. <END>"][min(turns - 1, 2)]


gnani.synthesize_stream = synthesize_stream
gnani.synthesize = synthesize
gnani.live_stt = live_stt
if os.getenv("FAKE_LLM") == "1":
    llm.stream = fake_llm
assert speech  # (imported so its gnani reference is the patched module)

if __name__ == "__main__":
    MIC_WAV.parent.mkdir(exist_ok=True)
    MIC_WAV.write_bytes(gnani._wav(mic_audio()))
    uvicorn.run(main.app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
