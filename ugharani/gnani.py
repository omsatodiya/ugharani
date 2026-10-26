"""Thin client for Gnani Prisma (STT). Docs: https://docs.gnani.ai/api/STT/speech-to-text.md"""

import json
import unicodedata

import httpx

from ugharani.config import get_settings


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
