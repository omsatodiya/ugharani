"""Sample ledger for demos, dated relative to today so something is always due.

Seeded today, the summary reads: 1 due today (₹1,20,000) and 1 due in 2 days (₹75,000).
"""

import sqlite3
from datetime import date, timedelta

from ugharani import db
from ugharani.extract import parse

# (transcript, days before today it was recorded)
SAMPLE = [
    ("રમેશભાઈ ને ₹1,00,000 નો માલ, 20 દિવસ", 30),   # paid off below
    ("રમેશભાઈ ને ₹1,40,000 નો માલ, 30 દિવસ", 30),   # due today, part-paid
    ("કાંતાબેન ને ₹75,000 નો માલ, 32 દિવસ", 30),    # due in 2 days
    ("મહેશભાઈ ને ₹50,000 નો માલ, 60 દિવસ", 10),     # due later
    ("રમેશભાઈએ ₹1,20,000 જમા કરાવ્યા", 0),
]


def seed(conn: sqlite3.Connection, today: date | None = None) -> int:
    """Add the sample entries to an empty ledger. Returns how many were added."""
    if db.list_entries(conn):
        return 0
    today = today or date.today()
    for text, days_ago in SAMPLE:
        on = today - timedelta(days=days_ago)
        db.add_entry(conn, parse(text, today=on), text, today=on)
    return len(SAMPLE)
