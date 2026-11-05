"""The owner's limits, checked in code on every sentence before the agent says it.

The prompt asks Gemini to stay within them, but a model can still slip: offer a discount, quote a
rate, agree to a date a month away, or say an amount that isn't on any bill. None of that may
reach the customer. A sentence that breaks a rule is replaced by a hand-over to the owner, and the
owner is told why.
"""

import re
from datetime import date, timedelta

from ugharani import extract
from ugharani.reminders import MONTHS

# Things she never brings up (the owner decides them, or they're never said at all). Matched on
# words, so "ભાવ" in "ભાવનગર" doesn't count.
NEVER = {
    "discount": ["ડિસ્કાઉન્ટ", "discount", "છૂટ", "કસર", "કમિશન"],
    "interest or penalty": ["વ્યાજ", "interest", "ઇન્ટરેસ્ટ", "પેનલ્ટી", "penalty", "દંડ", "ચાર્જ"],
    "legal threat": ["કોર્ટ", "court", "વકીલ", "કેસ", "લીગલ", "legal", "નોટિસ", "notice", "પોલીસ"],
    "stopping supply": ["સપ્લાય બંધ", "માલ બંધ", "ઓર્ડર બંધ", "બ્લોક", "block"],
    "rate": ["ભાવ", "rate", "રેટ"],
}
# A sentence that hands the topic over ("ડિસ્કાઉન્ટ બાબતે શેઠ તમને ફોન કરશે") may name it.
HANDING_OVER = re.compile(r"ફોન કરશે|ફોન કરી લેશે|વાત કરી લેજો|વાત કરશે|વાત કરી લેશે|કૉલ કરશે|बात कर|फोन कर|ફોન કરેંગે|બાત કર")

AMOUNT = re.compile(r"₹\s?([\d,]+)|([\d,]{4,})\s*(?:રૂપિયા|રૂ\.?|/-)")
DAY_OF_MONTH = re.compile(r"(\d{1,2})\s*(?:તારીખ|તા\.)")
DAY_MONTH = re.compile(r"(\d{1,2})\s*(" + "|".join(m[:3] for m in MONTHS) + r")")
IN_DAYS = re.compile(r"(\d{1,2})\s*(?:દિવસ|दिन|દિન)")


SUFFIXES = ("", "માં", "મા", "નો", "ના", "ની", "નું", "ને", "થી", "નુ", "વાળા", "વાળું", "ે", "ો", "s")


def _is(word: str, term: str) -> bool:
    """`word` is `term`, maybe inflected: "કોર્ટમાં", "વ્યાજનું"; but not "ભાવનગર" for "ભાવ"."""
    return word.startswith(term) and word[len(term):] in SUFFIXES


def _amounts(text: str) -> set[int]:
    found = set()
    for m in AMOUNT.finditer(text):
        digits = (m.group(1) or m.group(2)).replace(",", "")
        if digits.isdigit():
            found.add(int(digits))
    return found


def _numbers(text: str) -> set[int]:
    """Any amounts the customer said: "50,000", "₹50,000", "60 હજાર", "દોઢ લાખ"."""
    tokens = [t.lower() for t in extract._TOKEN.findall(text)]
    return {round(value) for value, _, _ in extract._number_groups(tokens)}


def _dates(text: str, today: date) -> list[date]:
    """Dates the sentence names: "25 તારીખે" (this month, or next if past), "5 ડિસેમ્બરે", "20 દિવસમાં"."""
    out = []
    for m in DAY_MONTH.finditer(text):
        month = next(i for i, name in enumerate(MONTHS, 1) if name.startswith(m.group(2)))
        try:
            when = date(today.year, month, int(m.group(1)))
        except ValueError:
            continue
        if when < today - timedelta(days=180):  # "5 જાન્યુઆરી" said in November: next year
            when = when.replace(year=today.year + 1)
        out.append(when)  # (a recent past date is a bill's date, never past the limit)
    if not out:
        for m in DAY_OF_MONTH.finditer(text):
            day = int(m.group(1))
            year, month = today.year, today.month
            if day < today.day:
                year, month = (year + 1, 1) if month == 12 else (year, month + 1)
            try:
                out.append(date(year, month, day))
            except ValueError:
                pass
    for m in IN_DAYS.finditer(text):
        out.append(today + timedelta(days=int(m.group(1))))
    return out


def problem(text: str, settings: dict, customer: dict, history: list[dict], today: date) -> str | None:
    """Why `text` must not be said (for the owner's notes), or None if it's fine."""
    words = re.findall(r"[\w઀-૿]+", text.lower())
    lower = text.lower()
    handing_over = bool(HANDING_OVER.search(text))
    for topic, terms in NEVER.items():
        if any((t in lower if " " in t else any(_is(w, t) for w in words)) for t in terms) and not handing_over:
            return f"she was about to talk about {topic}: {text}"

    # Amounts: what's owed, a bill, what the customer said, or what's left after it.
    balance = customer["balance"]
    known = {balance, *(b["amount"] for b in customer.get("bills", []))}
    said = set().union(*(_numbers(h["text"]) for h in history if h["who"] == "customer"), set())
    known |= said | {balance - n for n in said if 0 < n < balance}
    known |= set().union(*(_amounts(h["text"]) for h in history if h["who"] == "agent"), set())
    for amount in _amounts(text):
        if amount not in known:
            return f"she was about to say an amount that is on no bill: {text}"

    latest = today + timedelta(days=settings["split_days"])
    for when in _dates(text, today):
        if when > latest:
            return f"she was about to agree to {when.isoformat()}, past the {settings['split_days']}-day limit: {text}"
    return None


def instead(settings: dict, customer: dict) -> str:
    """What she says in place of a sentence that broke a rule."""
    return f"એ બાબતે હું {settings['owner_name']}ને વાત કરી દઉં છું, એ તમને ફોન કરશે."
