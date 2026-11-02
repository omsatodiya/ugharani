"""Thin Gemini client: the call agent's brain. Docs: https://ai.google.dev/api/generate-content"""

import json
import os
from collections.abc import AsyncIterator

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class LLMError(Exception):
    pass


def model() -> str:
    # Flash-lite: natural Gujarati-Hindi in testing, and the fastest Flash tier for a live call.
    return os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def _key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise LLMError("GEMINI_API_KEY is not set")
    return key


def _body(system: str, history: list[dict], schema: dict | None, max_tokens: int) -> dict:
    """history: [{"who": "agent" | "customer", "text": ...}] -> Gemini contents."""
    contents = [{"role": "model" if h["who"] == "agent" else "user", "parts": [{"text": h["text"]}]}
                for h in history]
    if not contents or contents[0]["role"] != "user":
        # Gemini wants the user to speak first; the call starts with the phone being picked up.
        contents.insert(0, {"role": "user", "parts": [{"text": "(ફોન ઉપાડ્યો)"}]})
    config = {"maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingLevel": "minimal"}}
    if schema:
        config |= {"responseMimeType": "application/json", "responseSchema": schema}
    return {"system_instruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": config}


def _text(payload: dict) -> str:
    try:
        return "".join(p.get("text", "") for p in payload["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError):
        return ""


def fallback_model() -> str:
    # A second model has its own free-tier quota: used when the first answers 429 (rate limited).
    return os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash")


async def generate(system: str, history: list[dict], schema: dict | None = None, max_tokens: int = 400) -> str:
    body = _body(system, history, schema, max_tokens)
    async with httpx.AsyncClient(timeout=30) as client:
        for name in (model(), fallback_model()):
            resp = await client.post(f"{BASE}/{name}:generateContent", params={"key": _key()}, json=body)
            if resp.status_code != 429:
                break
    if resp.status_code != 200:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return _text(resp.json()).strip()


async def generate_json(system: str, history: list[dict], schema: dict) -> dict:
    text = await generate(system, history, schema, max_tokens=800)
    try:
        return json.loads(text)
    except ValueError:
        raise LLMError(f"not JSON: {text[:200]}") from None


# On a call, a reply that hasn't started within this long is abandoned and asked again: flash-lite
# usually starts in ~1 s but now and then stalls for 10 s+, and a retry is faster than waiting it out.
FIRST_CHUNK_TIMEOUT = 4.0


async def stream(system: str, history: list[dict], max_tokens: int = 400) -> AsyncIterator[str]:
    """Yield the reply as it is generated, so speech can start on the first sentence.

    Tries flash-lite twice (each with a short wait for the first chunk), then the fallback model.
    """
    body = _body(system, history, None, max_tokens)
    attempts = [(model(), FIRST_CHUNK_TIMEOUT), (model(), FIRST_CHUNK_TIMEOUT), (fallback_model(), 20.0)]
    last = "no attempt"
    for name, wait in attempts:
        timeout = httpx.Timeout(30.0, read=wait)  # read: also the wait for the first bytes
        started = False
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", f"{BASE}/{name}:streamGenerateContent",
                                         params={"key": _key(), "alt": "sse"}, json=body) as resp:
                    if resp.status_code == 429 or resp.status_code >= 500:
                        last = f"HTTP {resp.status_code}"
                        continue  # rate limited or overloaded: try again / the fallback
                    if resp.status_code != 200:
                        raise LLMError(f"HTTP {resp.status_code}: {(await resp.aread()).decode(errors='replace')[:300]}")
                    async for line in resp.aiter_lines():
                        if line.startswith("data:"):
                            if chunk := _text(json.loads(line[5:])):
                                started = True
                                yield chunk
                    if started:
                        return
                    last = "empty reply"
        except httpx.TimeoutException:
            if started:  # half a reply was already spoken: don't start it again
                raise LLMError(f"{name} stalled mid-reply") from None
            last = f"{name}: no reply in {wait:.0f}s"
        except httpx.TransportError as e:
            last = f"{name}: {type(e).__name__}"
    raise LLMError(f"no reply after {len(attempts)} tries ({last})")
