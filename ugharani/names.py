"""Match buyer names across scripts and spellings.

'Rameshbhai', 'રમેશભાઈ' and 'રામેશભાઈ' (an STT vowel slip) should be one buyer.
Names are transliterated to Latin, honorifics dropped, spelling variants smoothed,
then compared by consonant skeleton plus overall similarity.
"""

import re
from difflib import SequenceMatcher

from ugharani.extract import HONORIFICS

_CONSONANTS = {
    "ક": "k", "ખ": "kh", "ગ": "g", "ઘ": "gh", "ઙ": "n",
    "ચ": "ch", "છ": "chh", "જ": "j", "ઝ": "jh", "ઞ": "n",
    "ટ": "t", "ઠ": "th", "ડ": "d", "ઢ": "dh", "ણ": "n",
    "ત": "t", "થ": "th", "દ": "d", "ધ": "dh", "ન": "n",
    "પ": "p", "ફ": "ph", "બ": "b", "ભ": "bh", "મ": "m",
    "ય": "y", "ર": "r", "લ": "l", "ળ": "l", "વ": "v",
    "શ": "sh", "ષ": "sh", "સ": "s", "હ": "h",
}
_VOWELS = {
    "અ": "a", "આ": "aa", "ઇ": "i", "ઈ": "ii", "ઉ": "u", "ઊ": "uu", "ઋ": "ru",
    "એ": "e", "ઐ": "ai", "ઓ": "o", "ઔ": "au", "ઍ": "e", "ઑ": "o",
}
_MATRAS = {
    "ા": "aa", "િ": "i", "ી": "ii", "ુ": "u", "ૂ": "uu", "ૃ": "ru",
    "ે": "e", "ૈ": "ai", "ો": "o", "ૌ": "au", "ૅ": "e", "ૉ": "o",
}
_VIRAMA = "્"
_NASALS = {"ં": "n", "ઁ": "n", "ઃ": "h"}

# Applied in order to both transliterated and romanised names.
_SPELLING = [
    (r"chh", "ch"), (r"f", "ph"), (r"w", "v"), (r"z", "j"), (r"q", "k"),
    (r"aa+", "a"), (r"ee|ii", "i"), (r"oo|uu", "u"),
    (r"([^aeiou])\1", r"\1"),  # Bhatt -> Bhat
]
_HONORIFIC_TAIL = re.compile(rf"\s*({'|'.join(HONORIFICS)}|ji|જી)$")


def transliterate(text: str) -> str:
    """Gujarati script -> rough Latin. Inherent 'a' is kept except at word end."""
    text = text.replace("઼", "")  # nukta
    out = []
    for i, ch in enumerate(text):
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
            word_end = not nxt.strip()
            if nxt not in _MATRAS and nxt != _VIRAMA and not word_end:
                out.append("a")  # inherent vowel
        elif ch != _VIRAMA:
            out.append(_MATRAS.get(ch) or _VOWELS.get(ch) or _NASALS.get(ch) or ch)
    return "".join(out)


def normalize(name: str) -> str:
    """Comparable Latin form: 'Raameshbhai' and 'રમેશભાઈ' both become 'ramesh'."""
    name = _HONORIFIC_TAIL.sub("", name.strip().lower())
    name = transliterate(name)
    name = re.sub(r"[^a-z]", "", name)
    for pattern, repl in _SPELLING:
        name = re.sub(pattern, repl, name)
    return name


def _skeleton(norm: str) -> str:
    return re.sub(r"[aeiou]", "", norm)


def similarity(a: str, b: str) -> float:
    """0..1; 0 unless the consonant skeletons match exactly."""
    na, nb = normalize(a), normalize(b)
    if not na or _skeleton(na) != _skeleton(nb):
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def match(name: str, known: list[str], threshold: float = 0.75) -> str | None:
    """Return the known buyer that `name` refers to, or None if it's a new buyer."""
    best = max(known, key=lambda k: similarity(name, k), default=None)
    return best if best is not None and similarity(name, best) >= threshold else None
