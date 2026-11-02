"""The follow-up desk: the owner's rules, customer contacts, the call log, and who to call today.

This is the job of the person a trader pays to chase payments: call when a bill
falls due, call again every few days, wait while a promise is still good, and
leave big amounts and disputes to the owner.
"""

import json
import sqlite3
from datetime import date, datetime, timedelta

from ugharani import reminders

# Every setting is stored as text; TYPES says how to read it back.
DEFAULTS = {
    "business_name": "Genius Polyplast",
    "business_name_spoken": "જીનિયસ પોલીપ્લાસ્ટ",  # how the agent says it (Timbre reads Gujarati script best)
    "business_place": "ગોંડલ, રાજકોટ",
    "products": "PVC, CPVC અને UPVC પાઇપ ફિટિંગ્સ, બ્રાસ ફિટિંગ્સ અને વાલ્વ",
    "agent_name": "કાવ્યા",         # who the agent says it is
    "owner_name": "શેઠ",             # how the agent refers to the owner
    "remind_after_days": "0",       # first call this many days after the due date
    "repeat_every_days": "3",       # then again after this many days without payment
    "handover_amount": "200000",    # dues at or above this go to the owner after the call
    "tone": "gentle",               # gentle | firm
    "auto_calls": "1",              # master switch for automatic calls
}
TYPES = {"remind_after_days": int, "repeat_every_days": int, "handover_amount": int, "auto_calls": bool}
TONES = {"gentle", "firm"}
OUTCOMES = {"promised", "paid", "dispute", "callback", "handover", "refused", "unclear"}


# ---------- settings ----------

def get_settings(conn: sqlite3.Connection) -> dict:
    stored = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    out = {}
    for key, default in DEFAULTS.items():
        raw = stored.get(key, default)
        kind = TYPES.get(key, str)
        out[key] = raw == "1" if kind is bool else kind(raw)
    return out


def update_settings(conn: sqlite3.Connection, changes: dict) -> dict:
    """Validate and save the owner's changes; unknown keys are rejected."""
    for key, value in changes.items():
        if key not in DEFAULTS:
            raise ValueError(f"unknown setting {key!r}")
        kind = TYPES.get(key, str)
        if kind is bool:
            text = "1" if value in (True, 1, "1", "true") else "0"
        elif kind is int:
            if int(value) < 0:
                raise ValueError(f"{key} can't be negative")
            text = str(int(value))
        else:
            text = str(value).strip()
            if not text:
                raise ValueError(f"{key} can't be empty")
            if key == "tone" and text not in TONES:
                raise ValueError(f"tone must be one of {sorted(TONES)}")
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, text))
    conn.commit()
    return get_settings(conn)


# ---------- customers ----------

def upsert_customer(conn: sqlite3.Connection, name: str, phone: str | None = None,
                    deals_with: str | None = None, auto_call: bool | None = None,
                    firm: str | None = None, city: str | None = None) -> None:
    conn.execute("INSERT OR IGNORE INTO customers (name) VALUES (?)", (name,))
    for column, value in (("phone", phone), ("deals_with", deals_with), ("firm", firm), ("city", city)):
        if value is not None:
            conn.execute(f"UPDATE customers SET {column} = ? WHERE name = ?", (value.strip() or None, name))
    if auto_call is not None:
        conn.execute("UPDATE customers SET auto_call = ? WHERE name = ?", (int(auto_call), name))
    conn.commit()


def customers(conn: sqlite3.Connection) -> list[dict]:
    """Everyone in the ledger or the contact list, with balance, contact and last call."""
    contacts = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM customers")}
    owed = {b["buyer"]: b for b in reminders.balances(conn)}
    out = []
    for name in dict.fromkeys([*owed, *contacts]):
        c = contacts.get(name, {})
        b = owed.get(name, {})
        last = last_call(conn, name)
        out.append({
            "name": name,
            "firm": c.get("firm"),
            "city": c.get("city"),
            "phone": c.get("phone"),
            "deals_with": c.get("deals_with"),
            "auto_call": bool(c.get("auto_call", 1)),
            "balance": b.get("balance", 0),
            "earliest_due": b.get("earliest_due"),
            "last_call": last,
        })
    return out


# ---------- calls ----------

def _call(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    call = dict(row)
    call["transcript"] = json.loads(call["transcript"]) if call["transcript"] else []
    return call


def start_call(conn: sqlite3.Connection, customer: str, amount_due: int, trigger: str = "manual",
               when: datetime | None = None) -> int:
    # Local time, not SQLite's UTC default: "called today" must mean the trader's today.
    when = when or datetime.now()
    cur = conn.execute("INSERT INTO calls (customer, trigger, amount_due, created_at) VALUES (?, ?, ?, ?)",
                       (customer, trigger, amount_due, when.isoformat(timespec="seconds")))
    conn.commit()
    return cur.lastrowid


def get_call(conn: sqlite3.Connection, call_id: int) -> dict | None:
    return _call(conn.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone())


def last_call(conn: sqlite3.Connection, customer: str, before: int | None = None) -> dict | None:
    """The customer's latest call, or the latest one before call id `before`."""
    return _call(conn.execute("SELECT * FROM calls WHERE customer = ? AND id < ? ORDER BY id DESC LIMIT 1",
                              (customer, before if before is not None else 2**62)).fetchone())


def list_calls(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    return [_call(r) for r in conn.execute("SELECT * FROM calls ORDER BY id DESC LIMIT ?", (limit,))]


def set_status(conn: sqlite3.Connection, call_id: int, status: str) -> None:
    ended = status in ("completed", "missed", "declined", "failed")
    conn.execute("UPDATE calls SET status = ?, ended_at = CASE WHEN ? THEN ? ELSE ended_at END WHERE id = ?",
                 (status, ended, datetime.now().isoformat(timespec="seconds"), call_id))
    conn.commit()


def end_live_call(conn: sqlite3.Connection, call_id: int, transcript: list[dict], ok: bool = True) -> None:
    """The line dropped or someone hung up: keep what was said. Notes are added after (finish_call)."""
    conn.execute("UPDATE calls SET status = ?, transcript = ?, ended_at = ? WHERE id = ? AND status = 'in_progress'",
                 ("completed" if ok else "failed", json.dumps(transcript, ensure_ascii=False),
                  datetime.now().isoformat(timespec="seconds"), call_id))
    conn.commit()


def finish_call(conn: sqlite3.Connection, call_id: int, *, transcript: list[dict], outcome: str,
                summary: str, promised_amount: int | None = None, promised_date: date | None = None,
                recording: str | None = None) -> None:
    """Store what the call achieved: the agent's notes in 'the sheet'."""
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}")
    conn.execute(
        """UPDATE calls SET status = 'completed', outcome = ?, summary = ?, transcript = ?,
               promised_amount = ?, promised_date = ?, recording = ?, ended_at = ? WHERE id = ?""",
        (outcome, summary, json.dumps(transcript, ensure_ascii=False), promised_amount,
         promised_date.isoformat() if promised_date else None, recording,
         datetime.now().isoformat(timespec="seconds"), call_id),
    )
    conn.commit()


# ---------- who to call ----------

def _call_day(call: dict) -> date:
    return date.fromisoformat(call["created_at"][:10])


def to_call(conn: sqlite3.Connection, today: date) -> list[dict]:
    """Customers the agent should call today, most overdue first, each with the reason.

    - first call `remind_after_days` after the oldest unpaid due date
    - while a promise is still in the future, wait; once it passes unpaid, call
    - a call that didn't get through is retried the next day
    - otherwise call again every `repeat_every_days`
    - never: auto calls off (globally or for this customer), or the owner took it over
    """
    rules = get_settings(conn)
    if not rules["auto_calls"]:
        return []
    out = []
    for c in customers(conn):
        if c["balance"] <= 0 or not c["earliest_due"] or not c["auto_call"]:
            continue
        due = date.fromisoformat(c["earliest_due"])
        if today < due + timedelta(days=rules["remind_after_days"]):
            continue
        last = c["last_call"]
        reason = "overdue" if due < today else "due_today"
        if last:
            if last["status"] in ("ringing", "in_progress") or last["outcome"] in ("handover", "dispute"):
                continue  # already on the phone, or the owner's to handle now
            if last["status"] in ("missed", "declined", "failed"):
                if (today - _call_day(last)).days < 1:
                    continue
                reason = "retry"  # didn't get through: try again the next day
            elif last["promised_date"]:
                promised = date.fromisoformat(last["promised_date"])
                if today <= promised:
                    continue
                reason = "promise_missed"
            elif (today - _call_day(last)).days < rules["repeat_every_days"]:
                continue
        out.append({"customer": c["name"], "phone": c["phone"], "amount": c["balance"],
                    "due_date": c["earliest_due"], "reason": reason})
    return sorted(out, key=lambda x: x["due_date"])
