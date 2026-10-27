"""What Ugharani says out loud: Timbre clips, cached on disk by sentence.

Every clip costs Timbre credits, so the same sentence is only ever synthesised once.
"""

import hashlib
from datetime import date
from pathlib import Path

from ugharani import gnani
from ugharani.config import audio_cache_dir, tts_model, tts_voice
from ugharani.extract import ParsedEntry


def clip_key(text: str) -> str:
    """Stable key for a sentence in the current voice; also its file name."""
    return hashlib.sha256(f"{tts_model()}/{tts_voice()}\n{text}".encode()).hexdigest()[:16]


def clip_path(key: str) -> Path:
    return Path(audio_cache_dir()) / f"{key}.wav"


async def speak(text: str) -> str:
    """Synthesise `text` unless it is already cached; return its clip key."""
    key = clip_key(text)
    path = clip_path(key)
    if not path.exists():
        wav = await gnani.synthesize(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav)
    return key


def rupees(amount: int) -> str:
    """Indian digit grouping, which Timbre reads as lakh/hazaar: 240000 -> '₹2,40,000'."""
    head, tail = str(amount)[:-3], str(amount)[-3:]
    groups = []
    while len(head) > 2:
        head, groups = head[:-2], [head[-2:], *groups]
    return "₹" + ",".join([g for g in [head, *groups] if g] + [tail])


# Asked one field at a time, so a short answer like '60 દિવસ' fills it.
QUESTIONS = {
    ("credit", "buyer"): "કોને માલ આપ્યો?",
    ("payment", "buyer"): "કોણે પૈસા આપ્યા?",
    ("credit", "amount"): "કેટલા રૂપિયાનો માલ?",
    ("payment", "amount"): "કેટલા રૂપિયા જમા થયા?",
    ("credit", "due_date"): "કેટલા દિવસની મુદત?",
}


def question(entry: ParsedEntry) -> str | None:
    """The follow-up question for the first missing field, or None if nothing is missing."""
    return QUESTIONS[(entry.kind, entry.missing[0])] if entry.missing else None


def _to(name: str) -> str:
    """'રમેશભાઈને', but 'Rameshbhai ને': a suffix glued to Latin script reads badly."""
    return f"{name} ને" if name.isascii() else f"{name}ને"


def readback(entry: ParsedEntry, today: date) -> str:
    """Repeat a complete entry back to the trader before it is saved."""
    if entry.kind == "payment":
        return f"{entry.buyer} પાસેથી {rupees(entry.amount)} જમા. બરાબર?"
    days = (entry.due_date - today).days
    return f"{_to(entry.buyer)} {rupees(entry.amount)}નો માલ, {days} દિવસની મુદત. બરાબર?"


def reply(entry: ParsedEntry, today: date) -> str:
    """What to say after a recording: the next question, or the read-back."""
    return question(entry) or readback(entry, today)
