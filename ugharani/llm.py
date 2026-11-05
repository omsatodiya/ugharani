"""Thin Gemini client: the call agent's brain. Docs: https://ai.google.dev/api/generate-content"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta/models"
log = logging.getLogger("uvicorn.error")


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
            try:
                resp = await client.post(f"{BASE}/{name}:generateContent", params={"key": _key()}, json=body)
            except httpx.TransportError as e:
                if name == fallback_model():
                    raise LLMError(f"{name}: {type(e).__name__}") from None
                continue
            if resp.status_code not in (429, 500, 503):  # rate limited or overloaded: try the other
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


# Measured on the free tier: either model is sometimes overloaded (no first chunk for 15 s, or 503)
# while the other answers in ~1.5 s, and which one changes from day to day. So a call asks the first
# model, and if it hasn't started within HEDGE_AFTER, asks the other one too; the first to answer is
# used and the other is cancelled. Extra quota is spent only when the first model is slow.
HEDGE_AFTER = 1.5
_last_winner: str | None = None
FIRST_CHUNK_TIMEOUT = 6.0  # a model that hasn't started by then has failed


async def _attempt(name: str, body: dict, out: asyncio.Queue) -> None:
    """Stream one model's reply into `out` as (name, "chunk" | "done" | "error", payload)."""
    started = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=FIRST_CHUNK_TIMEOUT)) as client:
            async with client.stream("POST", f"{BASE}/{name}:streamGenerateContent",
                                     params={"key": _key(), "alt": "sse"}, json=body) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode(errors="replace")[:200]
                    await out.put((name, "error", LLMError(f"{name}: HTTP {resp.status_code} {detail}")))
                    return
                async for line in resp.aiter_lines():
                    if line.startswith("data:") and (chunk := _text(json.loads(line[5:]))):
                        started = True
                        await out.put((name, "chunk", chunk))
        await out.put((name, "done", None) if started else (name, "error", LLMError(f"{name}: empty reply")))
    except httpx.TimeoutException:
        what = "stalled mid-reply" if started else f"no reply in {FIRST_CHUNK_TIMEOUT:.0f}s"
        await out.put((name, "error", LLMError(f"{name}: {what}")))
    except httpx.TransportError as e:
        await out.put((name, "error", LLMError(f"{name}: {type(e).__name__}")))


async def stream(system: str, history: list[dict], max_tokens: int = 400) -> AsyncIterator[str]:
    """Yield the reply as it is generated, so speech can start on the first sentence.

    Hedged: the second model is asked too if the first hasn't started within HEDGE_AFTER, or failed.
    """
    global _last_winner
    body = _body(system, history, None, max_tokens)
    names = [model(), fallback_model()]
    if _last_winner == names[1]:  # the model that answered last time goes first
        names.reverse()
    out: asyncio.Queue = asyncio.Queue()
    tasks: dict[str, asyncio.Task] = {}
    loop = asyncio.get_running_loop()

    def ask(name: str) -> None:
        tasks[name] = asyncio.create_task(_attempt(name, body, out))

    ask(names[0])
    hedge_at = loop.time() + HEDGE_AFTER
    winner: str | None = None
    failed: dict[str, Exception] = {}
    try:
        while True:
            waiting = winner is None and len(tasks) < len(names)
            try:
                name, kind, payload = await asyncio.wait_for(
                    out.get(), timeout=max(0.0, hedge_at - loop.time()) if waiting else None)
            except TimeoutError:
                log.warning("gemini: %s slow to start, asking %s too", names[0], names[1])
                ask(names[1])
                continue
            if winner is not None and name != winner:
                continue  # the other model's leftovers
            if kind == "chunk":
                if winner is None:
                    winner = _last_winner = name
                    for other, task in tasks.items():
                        if other != name:
                            task.cancel()
                yield payload
            elif kind == "done":
                return
            else:  # error
                if name == winner:
                    raise payload  # (half the reply is already said: don't start it again)
                log.warning("gemini: %s", payload)
                failed[name] = payload
                if len(tasks) < len(names):
                    ask(names[len(tasks)])  # no point waiting for HEDGE_AFTER
                elif len(failed) == len(names):
                    raise LLMError("no reply: " + "; ".join(str(e) for e in failed.values()))
    finally:
        for task in tasks.values():
            task.cancel()
