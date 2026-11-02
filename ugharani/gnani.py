"""Thin clients for Gnani Prisma (STT, REST and live) and Timbre (TTS). Docs: https://docs.gnani.ai/llms.txt"""

import asyncio
import base64
import io
import json
import logging
import os
import unicodedata
import wave
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

import httpx
import websockets

from ugharani.config import get_settings

log = logging.getLogger("uvicorn.error")

TTS_SAMPLE_RATE = 16000  # Prisma resamples to 16 kHz mono anyway


class GnaniError(Exception):
    pass


class GnaniBusy(GnaniError):
    """Gnani's gateway timed out or is overloaded (502/503/504): worth trying again later."""


BUSY_STATUSES = {502, 503, 504}
STT_ATTEMPTS = 2  # one retry: a 504 from Gnani's gateway usually clears on the next call


def _short(resp: httpx.Response) -> str:
    """The error body, but not a gateway's HTML error page."""
    text = resp.text.strip()
    return "gateway error page" if text.startswith("<") else text[:200]


_calls: dict[date, int] = {}


def _spend() -> None:
    """Count a paid call; refuse once GNANI_DAILY_LIMIT calls were made today by this server.

    A guard so a public demo link can't drain the challenge credits.
    """
    today = date.today()
    if today not in _calls:
        _calls.clear()  # new day, new budget
        _calls[today] = 0
    limit = int(os.getenv("GNANI_DAILY_LIMIT", "150"))
    if _calls[today] >= limit:
        raise GnaniError(f"daily limit of {limit} Gnani calls reached")
    _calls[today] += 1


def bias_words(names: list[str]) -> list[str]:
    """Prisma's bias_list takes up to 100 letter-only words (no digits, spaces or punctuation)."""
    def letters_only(word: str) -> bool:
        return all(c.isalpha() or unicodedata.category(c).startswith("M") for c in word)

    words = dict.fromkeys(w for name in names for w in name.split() if letters_only(w))
    return list(words)[:100]


async def transcribe(audio: bytes, filename: str, bias: list[str] | None = None) -> dict:
    """POST /stt/v3 with ITN on. Returns the JSON payload (transcript, request_id, ...)."""
    s = get_settings()
    form = {
        "language_code": s.language,
        "format": "transcribe",  # enables ITN: numbers, ₹, dates -> digits
    }
    if bias:
        form["bias_list"] = json.dumps(bias, ensure_ascii=False)
        form["bias_score"] = "1.0"  # docs: start at 1.0

    for attempt in range(1, STT_ATTEMPTS + 1):
        _spend()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{s.gnani_base_url}/stt/v3",
                    headers=s.auth_headers,
                    data=form,
                    files={"audio_file": (filename, audio)},
                )
        except httpx.TransportError as e:  # timeouts and dropped connections
            busy = GnaniBusy(f"no response from Prisma ({type(e).__name__})")
        else:
            if resp.status_code not in BUSY_STATUSES:
                break
            busy = GnaniBusy(f"HTTP {resp.status_code}: {_short(resp)}")
        if attempt == STT_ATTEMPTS:
            raise busy
    try:
        payload = resp.json()
    except ValueError:
        raise GnaniError(f"HTTP {resp.status_code}: {_short(resp)}") from None
    if resp.status_code != 200 or not payload.get("success"):
        raise GnaniError(f"HTTP {resp.status_code}: {payload}")
    return payload


def _wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TTS_SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _tts_body(text: str) -> dict:
    s = get_settings()
    return {
        "text": text,
        "model": s.tts_model,
        "voice": s.tts_voice,
        "language": s.language,
        # raw PCM chunks: played as they arrive on a call, wrapped in a WAV header for clips
        "audio_config": {
            "sample_rate": TTS_SAMPLE_RATE,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "raw",
        },
    }


async def synthesize_stream(text: str) -> AsyncIterator[bytes]:
    """POST /api/v1/tts/sse and yield raw 16 kHz mono PCM16 chunks as Timbre makes them."""
    s = get_settings()
    _spend()
    event = None
    sent = False
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", f"{s.gnani_base_url}/api/v1/tts/sse", headers=s.auth_headers,
                                 json=_tts_body(text)) as resp:
            if resp.status_code != 200:
                raise GnaniError(f"HTTP {resp.status_code}: {(await resp.aread()).decode(errors='replace')[:200]}")
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[len("data:"):])
                    if event == "error":
                        raise GnaniError(f"TTS error: {data}")
                    if data.get("audio"):
                        sent = True
                        yield base64.b64decode(data["audio"])
                    if event == "complete" or data.get("is_final"):
                        break
    if not sent:
        raise GnaniError("TTS returned no audio")


async def synthesize(text: str) -> bytes:
    """The whole sentence as WAV bytes (16 kHz mono PCM)."""
    return _wav(b"".join([chunk async for chunk in synthesize_stream(text)]))


# ---------- live speech recognition for calls ----------

FRAME_BYTES = 1024  # Gnani wants exactly 512 samples of PCM16 per frame (32 ms at 16 kHz)


class LiveSTT:
    """One streaming Prisma session: send PCM as it is spoken, read VAD-cut transcripts."""

    def __init__(self, ws):
        self._ws = ws
        self._buf = bytearray()

    async def send(self, pcm: bytes) -> None:
        """Forward audio in exact 1024-byte frames, keeping any remainder for the next call."""
        self._buf += pcm
        while len(self._buf) >= FRAME_BYTES:
            frame, self._buf = bytes(self._buf[:FRAME_BYTES]), self._buf[FRAME_BYTES:]
            await self._ws.send(frame)

    async def events(self) -> AsyncIterator[dict]:
        """speech_start, processing, transcript and error messages, in order. Ends if Gnani closes."""
        try:
            async for raw in self._ws:
                if isinstance(raw, str):
                    yield json.loads(raw)
        except websockets.ConnectionClosed as e:
            log.warning("live STT closed: %s", e)


def live_headers(keyterms: list[str] | None = None) -> dict[str, str]:
    s = get_settings()
    headers = {
        "x-api-key-id": s.gnani_api_key,
        "model": "prisma-v3.0",
        # Exactly one locale on this endpoint; Hindi and English words come back in Gujarati script,
        # which Gemini reads fine.
        "language_code": os.getenv("STT_LANGUAGE", "gu-IN"),
        "format": "transcribe",  # amounts and dates as digits
        "x-sample-rate": str(TTS_SAMPLE_RATE),
        # A phone conversation: people pause mid-sentence ("15 તારીખે... કરી દઈશ").
        "x-min-silence-ms": os.getenv("STT_MIN_SILENCE_MS", "600"),
        "x-vad-threshold": os.getenv("STT_VAD_THRESHOLD", "0.6"),
        "x-idle-timeout-sec": "120",
        "topic": "A supplier's staff calling a dealer about a pending payment, in Gujarati and Hindi.",
    }
    if keyterms:
        # Headers are ASCII; the docs say to JSON-escape non-ASCII terms.
        headers["keyterms"] = json.dumps(keyterms[:200])
    return headers


@asynccontextmanager
async def live_stt(keyterms: list[str] | None = None) -> AsyncIterator[LiveSTT]:
    """Open wss://.../stt/v3/stream for one call."""
    s = get_settings()
    _spend()
    url = s.gnani_base_url.replace("https://", "wss://").replace("http://", "ws://") + "/stt/v3/stream"
    try:
        ws = await websockets.connect(url, additional_headers=live_headers(keyterms), open_timeout=10,
                                      max_size=2**20)
    except (websockets.InvalidStatus, websockets.InvalidHandshake, OSError, TimeoutError) as e:
        raise GnaniError(f"live STT connect failed: {e}") from None
    try:
        # The first message says whether Gnani accepted the settings; a refusal follows with a close.
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        except (TimeoutError, websockets.ConnectionClosed, ValueError) as e:
            raise GnaniError(f"live STT did not start: {e!r}") from None
        if hello.get("type") != "connected":
            raise GnaniError(f"live STT refused: {hello.get('message') or hello}")
        log.info("live STT connected: %s", hello.get("config"))
        yield LiveSTT(ws)
    finally:
        await ws.close()
