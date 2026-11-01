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


async def stream(system: str, history: list[dict], max_tokens: int = 400) -> AsyncIterator[str]:
    """Yield the reply as it is generated, so speech can start on the first sentence."""
    async with httpx.AsyncClient(timeout=30) as client:
        async with client.stream("POST", f"{BASE}/{model()}:streamGenerateContent",
                                 params={"key": _key(), "alt": "sse"},
                                 json=_body(system, history, None, max_tokens)) as resp:
            if resp.status_code != 200:
                raise LLMError(f"HTTP {resp.status_code}: {(await resp.aread()).decode(errors='replace')[:300]}")
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    if chunk := _text(json.loads(line[5:])):
                        yield chunk
