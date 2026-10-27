"""Thin clients for Gnani Prisma (STT) and Timbre (TTS). Docs: https://docs.gnani.ai/api/STT/speech-to-text.md"""

import base64
import io
import json
import unicodedata
import wave

import httpx

from ugharani.config import get_settings

TTS_SAMPLE_RATE = 16000  # Prisma resamples to 16 kHz mono anyway


class GnaniError(Exception):
    pass


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

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{s.gnani_base_url}/stt/v3",
            headers=s.auth_headers,
            data=form,
            files={"audio_file": (filename, audio)},
        )
    try:
        payload = resp.json()
    except ValueError:
        raise GnaniError(f"HTTP {resp.status_code}: {resp.text[:200]}") from None
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


async def synthesize(text: str) -> bytes:
    """POST /api/v1/tts/sse and return the speech as WAV bytes (16 kHz mono PCM)."""
    s = get_settings()
    body = {
        "text": text,
        "model": s.tts_model,
        "voice": s.tts_voice,
        "language": s.language,
        # raw PCM chunks are concatenated and wrapped in a WAV header locally
        "audio_config": {
            "sample_rate": TTS_SAMPLE_RATE,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "raw",
        },
    }
    pcm = bytearray()
    event = None
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", f"{s.gnani_base_url}/api/v1/tts/sse", headers=s.auth_headers, json=body) as resp:
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
                        pcm += base64.b64decode(data["audio"])
                    if event == "complete" or data.get("is_final"):
                        break
    if not pcm:
        raise GnaniError("TTS returned no audio")
    return _wav(bytes(pcm))
