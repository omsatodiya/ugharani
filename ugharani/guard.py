"""The owner's limits, checked in code on every sentence before the agent says it.

The prompt asks Gemini to stay within them, but a model can still slip: offer a discount, quote a
rate, agree to a date a month away, or say an amount that isn't on any bill. None of that may
reach the customer. A sentence that breaks a rule is replaced by a hand-over to the owner, and the
owner is told why.
"""

import asyncio
import logging
import re
from datetime import date, timedelta

from ugharani import dates, extract, llm
from ugharani.lang.gu import (CURRENCY, HALF, HANDING_OVER, NEVER, NEVER_PHRASES, OFFER, REST,  # noqa: F401
                               SUFFIXES, WHOLE)

log = logging.getLogger("uvicorn.error")

# Topics the owner may discuss, so she may say the owner will call about them. Threats and
# stopping supply are never said, handed over or not.
HANDED_OVER_TOPICS = {"discount", "interest or penalty", "rate"}

AMOUNT = re.compile(r"₹\s?([\d,]+)|([\d,]+)\s*(?:રૂપિયા|રૂ\.|રૂ\b|/-|rupees|rs\b)"
                    r"|(?<![\d,])(\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?![\d,])")  # "1,50,000", "100,000"


def _is(word: str, term: str) -> bool:
    """`word` is `term`, maybe inflected: "કોર્ટમાં", "વ્યાજનું"; but not "ભાવનગર" for "ભાવ"."""
    return word.startswith(term) and word[len(term):] in SUFFIXES


def _amounts(text: str) -> set[int]:
    """Amounts in a sentence of hers: "₹1,20,000", "1,20,000 રૂપિયા", and in words, "75 હજાર",
    "એક લાખ દસ હજાર", "સવા લાખ". (Words only with હજાર/લાખ/કરોડ: "10 તારીખે" is not money.)"""
    found = set()
    for m in AMOUNT.finditer(text):
        digits = (m.group(1) or m.group(2) or m.group(3)).replace(",", "")
        if digits.isdigit():
            found.add(int(digits))
    tokens = [t.lower() for t in extract._TOKEN.findall(text)]
    for value, start, end in extract._number_groups(tokens):
        if any((extract._magnitude(t) or 0) >= 1_000 for t in tokens[start:end]):
            found.add(round(value))
    for word, nxt in zip(tokens, tokens[1:]):  # "અઢાર રૂપિયા", "પચાસ રૂપિયા"
        value = extract.NUMBER_WORDS.get(word)
        if isinstance(value, int) and nxt.startswith(CURRENCY):
            found.add(value)
    return found


def _numbers(text: str) -> set[int]:
    """Any amounts the customer said: "50,000", "₹50,000", "60 હજાર", "દોઢ લાખ"."""
    tokens = [t.lower() for t in extract._TOKEN.findall(text)]
    return {round(value) for value, _, _ in extract._number_groups(tokens)}


def problem(text: str, settings: dict, customer: dict, history: list[dict], today: date) -> str | None:
    """Why `text` must not be said (for the owner's notes), or None if it's fine."""
    words = re.findall(r"[\w઀-૿]+", text.lower())
    lower = text.lower()
    handing_over = bool(HANDING_OVER.search(text)) and not OFFER.search(text)
    for topic, terms in NEVER.items():
        named = any((t in lower if " " in t else any(_is(w, t) for w in words)) for t in terms)
        if named and not (handing_over and topic in HANDED_OVER_TOPICS):
            return f"she was about to talk about {topic}: {text}"
    for topic, pattern in NEVER_PHRASES.items():
        # ("માફ કરી દઉં", "ઓછું કરી આપીશું" are offers in themselves: a hand-over clause beside them
        # doesn't take them back, unlike the bare word "ડિસ્કાઉન્ટ" in "ડિસ્કાઉન્ટ બાબતે શેઠ ફોન કરશે")
        if pattern.search(lower):
            return f"she was about to talk about {topic}: {text}"

    # Amounts: what's owed, a bill, what the customer said, or what's left after it.
    balance = customer["balance"]
    known = {balance, *(b["amount"] for b in customer.get("bills", []))}
    said = set().union(*(_numbers(h["text"]) for h in history if h["who"] == "customer"), set())
    if any(w in h["text"] for h in history if h["who"] == "customer" for w in HALF):
        said.add(balance // 2)  # "અડધું દસ દિવસમાં": she may say the half as ₹60,000
    known |= said | {balance - n for n in said if 0 < n < balance}
    known |= set().union(*(_amounts(h["text"]) for h in history if h["who"] == "agent"), set())
    for amount in _amounts(text):
        if amount not in known:
            return f"she was about to say an amount that is on no bill: {text}"

    # Dates: the last part by split_days; past promise_days only for a part, never the whole amount.
    split_by = today + timedelta(days=settings["split_days"])
    promise_by = today + timedelta(days=settings["promise_days"])
    named = _amounts(text)
    # the whole amount: named (or "પૂરા પૈસા"), but not as the source of a smaller part
    # ("₹1,20,000 માંથી ₹50,000 કાલે")
    whole = (balance in named or bool(WHOLE.search(text))) and not any(0 < n < balance for n in named)
    in_parts = _in_parts(text, history, balance)
    for start, until in dates.spans(text, today):
        if until > split_by:
            return f"she was about to agree to {until.isoformat()}, past the {settings['split_days']}-day limit: {text}"
        # A range like "આવતા અઠવાડિયે" that starts in time can still be narrowed to a day in it,
        # unless the whole amount is meant: then its last day counts ("બાર તારીખ સુધીમાં પૂરા પૈસા").
        if (until if whole else start) > promise_by and (whole or not in_parts):
            return (f"she was about to agree to the whole amount on {start.isoformat()}, past the "
                    f"{settings['promise_days']}-day limit: {text}")
    return None


def _in_parts(text: str, history: list[dict], balance: int) -> bool:
    """Is a part payment being talked about: an amount below the balance, or "the rest"?

    Only money ("₹50,000", "50 હજાર", "50,000"), not any number ("UTR 4528", "18 તારીખે"); and not
    her mention of a bill ("₹50,000 વાળું બિલ 20 ઑક્ટોબરનું છે"), which is no payment plan."""
    for line, earlier in [(text, False), *((h["text"], h["who"] == "agent") for h in history)]:
        if any(w in line for w in REST):
            return True
        if earlier and "બિલ" in line:  # (her earlier mention of a bill; this sentence's plan counts)
            continue
        if any(0 < n < balance for n in _amounts(line)):
            return True
    return False


# ---------- after the call: a second opinion on what words can't pin down ----------

# Threats, stopping supply and discounts can be said in endless ways ("ટ્રેલર રવાના નહીં થાય",
# "લાયસન્સ રદ", "રાઉન્ડ ઓફ"); the word lists above catch the common ones as she speaks. Checking
# every sentence with Gemini before it is said was measured on the free tier (Nov 2026): a median
# 2.3 s, often 8 s, so it would slow every reply. Instead, after the call Gemini reads all her lines
# at once (one request) and anything it finds goes to the owner, who can call and correct it.
AUDIT_TIMEOUT = 60.0
AUDIT_TOPICS = ["discount", "threat", "supply"]
AUDIT_SCHEMA = {
    "type": "object",
    "properties": {"found": {"type": "array", "items": {
        "type": "object",
        "properties": {"line": {"type": "integer"}, "topic": {"type": "string", "enum": AUDIT_TOPICS}},
        "required": ["line", "topic"]}}},
    "required": ["found"],
}
AUDIT_PROMPT = """You check what an AI agent said on a payment-reminder phone call for a Gujarat \
pipe-fittings company (Gujarati, Hindi written in Gujarati script, or mixed). You get her lines, \
numbered. List every line that breaks one of these rules, with the rule; an empty list if none:
- discount: offers, agrees to or hints at paying less, a discount, waiving or reducing any part, \
rounding off, settling for less, cash discount, any concession on the amount
- threat: legal action, court, lawyer, police, complaints against them, notices, damaging their \
name or reputation, ending the relationship, any pressure or scare tactic
- supply: stopping, holding, cancelling or delaying their goods, orders, dispatch, delivery, \
dealership or account until they pay
Not breaking: asking for a date or amount, confirming a payment plan, payment modes, apologising \
("માફ કરજો"), saying the owner or a colleague will call about a discount, rate or dispute without \
promising anything, noting their complaint, sending a statement on WhatsApp, greetings. Dates and \
amounts are checked elsewhere: ignore them."""


async def audit(lines: list[str], strict: bool = False) -> list[str]:
    """Her lines from one call, read by Gemini: what the owner should know about, or [] (none, or
    no answer: the audit is a second opinion, its failure changes nothing). `strict`: raise when
    there is no answer instead (an evaluation must not count an outage as "found nothing")."""
    if not lines:
        return []
    numbered = "\n".join(f"{n}. {line}" for n, line in enumerate(lines, 1))
    try:
        out = await asyncio.wait_for(
            llm.generate_json(AUDIT_PROMPT, [{"who": "customer", "text": numbered}], AUDIT_SCHEMA),
            timeout=AUDIT_TIMEOUT)
    except (TimeoutError, llm.LLMError) as e:
        if strict:
            raise
        log.warning("audit: no answer (%s)", type(e).__name__)
        return []
    found = []
    for item in out.get("found", []) if isinstance(out, dict) else []:
        n, topic = item.get("line"), item.get("topic")
        if isinstance(n, int) and 1 <= n <= len(lines) and topic in AUDIT_TOPICS:
            found.append(f"{topic}: {lines[n - 1]}")
    return found


def instead(settings: dict, customer: dict) -> str:
    """What she says in place of a sentence that broke a rule."""
    return f"એ બાબતે હું {settings['owner_name']}ને વાત કરી દઉં છું, એ તમને ફોન કરશે."
