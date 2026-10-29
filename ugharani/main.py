import mimetypes
import os
import re
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from ugharani import db, gnani, reminders, speech
from ugharani.extract import ParsedEntry, merge, missing_fields, parse
from ugharani.seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Free hosting wipes the disk on every restart, so a demo server starts from sample buyers.
    if os.getenv("DEMO_SEED") == "1":
        conn = db.connect()
        try:
            seed(conn)
        finally:
            conn.close()
    yield


app = FastAPI(title="Ugharani", lifespan=lifespan)


class Draft(BaseModel):
    """An entry the trader has not confirmed yet. The client holds it between requests."""

    kind: Literal["credit", "payment"] = "credit"
    buyer: str | None = None
    amount: int | None = None
    due_date: date | None = None
    transcript: str = ""

    def entry(self) -> ParsedEntry:
        return ParsedEntry(
            kind=self.kind,
            buyer=self.buyer,
            amount=self.amount,
            due_days=None,
            due_date=self.due_date,
            missing=missing_fields(self.kind, self.buyer, self.amount, self.due_date),
        )


async def audio_url(text: str) -> str | None:
    """Speak `text` (cached), or None if Timbre fails: the client can still show the text."""
    try:
        return f"/audio/{await speech.speak(text)}.wav"
    except gnani.GnaniError:
        return None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/entries/voice")
async def voice_entry(audio: UploadFile, draft: str | None = Form(None)) -> dict:
    """Audio clip -> Prisma transcript -> draft entry + what to say back. Saves nothing.

    Send the previous response's `draft` (as JSON) with a follow-up recording to fill
    its missing field. Once nothing is missing, `say` is the read-back; the client
    saves the draft with POST /entries when the trader confirms.
    """
    try:
        previous = Draft.model_validate_json(draft) if draft else None
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"bad draft: {e.errors()}")

    conn = db.connect()
    try:
        bias = gnani.bias_words(db.known_buyers(conn))
        try:
            stt = await gnani.transcribe(await audio.read(), audio.filename or "audio.wav", bias)
        except gnani.GnaniError as e:
            raise HTTPException(status_code=502, detail=f"Prisma STT failed: {e}")

        transcript = stt["transcript"]
        today = date.today()
        entry = parse(transcript, today=today)
        if previous:
            entry = merge(previous.entry(), entry)
        if entry.buyer:
            entry = replace(entry, buyer=db.resolve_buyer(conn, entry.buyer))
    finally:
        conn.close()

    say = speech.reply(entry, today)
    return {
        "transcript": transcript,
        "stt_request_id": stt.get("request_id"),
        "draft": Draft(
            kind=entry.kind,
            buyer=entry.buyer,
            amount=entry.amount,
            due_date=entry.due_date,
            transcript=f"{previous.transcript} | {transcript}" if previous else transcript,
        ).model_dump(mode="json"),
        "missing": entry.missing,
        "say": say,
        "audio": await audio_url(say),
    }


@app.post("/entries")
def save_entry(draft: Draft) -> dict:
    """Save a draft the trader confirmed."""
    entry = draft.entry()
    if entry.missing:
        raise HTTPException(status_code=422, detail={"missing": entry.missing})
    conn = db.connect()
    try:
        return {"entry_id": db.add_entry(conn, entry, draft.transcript)}
    finally:
        conn.close()


@app.get("/entries")
def list_entries() -> list[dict]:
    conn = db.connect()
    try:
        return [dict(r) for r in db.list_entries(conn)]
    finally:
        conn.close()


@app.get("/balances")
def balances() -> list[dict]:
    conn = db.connect()
    try:
        return reminders.balances(conn)
    finally:
        conn.close()


@app.get("/summary")
async def summary(today: date | None = None) -> dict:
    """The trader's daily summary: overdue, due today, due soon. `today` lets a demo jump ahead."""
    today = today or date.today()
    conn = db.connect()
    try:
        items = reminders.due_items(conn, today)
    finally:
        conn.close()
    say = reminders.summary_text(items)
    return {"today": today.isoformat(), "items": items, "say": say, "audio": await audio_url(say)}


@app.get("/reminders/{buyer}")
async def buyer_reminder(buyer: str, today: date | None = None) -> dict:
    """A polite reminder for one buyer, for the trader to send from their own WhatsApp."""
    today = today or date.today()
    conn = db.connect()
    try:
        reminder = reminders.buyer_reminder(conn, db.resolve_buyer(conn, buyer), today)
    finally:
        conn.close()
    if reminder is None:
        raise HTTPException(status_code=404, detail=f"nothing due from {buyer}")
    return {**reminder, "audio": await audio_url(reminder["say"])}


@app.get("/audio/{key}.wav")
def audio(key: str) -> FileResponse:
    """Serve a cached Timbre clip. Keys come from speech.speak, so nothing here costs credits."""
    path = speech.clip_path(key)
    if not re.fullmatch(r"[0-9a-f]{16}", key) or not path.exists():
        raise HTTPException(status_code=404, detail="no such clip")
    return FileResponse(path, media_type="audio/wav")


# The PWA. Mounted last so the API routes above match first.
mimetypes.add_type("application/manifest+json", ".webmanifest")
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="pwa")
