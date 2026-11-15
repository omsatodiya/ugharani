"""Dates as people say them on the phone, in Gujarati, Hindi (in Gujarati script) and English.

Every mention becomes a span, (earliest, latest): "15 તારીખે" is one day; "આવતા અઠવાડિયે" is
next Monday to Sunday; "આવતા મહિને" is all of next month; "20 દિવસમાં" is today to 20 days on.
The checker blocks a sentence whose latest day is past the owner's limit; the notes can take the
earliest.
"""

import re
from calendar import monthrange
from datetime import date, timedelta

from ugharani import extract
from ugharani.reminders import MONTHS

Span = tuple[date, date]

WEEKDAYS = [  # Monday first, as date.weekday()
    ("સોમવાર", "somvar", "monday"),
    ("મંગળવાર", "મંગલવાર", "mangalvar", "tuesday"),
    ("બુધવાર", "budhvar", "wednesday"),
    ("ગુરુવાર", "ગુરૂવાર", "guruvar", "thursday"),
    ("શુક્રવાર", "shukravar", "friday"),
    ("શનિવાર", "shanivar", "saturday"),
    ("રવિવાર", "ravivar", "sunday"),
]
NEXT = {"આવતા", "આવતે", "આવતી", "આવતો", "અગલે", "અગલા", "અગલી", "next", "aavta", "agle"}
THIS = {"આ", "ઇસ", "ઈસ", "this"}
TOMORROW = {"કાલે", "કાલ", "કલ", "tomorrow", "kale"}
DAY_AFTER = {"પરમ", "પરમદિવસે", "પરસોં", "parmdivse"}
TODAY = {"આજે", "આજ", "today", "aaje"}
WEEK = ("અઠવાડ", "હફ્ત", "હફત", "week", "athvad", "hafta")
MONTH = ("મહિન", "મહીન", "month", "mahin")


def _plain(text: str) -> str:
    return text.lower().replace("ઑ", "ઓ")  # "ઑક્ટોબર" and "ઓક્ટોબર" are both written


MONTH_NAMES = [_plain(m) for m in MONTHS]
DAY_OF_MONTH = re.compile(r"(\d{1,2})\s*(?:તારીખ|તા\.|tarikh)")
DAY_MONTH = re.compile(r"(\d{1,2})\s*(" + "|".join(m[:3] for m in MONTH_NAMES) + r")")


def _month_end(day: date) -> date:
    return day.replace(day=monthrange(day.year, day.month)[1])


def _next_month(day: date) -> date:
    return (day.replace(day=1) + timedelta(days=32)).replace(day=1)


def _calendar_dates(text: str, today: date) -> list[Span]:
    """"5 ડિસેમ્બરે" (a recent past date is a bill's date: next year only if long past) and
    "25 તારીખે" (this month, or next month if the day has gone)."""
    out = []
    for m in DAY_MONTH.finditer(text):
        month = next(i for i, name in enumerate(MONTH_NAMES, 1) if name.startswith(m.group(2)))
        try:
            when = date(today.year, month, int(m.group(1)))
        except ValueError:
            continue
        if when < today - timedelta(days=180):  # "5 જાન્યુઆરી" said in November: next year
            when = when.replace(year=today.year + 1)
        out.append((when, when))
    if out:
        return out
    for m in DAY_OF_MONTH.finditer(text):
        day, year, month = int(m.group(1)), today.year, today.month
        if day < today.day:
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        try:
            out.append((date(year, month, day), date(year, month, day)))
        except ValueError:
            pass
    return out


def _durations(tokens: list[str], today: date) -> list[Span]:
    """"20 દિવસમાં", "ત્રીસ દિવસ", "ત્રણ અઠવાડિયામાં", "બે મહિના": within that long."""
    out = []
    for value, start, end in extract._number_groups(tokens):
        if end >= len(tokens) or any(extract._magnitude(t) for t in tokens[start:end]):
            continue  # not followed by a unit, or money ("50 હજાર")
        unit = tokens[end]
        if unit.startswith(WEEK):
            days = 7 * value
        elif unit.startswith(MONTH):
            days = 30 * value
        elif unit.startswith(("દિવસ", "divas", "day")) or unit in {"દિન", "દિનો", "din"}:
            days = value
        else:
            continue
        out.append((today, today + timedelta(days=round(days))))
    return out


def _counted(tok: str) -> bool:
    """A number ("2", "બે") before "અઠવાડિયા" / "મહિના": a duration, read by _durations."""
    return bool(tok) and (tok[0].isdigit() or extract._number(tok) is not None)


def _relative(tokens: list[str], today: date) -> list[Span]:
    """Weekdays, tomorrow, next week / month, this week / month."""
    out = []
    for i, tok in enumerate(tokens):
        prev = tokens[i - 1] if i else ""
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if tok in TODAY:
            out.append((today, today))
        elif tok in TOMORROW:
            out.append((today + timedelta(days=1),) * 2)
        elif tok in DAY_AFTER:
            out.append((today + timedelta(days=2),) * 2)
        elif (wd := next((n for n, names in enumerate(WEEKDAYS) if tok.startswith(names)), None)) is not None:
            ahead = (wd - today.weekday()) % 7 or 7  # "બુધવારે" said on a Wednesday: next week's
            out.append((today + timedelta(days=ahead),) * 2)
        elif tok.startswith(WEEK) and not _counted(prev):
            monday = today + timedelta(days=7 - today.weekday())
            if prev in NEXT:
                out.append((monday, monday + timedelta(days=6)))
            elif prev in THIS or tok.endswith(("માં", "મા")):  # "આ અઠવાડિયામાં"
                out.append((today, monday - timedelta(days=1)))
        elif tok.startswith(MONTH) and not _counted(prev):
            if prev in NEXT:
                first = _next_month(today)
                out.append((first, _month_end(first)))
            elif prev in THIS or nxt.startswith(("અંત", "આખર", "છેલ્લ")) or tok.startswith("મહિનાના"):
                out.append((today, _month_end(today)))  # "આ મહિને", "મહિનાના અંતે"
    return out


def spans(text: str, today: date) -> list[Span]:
    """Every date the text names, as (earliest, latest)."""
    plain = _plain(text)
    tokens = [t.lower() for t in extract._TOKEN.findall(plain)]
    return _calendar_dates(plain, today) + _durations(tokens, today) + _relative(tokens, today)
