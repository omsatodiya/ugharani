"""Sample ledger for demos, dated relative to today so something is always due.

Seeded today, the summary reads: 1 due today (₹1,20,000) and 1 due in 2 days (₹75,000).
"""

import sqlite3
from datetime import date, timedelta

from ugharani import db, followup
from ugharani.extract import parse

# (transcript, days before today it was recorded)
SAMPLE = [
    ("રમેશભાઈ ને ₹1,00,000 નો માલ, 20 દિવસ", 30),   # paid off below
    ("રમેશભાઈ ને ₹1,40,000 નો માલ, 30 દિવસ", 30),   # due today, part-paid
    ("કાંતાબેન ને ₹75,000 નો માલ, 32 દિવસ", 30),    # due in 2 days
    ("મહેશભાઈ ને ₹50,000 નો માલ, 60 દિવસ", 10),     # due later
    ("રમેશભાઈએ ₹1,20,000 જમા કરાવ્યા", 0),
]
# Genius Polyplast (Gondal) makes pipe fittings and valves; its buyers are hardware and
# sanitary dealers around Saurashtra. Firms are made up; numbers are demo-only (98000 0000x),
# since calls happen in the browser and nothing is dialled.
CONTACTS = [
    # (person, firm, city, phone, deals with at Genius Polyplast)
    ("રમેશભાઈ", "શ્રીજી હાર્ડવેર", "જેતપુર", "9800000001", "મનીષભાઈ"),
    ("કાંતાબેન", "ખોડિયાર સેનિટરી", "જૂનાગઢ", "9800000002", "મનીષભાઈ"),
    ("મહેશભાઈ", "ઉમિયા પાઇપ સેન્ટર", "મોરબી", "9800000003", "રાજુભાઈ"),
]


def seed(conn: sqlite3.Connection, today: date | None = None) -> int:
    """Add the sample entries to an empty ledger. Returns how many were added."""
    if db.list_entries(conn):
        return 0
    today = today or date.today()
    for text, days_ago in SAMPLE:
        on = today - timedelta(days=days_ago)
        db.add_entry(conn, parse(text, today=on), text, today=on)
    for name, firm, city, phone, deals_with in CONTACTS:
        followup.upsert_customer(conn, name, phone=phone, deals_with=deals_with, firm=firm, city=city)
    return len(SAMPLE)
