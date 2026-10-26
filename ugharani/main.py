from fastapi import FastAPI, HTTPException, UploadFile

from ugharani import db, gnani
from ugharani.extract import parse

app = FastAPI(title="Ugharani")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/entries/voice")
async def add_voice_entry(audio: UploadFile) -> dict:
    """Audio clip -> Prisma transcript -> parsed entry, saved if buyer/amount/due date are all present."""
    conn = db.connect()
    try:
        bias = gnani.bias_words(db.known_buyers(conn))
        try:
            stt = await gnani.transcribe(await audio.read(), audio.filename or "audio.wav", bias)
        except gnani.GnaniError as e:
            raise HTTPException(status_code=502, detail=f"Prisma STT failed: {e}")

        transcript = stt["transcript"]
        entry = parse(transcript)
        buyer = db.resolve_buyer(conn, entry.buyer) if entry.buyer else None
        return {
            "transcript": transcript,
            "stt_request_id": stt.get("request_id"),
            "kind": entry.kind,
            "buyer": buyer,
            "amount": entry.amount,
            "due_date": entry.due_date.isoformat() if entry.due_date else None,
            "missing": entry.missing,
            "entry_id": db.add_entry(conn, entry, transcript) if entry.complete else None,
        }
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
        return [dict(r) for r in db.balances(conn)]
    finally:
        conn.close()
