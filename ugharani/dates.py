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

AFTER = {"પછી", "પછીથી", "બાદ", "બાદમાં", "after", "pachhi"}      # "દિવાળી પછી": no end
BEFORE = {"પહેલાં", "પહેલા", "પેલા", "પહેલે", "before"}             # "દિવાળી પહેલાં": by then
BY = {"સુધી", "સુધીમાં", "તક", "until", "by"}                       # "15 તારીખ સુધી": by then
CONNECTORS = {"કે", "ના", "ની", "નો"}                                 # "દિવાળી કે બાદ"
OPEN = date.max  # "after X": no latest day

# Festivals traders date payments by. Lunar dates move each year; from Gujarati calendars, to
# within a day (sources differ by one), which is close enough for a limit. Extend every year: a
# festival with no date ahead counts as open-ended, so a sentence naming it is never let through.
FESTIVALS = {
    "diwali": ["2026-11-08", "2027-10-29"],
    "new_year": ["2026-11-10", "2027-10-30"],      # બેસતું વર્ષ
    "labh_pancham": ["2026-11-14", "2027-11-03"],
    "dev_diwali": ["2026-11-24", "2027-11-13"],
    "uttarayan": ["2026-01-14", "2027-01-14", "2028-01-14"],
    "holi": ["2026-03-04", "2027-03-22"],          # ધુળેટી
    "raksha_bandhan": ["2026-08-28", "2027-08-17"],
    "janmashtami": ["2026-09-04", "2027-08-25"],
    "navratri": ["2026-10-11", "2027-09-30"],
}
FESTIVAL_WORDS = {  # stems; the word may be inflected ("દિવાળીએ", "હોળીમાં")
    "diwali": ("દિવાળી", "દીવાળી", "દિવાલી", "દીવાલી", "diwali"),
    "uttarayan": ("ઉત્તરાયણ", "ઉતરાયણ", "સંક્રાંતિ", "સંક્રાંત", "uttarayan"),
    "holi": ("હોળી", "હોલી", "ધુળેટી", "ધૂળેટી", "holi"),
    "raksha_bandhan": ("રક્ષાબંધન", "બળેવ", "રાખડી", "rakhi"),
    "janmashtami": ("જન્માષ્ટમી", "janmashtami"),
    "navratri": ("નવરાત્રી", "નવરાત્રિ", "નોરતા", "navratri"),
}
FESTIVAL_AFTER_WORD = {  # two words: (first, stem of the second)
    ("દેવ", "દિવાળી"): "dev_diwali", ("લાભ", "પાંચમ"): "labh_pancham",
    ("બેસતું", "વર્ષ"): "new_year", ("બેસતા", "વર્ષ"): "new_year", ("નવા", "વર્ષ"): "new_year",
}
DATE_SUFFIXES = ("એ", "ે", "માં", "મા")  # "દિવાળીએ", "હોળીમાં" ("દિવાળીના દિવસે" below)


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
        out.append(_bounded((when, when), _after_match(text, m), today))
    if out:
        return out
    for m in DAY_OF_MONTH.finditer(text):
        day, year, month = int(m.group(1)), today.year, today.month
        if day < today.day:
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        try:
            when = date(year, month, day)
        except ValueError:
            continue
        out.append(_bounded((when, when), _after_match(text, m), today))
    return out


def _after_match(text: str, m: re.Match) -> list[str]:
    """The words after a regex match, without the rest of the matched word ("તારીખ|ે પછી")."""
    rest = text[m.end():]
    words = _tokens(rest)
    return words[1:] if rest[:1].strip() and words else words


def _cue(following: list[str]) -> str | None:
    """The word that bounds a date mention ("પછી", "પહેલાં", "સુધી"), if one comes next."""
    words = following[1:2] if following[:1] and following[0] in CONNECTORS else following[:1]
    word = words[0] if words else ""
    return "after" if word in AFTER else "before" if word in BEFORE else "by" if word in BY else None


def _bounded(span: Span, following: list[str], today: date) -> Span:
    cue = _cue(following)
    if cue == "after":
        return (span[1], OPEN)
    if cue == "before":
        return (min(today, span[0]), span[0])
    if cue == "by":
        return (min(today, span[1]), span[1])
    return span


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in extract._TOKEN.findall(text)]


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
        when = today + timedelta(days=round(days))
        if _cue(tokens[end + 1:]) == "after":  # "7 દિવસ પછી": in everyday speech, on day 7
            out.append((when, when))
        else:
            out.append(_bounded((today, when), tokens[end + 1:], today))
    return out


def _counted(tok: str) -> bool:
    """A number ("2", "બે") before "અઠવાડિયા" / "મહિના": a duration, read by _durations."""
    return bool(tok) and (tok[0].isdigit() or extract._number(tok) is not None)


def _relative_span(tok: str, prev: str, nxt: str, today: date) -> Span | None:
    """One word (with its neighbours) as a date: weekdays, tomorrow, next week / month, this
    week / month."""
    if tok in TODAY:
        return (today, today)
    if tok in TOMORROW:
        return (today + timedelta(days=1),) * 2
    if tok in DAY_AFTER:
        return (today + timedelta(days=2),) * 2
    if (wd := next((n for n, names in enumerate(WEEKDAYS) if tok.startswith(names)), None)) is not None:
        ahead = (wd - today.weekday()) % 7 or 7  # "બુધવારે" said on a Wednesday: next week's
        return (today + timedelta(days=ahead),) * 2
    if tok.startswith(WEEK) and not _counted(prev):
        monday = today + timedelta(days=7 - today.weekday())
        if prev in NEXT:
            return (monday, monday + timedelta(days=6))
        if prev in THIS or tok.endswith(("માં", "મા")):  # "આ અઠવાડિયામાં"
            return (today, monday - timedelta(days=1))
    if tok.startswith(MONTH) and not _counted(prev):
        if prev in NEXT:
            first = _next_month(today)
            return (first, _month_end(first))
        if prev in THIS or nxt.startswith(("અંત", "આખર", "છેલ્લ")) or tok.startswith("મહિનાના"):
            return (today, _month_end(today))  # "આ મહિને", "મહિનાના અંતે"
    return None


def _month_alone(tok: str, prev: str, today: date) -> Span | None:
    """A month named without a day ("જાન્યુઆરીમાં"): all of it; this year's if this month or
    recent, else next year's. ("5 ડિસેમ્બર", with the day, is read by _calendar_dates.)"""
    if prev[:1].isdigit():
        return None
    month = next((i for i, name in enumerate(MONTH_NAMES, 1) if len(name) > 2 and tok.startswith(name)), None)
    if month is None:
        return None
    first = date(today.year, month, 1)
    if first < today.replace(day=1) - timedelta(days=180):
        first = first.replace(year=today.year + 1)
    end = _month_end(first)
    return (first if end < today else max(first, today), end)  # (a past month: a bill's)


def _relative(tokens: list[str], today: date) -> list[Span]:
    out = []
    for i, tok in enumerate(tokens):
        prev = tokens[i - 1] if i else ""
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if span := _relative_span(tok, prev, nxt, today) or _month_alone(tok, prev, today):
            out.append(_bounded(span, tokens[i + 1:], today))
    return out


def _festival_day(name: str, today: date) -> date | None:
    """The festival's date nearest today ("દિવાળી પછી" a week after Diwali means that Diwali)."""
    days = [date.fromisoformat(d) for d in FESTIVALS[name]]
    near = [d for d in days if abs((d - today).days) <= 183]
    return min(near, key=lambda d: abs((d - today).days)) if near else None


def _festivals(tokens: list[str], today: date) -> list[Span]:
    """"દિવાળી પછી", "હોળી પહેલાં", "ઉત્તરાયણ પર", "દિવાળીએ"; not "દિવાળીની શુભકામનાઓ"."""
    out = []
    for i, tok in enumerate(tokens):
        prev = tokens[i - 1] if i else ""
        name = next((n for (first, second), n in FESTIVAL_AFTER_WORD.items()
                     if prev == first and tok.startswith(second)), None)
        stem = None
        if name:
            stem = next(second for (first, second), n in FESTIVAL_AFTER_WORD.items()
                        if n == name and tok.startswith(second))
        else:
            for n, stems in FESTIVAL_WORDS.items():
                stem = next((st for st in stems if tok.startswith(st)), None)
                if stem:
                    name = n
                    break
        if not name:
            continue
        suffix, following = tok[len(stem):], tokens[i + 1:]
        on_the_day = suffix in ("ના", "ની") and following[:1] and following[0].startswith("દિવસ")
        if not (suffix in DATE_SUFFIXES or on_the_day or _cue(following) or following[:1] in (["પર"], ["ઉપર"])):
            continue  # named, but not as a date
        day = _festival_day(name, today)
        out.append(_bounded((day, day), following, today) if day else (today, OPEN))
    return out


def spans(text: str, today: date) -> list[Span]:
    """Every date the text names, as (earliest, latest)."""
    plain = _plain(text)
    tokens = _tokens(plain)
    return (_calendar_dates(plain, today) + _durations(tokens, today) + _relative(tokens, today)
            + _festivals(tokens, today))
