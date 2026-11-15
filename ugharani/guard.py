"""The owner's limits, checked in code on every sentence before the agent says it.

The prompt asks Gemini to stay within them, but a model can still slip: offer a discount, quote a
rate, agree to a date a month away, or say an amount that isn't on any bill. None of that may
reach the customer. A sentence that breaks a rule is replaced by a hand-over to the owner, and the
owner is told why.
"""

import re
from datetime import date, timedelta

from ugharani import dates, extract

# Things she never brings up (the owner decides them, or they're never said at all). Matched on
# words, so "ભાવ" in "ભાવનગર" doesn't count.
NEVER = {
    "discount": ["ડિસ્કાઉન્ટ", "discount", "છૂટ", "કસર", "કમિશન"],
    "interest or penalty": ["વ્યાજ", "interest", "ઇન્ટરેસ્ટ", "પેનલ્ટી", "penalty", "દંડ", "ચાર્જ"],
    "legal threat": ["કોર્ટ", "court", "વકીલ", "કેસ", "લીગલ", "legal", "નોટિસ", "notice", "પોલીસ"],
    "stopping supply": ["સપ્લાય બંધ", "માલ બંધ", "ઓર્ડર બંધ", "બ્લોક", "block"],
    "rate": ["ભાવ", "rate", "રેટ"],
}
# Phrases, not single words: "ઓછું કરી આપીશું" (we'll reduce it), "માફ કરી દઈશું" (we'll waive it,
# but "માફ કરજો" is "sorry"), any percentage but 100 ("સો ટકા" is "definitely").
NEVER_PHRASES = {
    "discount": re.compile(
        r"(?<![\d.])(?!100\b)\d{1,2}(?:\.\d+)?\s*(?:%|ટકા|પર્સન્ટ|percent)"
        r"|(?:ઓછ[ુંાીો]+|કમ)\s+(?:કરી|કર|આપ|ભર|લઈ|લે|દે|ચાલશે)"
        r"|માફ\s*(?:કરી\s*દ|કરીશ|કરીએ|કર\s*દ|થઈ\s*જ|થશે|હો\s*જ)"),
}
# A sentence that hands the topic over ("ડિસ્કાઉન્ટ બાબતે શેઠ તમને ફોન કરશે") may name it.
HANDING_OVER = re.compile(r"ફોન કરશે|ફોન કરી લેશે|વાત કરી લેજો|વાત કરશે|વાત કરી લેશે|કૉલ કરશે|बात कर|फोन कर|ફોન કરેંગે|બાત કર")

AMOUNT = re.compile(r"₹\s?([\d,]+)|([\d,]{4,})\s*(?:રૂપિયા|રૂ\.?|/-)")


SUFFIXES = ("", "માં", "મા", "નો", "ના", "ની", "નું", "ને", "થી", "નુ", "વાળા", "વાળું", "ે", "ો", "s")


def _is(word: str, term: str) -> bool:
    """`word` is `term`, maybe inflected: "કોર્ટમાં", "વ્યાજનું"; but not "ભાવનગર" for "ભાવ"."""
    return word.startswith(term) and word[len(term):] in SUFFIXES


def _amounts(text: str) -> set[int]:
    """Amounts in a sentence of hers: "₹1,20,000", "1,20,000 રૂપિયા", and in words, "75 હજાર",
    "એક લાખ દસ હજાર", "સવા લાખ". (Words only with હજાર/લાખ/કરોડ: "10 તારીખે" is not money.)"""
    found = set()
    for m in AMOUNT.finditer(text):
        digits = (m.group(1) or m.group(2)).replace(",", "")
        if digits.isdigit():
            found.add(int(digits))
    tokens = [t.lower() for t in extract._TOKEN.findall(text)]
    for value, start, end in extract._number_groups(tokens):
        if any((extract._magnitude(t) or 0) >= 1_000 for t in tokens[start:end]):
            found.add(round(value))
    return found


def _numbers(text: str) -> set[int]:
    """Any amounts the customer said: "50,000", "₹50,000", "60 હજાર", "દોઢ લાખ"."""
    tokens = [t.lower() for t in extract._TOKEN.findall(text)]
    return {round(value) for value, _, _ in extract._number_groups(tokens)}


def problem(text: str, settings: dict, customer: dict, history: list[dict], today: date) -> str | None:
    """Why `text` must not be said (for the owner's notes), or None if it's fine."""
    words = re.findall(r"[\w઀-૿]+", text.lower())
    lower = text.lower()
    handing_over = bool(HANDING_OVER.search(text))
    for topic, terms in NEVER.items():
        if any((t in lower if " " in t else any(_is(w, t) for w in words)) for t in terms) and not handing_over:
            return f"she was about to talk about {topic}: {text}"
    for topic, pattern in NEVER_PHRASES.items():
        if pattern.search(lower) and not handing_over:
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

    # Dates: the last part by split_days; past promise_days only for a part, never the whole amount.
    split_by = today + timedelta(days=settings["split_days"])
    promise_by = today + timedelta(days=settings["promise_days"])
    whole = balance in _amounts(text)
    in_parts = _in_parts(text, history, balance)
    for start, until in dates.spans(text, today):
        if until > split_by:
            return f"she was about to agree to {until.isoformat()}, past the {settings['split_days']}-day limit: {text}"
        # (a range like "આવતા અઠવાડિયે" that starts in time can still be narrowed to a day in it)
        if start > promise_by and (whole or not in_parts):
            return (f"she was about to agree to the whole amount on {start.isoformat()}, past the "
                    f"{settings['promise_days']}-day limit: {text}")
    return None


REST = ("બાકીના", "બાકીનું", "બાકીનો", "બાકીની", "અડધા", "અડધું", "હપ્તા", "હપ્તે", "પહેલો હપ્તો")


def _in_parts(text: str, history: list[dict], balance: int) -> bool:
    """Is a part payment being talked about: an amount below the balance, or "the rest"?"""
    for line in [text, *(h["text"] for h in history)]:
        money = _amounts(line) | {n for n in _numbers(line) if n >= 1_000}  # (not "18 તારીખે")
        if any(0 < n < balance for n in money) or any(w in line for w in REST):
            return True
    return False


def instead(settings: dict, customer: dict) -> str:
    """What she says in place of a sentence that broke a rule."""
    return f"એ બાબતે હું {settings['owner_name']}ને વાત કરી દઉં છું, એ તમને ફોન કરશે."
