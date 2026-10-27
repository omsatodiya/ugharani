"""What is due: open credits, the trader's daily summary, and reminders for buyers.

Payments settle a buyer's oldest credits first, so a part-paid bill stays open
for the rest, with its own due date.
"""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from ugharani import db
from ugharani.speech import rupees

UPCOMING_DAYS = 3
MONTHS = ["જાન્યુઆરી", "ફેબ્રુઆરી", "માર્ચ", "એપ્રિલ", "મે", "જૂન",
          "જુલાઈ", "ઑગસ્ટ", "સપ્ટેમ્બર", "ઑક્ટોબર", "નવેમ્બર", "ડિસેમ્બર"]


@dataclass
class OpenCredit:
    entry_id: int
    buyer: str
    amount: int  # still unpaid, rupees
    due_date: date


def open_credits(conn: sqlite3.Connection) -> list[OpenCredit]:
    """Unpaid credits after each buyer's payments settle their oldest credits first."""
    paid = defaultdict(int)
    credits = []
    for row in db.list_entries(conn):  # id order = oldest first
        if row["kind"] == "payment":
            paid[row["buyer"]] += row["amount"]
        else:
            credits.append(OpenCredit(row["id"], row["buyer"], row["amount"], date.fromisoformat(row["due_date"])))
    still_open = []
    for credit in credits:
        settled = min(credit.amount, paid[credit.buyer])
        paid[credit.buyer] -= settled
        credit.amount -= settled
        if credit.amount:
            still_open.append(credit)
    return still_open


def status(due: date, today: date) -> str | None:
    if due < today:
        return "overdue"
    if due == today:
        return "today"
    if (due - today).days <= UPCOMING_DAYS:
        return "upcoming"
    return None


def due_items(conn: sqlite3.Connection, today: date) -> list[dict]:
    """Overdue, due today and due within UPCOMING_DAYS, most urgent first."""
    return [
        {"entry_id": c.entry_id, "buyer": c.buyer, "amount": c.amount,
         "due_date": c.due_date.isoformat(), "status": s}
        for c in sorted(open_credits(conn), key=lambda c: c.due_date)
        if (s := status(c.due_date, today))
    ]


def summary_text(items: list[dict]) -> str:
    """The trader's morning summary, e.g. 'આજે 2 ઉઘરાણી આવવાની છે, કુલ ₹4,10,000.'"""
    sentences = {
        "overdue": "{n} ઉઘરાણીની મુદત વીતી ગઈ છે, કુલ {total}.",
        "today": "આજે {n} ઉઘરાણી આવવાની છે, કુલ {total}.",
        "upcoming": f"આવતા {UPCOMING_DAYS} દિવસમાં {{n}} ઉઘરાણી, કુલ {{total}}.",
    }
    parts = []
    for s, sentence in sentences.items():
        if found := [i for i in items if i["status"] == s]:
            parts.append(sentence.format(n=len(found), total=rupees(sum(i["amount"] for i in found))))
    return " ".join(parts) or "આજે કોઈ ઉઘરાણી બાકી નથી."


def spoken_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


def buyer_reminder(conn: sqlite3.Connection, buyer: str, today: date) -> dict | None:
    """A polite reminder the trader sends a buyer: their open balance and earliest due date."""
    mine = [c for c in open_credits(conn) if c.buyer == buyer]
    if not mine:
        return None
    amount = sum(c.amount for c in mine)
    due = min(c.due_date for c in mine)
    if due < today:
        when = f"{spoken_date(due)}ના રોજ હતી"
    elif due == today:
        when = "આજે છે"
    else:
        when = f"{spoken_date(due)}ના રોજ છે"
    return {
        "buyer": buyer,
        "amount": amount,
        "due_date": due.isoformat(),
        "say": f"નમસ્તે {buyer}, {rupees(amount)}ની ચુકવણીની તારીખ {when}. અનુકૂળતાએ મોકલી આપશો. આભાર.",
    }
