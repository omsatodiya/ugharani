"""Sample ledger for demos, dated relative to today so something is always due.

Seeded today, the summary reads: 1 due today (₹1,20,000) and 1 due in 2 days (₹75,000).
"""

import json
import sqlite3
from datetime import date, datetime, time, timedelta

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


# Calls Kavya made in the last few days, so a fresh demo already shows outcomes, notes and the
# owner's to-do list. (days ago, hh:mm, customer, amount due, status, notes, conversation)
CALLS = [
    (5, "11:20", "કાંતાબેન", 75000, "missed", None, []),
    (4, "16:45", "રમેશભાઈ", 140000, "completed", {
        "outcome": "callback", "summary": "દુકાનમાં ગ્રાહક હતા, બે-ત્રણ દિવસમાં ફરી ફોન કરવાનું કહ્યું.",
    }, [("agent", "હેલો રમેશભાઈ?"), ("customer", "હા, બોલો."),
        ("agent", "હા નમસ્તે. હું કાવ્યા બોલું છું જીનિયસ પોલીપ્લાસ્ટમાંથી. પેમેન્ટ બાબતે ફોન કર્યો હતો."),
        ("customer", "અત્યારે ગ્રાહક છે, પછી ફોન કરજો."), ("agent", "સારું, વાંધો નહીં. આવજો.")]),
    (3, "12:10", "મહેશભાઈ", 50000, "completed", {
        "outcome": "handover", "summary": "વહેલું પેમેન્ટ કરે તો 2% ડિસ્કાઉન્ટ માગે છે. કાવ્યાએ હા ન પાડી, શેઠ ફોન કરશે એમ કહ્યું.",
        "owner_action": "મહેશભાઈએ 2% ડિસ્કાઉન્ટ માગ્યું છે: તમે ફોન કરો.",
        "flags": ["she was about to talk about discount: તો 2% ડિસ્કાઉન્ટ આપી દઈએ."],
    }, [("agent", "હેલો મહેશભાઈ?"), ("customer", "હા બોલો."),
        ("agent", "હા નમસ્તે. હું કાવ્યા બોલું છું જીનિયસ પોલીપ્લાસ્ટમાંથી. ₹50,000 નું પેમેન્ટ ક્યારે આવશે?"),
        ("customer", "અઠવાડિયામાં આપી દઉં, પણ 2% ડિસ્કાઉન્ટ આપો."),
        ("agent", "એ બાબતે હું શેઠને વાત કરી દઉં છું, એ તમને ફોન કરશે. આવજો.")]),
    (1, "10:35", "કાંતાબેન", 75000, "completed", {
        "outcome": "promised", "summary": "મુદતના દિવસે ₹75,000 RTGS કરી દેશે.",
        "promised_amount": 75000, "promised_in": 2, "payment_mode": "RTGS",
    }, [("agent", "હેલો કાંતાબેન?"), ("customer", "હા બોલો."),
        ("agent", "હા નમસ્તે. હું કાવ્યા બોલું છું જીનિયસ પોલીપ્લાસ્ટમાંથી. ₹75,000 ની મુદત આવે છે, એ ક્યારે મોકલશો?"),
        ("customer", "મુદતના દિવસે RTGS કરી દઈશ."), ("agent", "સારું. તો RTGS, બરાબર ને?"),
        ("customer", "હા."), ("agent", "સારું, આભાર કાંતાબેન. આવજો.")]),
]


def seed_calls(conn: sqlite3.Connection, today: date) -> None:
    """Add the sample calls (only to a call log that is still empty)."""
    if followup.list_calls(conn, limit=1):
        return
    for days_ago, hhmm, customer, due, status, notes, turns in CALLS:
        when = datetime.combine(today - timedelta(days=days_ago), time.fromisoformat(hhmm))
        call_id = followup.start_call(conn, customer, due, "auto", when=when)
        transcript = [{"who": who, "text": text} for who, text in turns]
        if notes is None:
            followup.set_status(conn, call_id, status)
            continue
        promised = today + timedelta(days=notes["promised_in"]) if notes.get("promised_in") else None
        followup.finish_call(conn, call_id, transcript=transcript, outcome=notes["outcome"],
                             summary=notes["summary"], promised_amount=notes.get("promised_amount"),
                             promised_date=promised, owner_action=notes.get("owner_action"),
                             payment_mode=notes.get("payment_mode"))
        conn.execute("UPDATE calls SET flags = ?, ended_at = ? WHERE id = ?",
                     (json.dumps(notes.get("flags", []), ensure_ascii=False),
                      (when + timedelta(minutes=2)).isoformat(timespec="seconds"), call_id))
    conn.commit()


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
    seed_calls(conn, today)
    return len(SAMPLE)
