"""Rule-based extraction of a ledger entry from a Gujarati/Hinglish transcript.

Handles Prisma output (Gujarati script, ITN digits like ₹2,40,000) and romanised
text ("Rameshbhai ne be lakh chaalis hazaar nu maal aapyu, saath divas").
An LLM can replace `parse` later; callers only depend on ParsedEntry.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from ugharani import clock

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
    **dict.fromkeys(["das", "દસ", "દશ"], 10),
    **dict.fromkeys(["agiyar", "અગિયાર"], 11),
    **dict.fromkeys(["bar", "baar", "બાર"], 12),
    **dict.fromkeys(["pandar", "pandara", "પંદર"], 15),
    **dict.fromkeys(["vees", "vis", "bees", "વીસ"], 20),
    **dict.fromkeys(["ekvees", "એકવીસ"], 21),
    **dict.fromkeys(["pachis", "pachchis", "પચીસ", "પચ્ચીસ"], 25),
    **dict.fromkeys(["trees", "tees", "ત્રીસ"], 30),
    **dict.fromkeys(["pantrees", "પાંત્રીસ"], 35),
    **dict.fromkeys(["chalis", "chaalis", "chaalees", "ચાળીસ", "ચાલીસ"], 40),
    **dict.fromkeys(["pistalis", "પિસ્તાળીસ", "પિસ્તાલીસ"], 45),
    **dict.fromkeys(["pachas", "pachaas", "પચાસ"], 50),
    **dict.fromkeys(["sath", "saath", "saith", "સાઠ", "સાઈઠ", "સાંઈઠ", "સાઇઠ"], 60),
    **dict.fromkeys(["sittar", "sitter", "સિત્તેર"], 70),
    **dict.fromkeys(["panchoter", "પંચોતેર"], 75),
    **dict.fromkeys(["ensi", "assi", "એંસી"], 80),
    **dict.fromkeys(["nevu", "nevun", "નેવું", "નેવુ"], 90),
    # English, as Prisma sometimes writes it in Gujarati script ('ફિફ્ટી'). Not 'થ્રી' and
    # other single digits: Prisma writes 'થ્રી' for a misheard 'ત્રીસ', and asking again
    # beats silently saving 3 days.
    **dict.fromkeys(["one"], 1), **dict.fromkeys(["two"], 2), **dict.fromkeys(["three"], 3),
    **dict.fromkeys(["four"], 4), **dict.fromkeys(["five"], 5),
    **dict.fromkeys(["ten", "ટેન"], 10), **dict.fromkeys(["fifteen", "ફિફ્ટીન"], 15),
    **dict.fromkeys(["twenty", "ટ્વેન્ટી"], 20), **dict.fromkeys(["thirty", "થર્ટી"], 30),
    **dict.fromkeys(["forty", "ફોર્ટી"], 40), **dict.fromkeys(["fifty", "ફિફ્ટી"], 50),
    **dict.fromkeys(["sixty", "સિક્સ્ટી"], 60), **dict.fromkeys(["ninety", "નાઈન્ટી", "નાઇન્ટી"], 90),
    **dict.fromkeys(["dodh", "dedh", "દોઢ"], 1.5),
    **dict.fromkeys(["adhi", "dhai", "અઢી"], 2.5),
}
# Every Gujarati number 1-99 (they are irregular, so a table), with common spellings, and Hindi as
# Prisma writes it in Gujarati script. Added to NUMBER_WORDS where not already there.
_GUJARATI_1_99 = """
1 એક|2 બે|3 ત્રણ|4 ચાર|5 પાંચ|6 છ|7 સાત|8 આઠ|9 નવ|10 દસ દશ|11 અગિયાર અગ્યાર|12 બાર|13 તેર|14 ચૌદ|
15 પંદર|16 સોળ|17 સત્તર|18 અઢાર|19 ઓગણીસ|20 વીસ|21 એકવીસ|22 બાવીસ|23 તેવીસ ત્રેવીસ|24 ચોવીસ|
25 પચ્ચીસ પચીસ|26 છવ્વીસ છવીસ|27 સત્તાવીસ સત્યાવીસ|28 અઠ્ઠાવીસ અઠ્યાવીસ|29 ઓગણત્રીસ|30 ત્રીસ|
31 એકત્રીસ|32 બત્રીસ|33 તેત્રીસ|34 ચોત્રીસ|35 પાંત્રીસ|36 છત્રીસ|37 સાડત્રીસ|38 આડત્રીસ|
39 ઓગણચાલીસ|40 ચાલીસ ચાળીસ|41 એકતાલીસ|42 બેતાલીસ|43 તેતાલીસ|44 ચુંમાલીસ ચુમ્માલીસ|
45 પિસ્તાલીસ પિસ્તાળીસ|46 છેતાલીસ|47 સુડતાલીસ|48 અડતાલીસ|49 ઓગણપચાસ|50 પચાસ|51 એકાવન|52 બાવન|
53 ત્રેપન|54 ચોપન|55 પંચાવન|56 છપ્પન|57 સત્તાવન|58 અઠ્ઠાવન|59 ઓગણસાઠ|60 સાઠ સાઈઠ સાંઈઠ સાઇઠ|
61 એકસઠ|62 બાસઠ|63 ત્રેસઠ|64 ચોસઠ|65 પાંસઠ|66 છાસઠ|67 સડસઠ|68 અડસઠ|69 અગણોસિત્તેર ઓગણસિત્તેર|
70 સિત્તેર|71 એકોતેર|72 બોતેર|73 તોંતેર|74 ચુમોતેર|75 પંચોતેર|76 છોતેર|77 સિત્યોતેર|78 ઇઠ્યોતેર|
79 ઓગણએંસી|80 એંસી એંશી અસી અંશી|81 એક્યાસી|82 બ્યાસી|83 ત્યાસી|84 ચોર્યાસી|85 પંચાસી|86 છ્યાસી|
87 સિત્યાસી|88 અઠ્યાસી ઈઠ્યાસી|89 નેવ્યાસી|90 નેવું નેવુ|91 એકાણું|92 બાણું|93 ત્રાણું|94 ચોરાણું|
95 પંચાણું|96 છન્નું|97 સત્તાણું|98 અઠ્ઠાણું|99 નવ્વાણું|
2 દો|3 તીન|6 છહ|9 નૌ|11 ગ્યારહ|12 બારહ|13 તેરહ|14 ચૌદહ|15 પંદ્રહ પંદરહ|16 સોલહ|17 સત્રહ|18 અઠારહ|19 ઉન્નીસ|20 બીસ|
25 પચ્ચીસ|30 તીસ|40 ચાલીસ|50 પચાસ|60 સાઠ|80 અસ્સી|90 નબ્બે
"""
for _entry in _GUJARATI_1_99.replace("\n", "").split("|"):
    if _entry.strip():
        _value, *_words = _entry.split()
        for _word in _words:
            NUMBER_WORDS.setdefault(_word, int(_value))

MAGNITUDES = {
    **dict.fromkeys(["so", "sau", "સો"], 100),
    **dict.fromkeys(["hazar", "hazaar", "hajar", "hajaar", "thousand", "હજાર", "થાઉઝન્ડ"], 1_000),
    **dict.fromkeys(["lakh", "lac", "laakh", "લાખ"], 100_000),
    **dict.fromkeys(["crore", "karod", "કરોડ"], 10_000_000),
}
# 'સાડા ત્રણ લાખ' = 3.5 lakh, 'સવા' adds a quarter, 'પોણા' takes one off
FRACTION_WORDS = {
    **dict.fromkeys(["sada", "saada", "સાડા", "સાડાં"], 0.5),
    **dict.fromkeys(["sava", "savaa", "સવા"], 0.25),
    **dict.fromkeys(["pona", "pauna", "પોણા"], -0.25),
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


def _magnitude(tok: str) -> int | None:
    """'હજાર', and inflected 'હજારનો' / 'લાખનું' / 'lakhnu'."""
    return MAGNITUDES.get(tok) or MAGNITUDES.get(re.sub(r"(નો|ના|નું|ની|nu|no|na|ni)$", "", tok))


def _split_itn(value: float, magnitude: int) -> float:
    """Prisma's ITN sometimes half-converts 'બે લાખ ચાલીસ હજાર' to '2,00,040 હજાર'.

    A number already at least as big as the word after it holds the smaller part
    in its low digits: 2,00,040 હજાર -> 2,00,000 + 40 x 1,000.
    """
    if value < magnitude:
        return value * magnitude
    low = value % magnitude
    return value - low + low * magnitude


# Hindi as Prisma writes it: "દિન" only as whole words ("દિનેશભાઈ" is a name), "હફ્તે" (a week)
HINDI_DURATIONS = {"દિન": 1, "દિનો": 1, "દિનોં": 1, "દિનમેં": 1}


def _duration_unit(tok: str) -> int | None:
    if tok in HINDI_DURATIONS:
        return HINDI_DURATIONS[tok]
    if tok.startswith(("હફ્ત", "હફત")):
        return 7
    return next((days for stem, days in DURATION_STEMS.items() if tok.startswith(stem)), None)


def _number_groups(tokens: list[str]) -> list[tuple[float, int, int]]:
    """Find numbers like '2,40,000', '2.4 lakh', 'be lakh chaalis hazaar'.

    Returns (value, start, end) token spans; tokens[end] is the token after the number.
    Number *words* only count next to a magnitude or duration unit, because
    'saath' also means 'with' and 'be' / 'so' are common words.
    """
    groups, i = [], 0
    while i < len(tokens):
        fraction = FRACTION_WORDS.get(tokens[i]) if i + 1 < len(tokens) else None
        if fraction is not None and _magnitude(tokens[i + 1]):
            val = 1 + fraction  # 'સવા લાખ' = 1.25 lakh; tokens[i] stands in for the number
        else:
            val = _number(tokens[i + 1] if fraction is not None else tokens[i])
            if val is None:
                i += 1
                continue
        start = i
        if fraction is not None and not _magnitude(tokens[i + 1]):  # 'સાડા ત્રણ' = 3.5
            val, i = val + fraction, i + 1
        is_digit = tokens[i][0].isdigit()
        total, chunk, used_magnitude, last_mag = 0.0, val, False, 0
        i += 1
        while i < len(tokens):
            if mag := _magnitude(tokens[i]):
                total += _split_itn(chunk, mag) if tokens[i - 1][0].isdigit() else chunk * mag
                chunk, used_magnitude, last_mag = 0.0, True, mag
                i += 1
            elif (
                used_magnitude and chunk == 0 and _number(tokens[i]) is not None
                and i + 1 < len(tokens) and _magnitude(tokens[i + 1])
            ):
                chunk = _number(tokens[i])  # 'be lakh chaalis hazaar'
                i += 1
            elif (
                used_magnitude and chunk == 0 and tokens[i][0].isdigit() and 100 <= _number(tokens[i]) < last_mag
                and not (i + 1 < len(tokens) and _duration_unit(tokens[i + 1]))  # not '2 lakh, 60 divas'
            ):
                chunk = _number(tokens[i])  # ITN: '5 લાખ 50,000'
                i += 1
                break
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
        # 'કાંતાબેને' is કાંતાબેન + the ે sign, not + ને, so try dropping just the sign too.
        stripped = _CASE_SUFFIX.sub("", tok)
        name = next((n for n in (tok, stripped, tok.removesuffix("ે")) if n.endswith(HONORIFICS)), stripped)
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
    today = today or clock.today()
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
    """Apply a follow-up recording to a draft: an answer ('60 divas') or a fix ('ના, સાઠ દિવસ').

    Whatever the new recording says wins, so a misheard field is fixed by saying
    just that field again. The draft's kind is kept: a bare answer always parses as a credit.
    """
    buyer = answer.buyer or draft.buyer
    amount = answer.amount if answer.amount is not None else draft.amount
    due_days, due_date = draft.due_days, draft.due_date
    if draft.kind == "credit" and answer.due_date is not None:
        due_days, due_date = answer.due_days, answer.due_date
    return ParsedEntry(
        kind=draft.kind,
        buyer=buyer,
        amount=amount,
        due_days=due_days,
        due_date=due_date,
        missing=missing_fields(draft.kind, buyer, amount, due_date),
    )
