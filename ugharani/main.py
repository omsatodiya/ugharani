import asyncio
import logging
import mimetypes
import os
import re
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from ugharani import db, followup, gnani, live, llm, reminders, speech
from ugharani.extract import ParsedEntry, merge, missing_fields, parse
from ugharani.seed import seed

log = logging.getLogger("uvicorn.error")


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


@app.middleware("http")
async def revalidate_pages(request, call_next):
    """Pages and scripts: always check for a newer version (a 304 when unchanged), so a deploy shows
    up at once instead of whenever the browser's heuristic cache expires. Clips never change."""
    resp = await call_next(request)
    if not request.url.path.startswith("/audio/"):
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


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
    except gnani.GnaniError as e:
        log.warning("Timbre TTS failed: %s", e)
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
        except gnani.GnaniBusy as e:
            log.warning("Prisma STT busy after retry: %s", e)
            raise HTTPException(  # the client keeps its draft, so only this answer is said again
                status_code=503, detail="અવાજ સર્વર વ્યસ્ત છે, ફરી બોલો · Speech server busy, please speak again"
            )
        except gnani.GnaniError as e:
            log.warning("Prisma STT failed: %s", e)
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


# ---------- the follow-up desk: the owner's dashboard ----------

@app.get("/settings")
def get_settings() -> dict:
    conn = db.connect()
    try:
        return followup.get_settings(conn)
    finally:
        conn.close()


@app.put("/settings")
def put_settings(changes: dict) -> dict:
    """Change some of the owner's follow-up rules; send only the keys to change."""
    conn = db.connect()
    try:
        return followup.update_settings(conn, changes)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        conn.close()


class Contact(BaseModel):
    firm: str | None = Field(None, max_length=80)
    city: str | None = Field(None, max_length=40)
    phone: str | None = Field(None, max_length=20)
    deals_with: str | None = Field(None, max_length=60)
    auto_call: bool | None = None


@app.get("/customers")
def list_customers() -> list[dict]:
    conn = db.connect()
    try:
        return followup.customers(conn)
    finally:
        conn.close()


@app.put("/customers/{name}")
def put_customer(name: str, contact: Contact) -> dict:
    conn = db.connect()
    try:
        name = db.resolve_buyer(conn, name)
        followup.upsert_customer(conn, name, contact.phone, contact.deals_with, contact.auto_call,
                                 contact.firm, contact.city)
        return next(c for c in followup.customers(conn) if c["name"] == name)
    finally:
        conn.close()


@app.get("/calls")
def list_calls() -> list[dict]:
    """The call log, newest first: what the agent heard and what it noted."""
    conn = db.connect()
    try:
        return followup.list_calls(conn)
    finally:
        conn.close()


@app.get("/calls/queue")
def call_queue(today: date | None = None) -> list[dict]:
    """Who the agent will call today under the owner's rules. `today` lets a demo jump ahead."""
    conn = db.connect()
    try:
        return followup.to_call(conn, today or date.today())
    finally:
        conn.close()


class CallRequest(BaseModel):
    customer: str


def _customer(conn, name: str) -> dict:
    name = db.resolve_buyer(conn, name)
    found = next((c for c in followup.customers(conn) if c["name"] == name), None)
    if found is None:
        raise HTTPException(status_code=404, detail=f"no customer {name}")
    return found


@app.post("/calls")
def place_call(req: CallRequest, tasks: BackgroundTasks) -> dict:
    """The owner taps 'call now': the customer's phone page starts ringing."""
    conn = db.connect()
    try:
        c = _customer(conn, req.customer)
        if c["balance"] <= 0:
            raise HTTPException(status_code=409, detail=f"{c['name']} has nothing pending")
        last = c["last_call"]
        if last and last["status"] in ("ringing", "in_progress"):
            return last  # already calling them
        tasks.add_task(live.warm_up, followup.get_settings(conn), c)
        return followup.get_call(conn, followup.start_call(conn, c["name"], c["balance"], "manual"))
    finally:
        conn.close()


@app.post("/calls/run")
def run_queue(tasks: BackgroundTasks, today: date | None = None) -> list[dict]:
    """The auto-ugharani tick: ring everyone due a call today under the owner's rules."""
    conn = db.connect()
    try:
        rules = followup.get_settings(conn)
        rung = []
        for q in followup.to_call(conn, today or date.today()):
            tasks.add_task(live.warm_up, rules, _customer(conn, q["customer"]))
            rung.append(followup.get_call(conn, followup.start_call(conn, q["customer"], q["amount"], "auto")))
        return rung
    finally:
        conn.close()


@app.get("/phone/incoming")
def incoming(customer: str) -> dict:
    """What the customer's phone shows: a ringing call (with caller details), or nothing."""
    conn = db.connect()
    try:
        c = _customer(conn, customer)
        rules = followup.get_settings(conn)
    finally:
        conn.close()
    call = c["last_call"]
    ringing = call if call and call["status"] == "ringing" else None
    return {
        "customer": c["name"],
        "caller": {"name": rules["business_name"], "spoken": rules["business_name_spoken"],
                   "place": rules["business_place"]},
        "call": ringing and {"id": ringing["id"], "created_at": ringing["created_at"]},
    }


class CallStatus(BaseModel):
    status: Literal["in_progress", "declined", "missed", "completed", "failed"]


# A ringing call may be answered, declined or missed; an answered one only ends.
NEXT_STATUS = {"ringing": {"in_progress", "declined", "missed", "failed"}, "in_progress": {"completed", "failed"}}


@app.post("/calls/{call_id}/status")
def call_status(call_id: int, change: CallStatus) -> dict:
    conn = db.connect()
    try:
        call = followup.get_call(conn, call_id)
        if call is None:
            raise HTTPException(status_code=404, detail="no such call")
        if change.status not in NEXT_STATUS.get(call["status"], set()):
            raise HTTPException(status_code=409, detail=f"call is {call['status']}, can't become {change.status}")
        followup.set_status(conn, call_id, change.status)
        return followup.get_call(conn, call_id)
    finally:
        conn.close()


_live_calls: set[int] = set()


def max_live_calls() -> int:
    """Each live call streams to Gnani and Gemini; a public demo link can't open more than this at once."""
    return int(os.getenv("MAX_LIVE_CALLS", "2"))


@app.websocket("/calls/{call_id}/live")
async def live_call(ws: WebSocket, call_id: int) -> None:
    """The answered call's audio: the phone page sends the customer's PCM, gets the agent's back.

    Binary frames both ways are 16 kHz mono PCM16. Text frames: the page may send
    {"type": "hangup"}; the server sends {"type": "line", "who", "text"} and, when the
    agent hangs up, {"type": "end"}.
    """
    conn = db.connect()
    try:
        call = followup.get_call(conn, call_id)
        customer = next((c for c in followup.customers(conn) if call and c["name"] == call["customer"]), None)
        rules = followup.get_settings(conn)
        previous = followup.last_call(conn, call["customer"], before=call_id) if call else None
    finally:
        conn.close()
    if call is None or customer is None or call["status"] != "in_progress":
        await ws.close(code=4404 if call is None else 4409)
        return
    if call_id in _live_calls or len(_live_calls) >= max_live_calls():
        await ws.close(code=4429)
        return
    _live_calls.add(call_id)
    await ws.accept()
    session = live.LiveCall(rules, customer, date.today(), previous, ws.send_bytes, ws.send_json)
    try:
        terms = [customer["name"], *(customer.get(k) for k in ("firm", "city", "deals_with")),
                 rules["business_name_spoken"]]
        async with gnani.live_stt([t for t in terms if t]) as stt:
            async def from_phone():
                while not session.done.is_set():
                    kind, data = live.browser_message(await ws.receive())
                    if kind == "audio":
                        await stt.send(data)
                    elif kind in ("hangup", "closed"):
                        session.ended_by = session.ended_by or "customer"
                        session.done.set()
                        return

            phone = asyncio.create_task(from_phone())
            try:
                await session.run(stt.events())
            finally:
                phone.cancel()
    except (gnani.GnaniError, llm.LLMError) as e:
        log.warning("call %s failed: %s", call_id, e)
    finally:
        _live_calls.discard(call_id)
        log.info("call %s ended by %s after %d turns", call_id, session.ended_by, len(session.history))
        conn = db.connect()
        try:
            # "failed" only if nothing was said at all; otherwise it's a (short) call worth noting
            followup.end_live_call(conn, call_id, session.history, ok=bool(session.history))
        finally:
            conn.close()
        try:
            await ws.close()
        except (RuntimeError, WebSocketDisconnect):
            pass  # the phone already closed it


@app.get("/calls/{call_id}")
def get_call(call_id: int) -> dict:
    conn = db.connect()
    try:
        call = followup.get_call(conn, call_id)
    finally:
        conn.close()
    if call is None:
        raise HTTPException(status_code=404, detail="no such call")
    return call


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
