"""Rule-based extraction of a ledger entry from a Gujarati/Hinglish transcript.

Handles Prisma output (Gujarati script, ITN digits like ₹2,40,000) and romanised
text ("Rameshbhai ne be lakh chaalis hazaar nu maal aapyu, saath divas").
An LLM can replace `parse` later; callers only depend on ParsedEntry.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

# A number (ASCII or Gujarati digits, Indian/Western commas), ₹, or a run of non-separators.
_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?|₹|[^\s\d,.!?।:;\"'₹]+")

NUMBER_WORDS = {
    **dict.fromkeys(["ek", "એક"], 1),
    **dict.fromkeys(["be", "do", "બે"], 2),
    **dict.fromkeys(["tran", "teen", "ત્રણ"], 3),
    **dict.fromkeys(["char", "chaar", "ચાર"], 4),
    **dict.fromkeys(["panch", "paanch", "પાંચ"], 5),
    **dict.fromkeys(["chha", "છ"], 6),
    **dict.fromkeys(["saat", "સાત"], 7),
    **dict.fromkeys(["aath", "આઠ"], 8),
    **dict.fromkeys(["nav", "nau", "નવ"], 9),
    **dict.fromkeys(["das", "દસ"], 10),
    **dict.fromkeys(["pandar", "pandara", "પંદર"], 15),
    **dict.fromkeys(["vees", "vis", "bees", "વીસ"], 20),
    **dict.fromkeys(["pachis", "pachchis", "પચીસ", "પચ્ચીસ"], 25),
    **dict.fromkeys(["trees", "tees", "ત્રીસ"], 30),
    **dict.fromkeys(["chalis", "chaalis", "chaalees", "ચાળીસ", "ચાલીસ"], 40),
    **dict.fromkeys(["pachas", "pachaas", "પચાસ"], 50),
    **dict.fromkeys(["sath", "saath", "સાઠ"], 60),
    **dict.fromkeys(["sittar", "sitter", "સિત્તેર"], 70),
    **dict.fromkeys(["ensi", "assi", "એંસી"], 80),
    **dict.fromkeys(["nevu", "nevun", "નેવું"], 90),
    **dict.fromkeys(["dodh", "dedh", "દોઢ"], 1.5),
    **dict.fromkeys(["adhi", "dhai", "અઢી"], 2.5),
}
MAGNITUDES = {
    **dict.fromkeys(["so", "sau", "સો"], 100),
    **dict.fromkeys(["hazar", "hazaar", "hajar", "hajaar", "હજાર"], 1_000),
    **dict.fromkeys(["lakh", "lac", "laakh", "લાખ"], 100_000),
    **dict.fromkeys(["crore", "karod", "કરોડ"], 10_000_000),
}
# Stems, so inflections like મહિને / મહિનામાં / divase still match.
DURATION_STEMS = {
    "divas": 1, "din": 1, "day": 1, "દિવસ": 1,
    "athvad": 7, "hafta": 7, "week": 7, "અઠવાડ": 7,
    "mahin": 30, "month": 30, "મહિન": 30,
}
NEXT_WORDS = {"aavta", "avta", "agle", "next", "આવતા", "આવતે"}
CURRENCY_BEFORE = {"₹", "rs", "inr"}
CURRENCY_AFTER = ("rupiy", "rupay", "rupee", "રૂપિય", "રૂ")
PAYMENT_STEMS = ("jama", "જમા", "chukav", "ચૂકવ", "ચુકવ", "bhary", "ભર્ય", "maly", "મળ્ય", "received", "paid")
HONORIFICS = ("bhai", "ben", "behen", "sheth", "ભાઈ", "ભાઇ", "બેન", "બહેન", "શેઠ")
_CASE_SUFFIX = re.compile(r"(ને|નો|ના|નું|ની|એ|ne|no|na|nu|ni|e)$")
OBJECT_MARKERS = {"ne", "ને", "ko"}  # "Rameshbhai ne ... aapyu": I gave to him
AGENT_MARKERS = {"e", "એ"}  # "Rameshbhai e ... aapya": he gave to me


@dataclass
class ParsedEntry:
    kind: str  # "credit" (goods given on udhaar) or "payment" (money received)
    buyer: str | None
    amount: int | None
    due_days: int | None
    due_date: date | None
    missing: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing


def _number(tok: str) -> float | None:
    if tok[0].isdigit():
        return float(tok.replace(",", ""))
    return NUMBER_WORDS.get(tok)


def _duration_unit(tok: str) -> int | None:
    return next((days for stem, days in DURATION_STEMS.items() if tok.startswith(stem)), None)


def _number_groups(tokens: list[str]) -> list[tuple[float, int, int]]:
    """Find numbers like '2,40,000', '2.4 lakh', 'be lakh chaalis hazaar'.

    Returns (value, start, end) token spans; tokens[end] is the token after the number.
    Number *words* only count next to a magnitude or duration unit, because
    'saath' also means 'with' and 'be' / 'so' are common words.
    """
    groups, i = [], 0
    while i < len(tokens):
        val = _number(tokens[i])
        if val is None:
            i += 1
            continue
        start, is_digit = i, tokens[i][0].isdigit()
        total, chunk, used_magnitude = 0.0, val, False
        i += 1
        while i < len(tokens):
            if tokens[i] in MAGNITUDES:
                total += chunk * MAGNITUDES[tokens[i]]
                chunk, used_magnitude = 0.0, True
                i += 1
            elif (
                used_magnitude and chunk == 0 and _number(tokens[i]) is not None
                and i + 1 < len(tokens) and tokens[i + 1] in MAGNITUDES
            ):
                chunk = _number(tokens[i])  # 'be lakh chaalis hazaar'
                i += 1
            else:
                break
        total += chunk
        unit_follows = i < len(tokens) and _duration_unit(tokens[i]) is not None
        if is_digit or used_magnitude or unit_follows:
            groups.append((total, start, i))
    return groups


def _display(name: str) -> str:
    return name.title() if name.isascii() else name


def _find_buyer(tokens: list[str]) -> str | None:
    for i, tok in enumerate(tokens):
        name = tok if tok.endswith(HONORIFICS) else _CASE_SUFFIX.sub("", tok)
        if name in HONORIFICS and i > 0 and _number(tokens[i - 1]) is None:
            return _display(f"{tokens[i - 1]} {name}")  # 'Patel sheth', 'Ramesh bhai'
        if any(name.endswith(h) and len(name) > len(h) for h in HONORIFICS):
            return _display(name)
    for prev, tok in zip(tokens, tokens[1:]):
        if tok in OBJECT_MARKERS | AGENT_MARKERS and _number(prev) is None:
            return _display(prev)
    return None


def _is_payment(tokens: list[str]) -> bool:
    if any(t.startswith(PAYMENT_STEMS) for t in tokens):
        return True
    agent = any(t in AGENT_MARKERS or t.endswith(("ભાઈએ", "ભાઇએ", "બેને", "bhaie")) for t in tokens)
    obj = any(t in OBJECT_MARKERS or t.endswith(("ભાઈને", "ભાઇને", "બેનને", "bhaine")) for t in tokens)
    return agent and not obj


def parse(transcript: str, today: date | None = None) -> ParsedEntry:
    today = today or date.today()
    tokens = [t.lower() for t in _TOKEN.findall(transcript)]

    due_days = None
    candidates = []  # (has_currency, value): prefer ₹-marked, then the largest
    for value, start, end in _number_groups(tokens):
        after = tokens[end] if end < len(tokens) else ""
        if unit := _duration_unit(after):
            due_days = round(value * unit)
            continue
        before = tokens[start - 1] if start else ""
        candidates.append((before in CURRENCY_BEFORE or after.startswith(CURRENCY_AFTER), value))
    amount = round(max(candidates)[1]) if candidates else None

    if due_days is None:  # 'aavta mahine' = next month
        for prev, tok in zip(tokens, tokens[1:]):
            if prev in NEXT_WORDS and (unit := _duration_unit(tok)):
                due_days = unit

    kind = "payment" if _is_payment(tokens) else "credit"
    if kind == "payment":
        due_days = None
    buyer = _find_buyer(tokens)

    due_date = today + timedelta(days=due_days) if due_days is not None else None
    return ParsedEntry(
        kind=kind,
        buyer=buyer,
        amount=amount,
        due_days=due_days,
        due_date=due_date,
        missing=missing_fields(kind, buyer, amount, due_date),
    )


def missing_fields(kind: str, buyer: str | None, amount: int | None, due_date: date | None) -> list[str]:
    missing = [name for name, val in (("buyer", buyer), ("amount", amount)) if val is None]
    if kind == "credit" and due_date is None:
        missing.append("due_date")
    return missing


def merge(draft: ParsedEntry, answer: ParsedEntry) -> ParsedEntry:
    """Fill a draft's missing fields from a follow-up answer ('60 divas', 'Rameshbhai').

    Fields the draft already has are kept, and so is its kind: a bare answer
    always parses as a credit.
    """
    buyer = draft.buyer or answer.buyer
    amount = draft.amount if draft.amount is not None else answer.amount
    due_days, due_date = draft.due_days, draft.due_date
    if draft.kind == "credit" and due_date is None:
        due_days, due_date = answer.due_days, answer.due_date
    return ParsedEntry(
        kind=draft.kind,
        buyer=buyer,
        amount=amount,
        due_days=due_days,
        due_date=due_date,
        missing=missing_fields(draft.kind, buyer, amount, due_date),
    )
