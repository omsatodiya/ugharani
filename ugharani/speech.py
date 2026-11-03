"""What Ugharani says out loud: Timbre clips, cached on disk by sentence.

Every clip costs Timbre credits, so the same sentence is only ever synthesised once.
"""

import hashlib
import wave
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

from ugharani import gnani
from ugharani.config import audio_cache_dir, tts_model, tts_speed, tts_voice
from ugharani.extract import ParsedEntry


def clip_key(text: str) -> str:
    """Stable key for a sentence in the current voice and speed; also its file name."""
    voice = tts_voice() if tts_speed() == 1.0 else f"{tts_voice()}@{tts_speed()}"  # (old keys stay valid)
    return hashlib.sha256(f"{tts_model()}/{voice}\n{text}".encode()).hexdigest()[:16]


# Clips shipped with the app (fixed sentences), so a fresh server's empty cache doesn't re-pay for them.
BUNDLED_DIR = Path(__file__).parent / "clips"


def clip_path(key: str) -> Path:
    bundled = BUNDLED_DIR / f"{key}.wav"
    return bundled if bundled.exists() else Path(audio_cache_dir()) / f"{key}.wav"


async def speak(text: str) -> str:
    """Synthesise `text` unless it is already cached or bundled; return its clip key."""
    key = clip_key(text)
    if not clip_path(key).exists():
        wav = await gnani.synthesize(text)
        path = Path(audio_cache_dir()) / f"{key}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav)
    return key


def _save(key: str, pcm: bytes) -> None:
    path = Path(audio_cache_dir()) / f"{key}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gnani._wav(pcm))


def cached_pcm(text: str) -> bytes | None:
    """The sentence's raw 16 kHz PCM if it was synthesised before, else None (costs nothing)."""
    path = clip_path(clip_key(text))
    if not path.exists():
        return None
    try:
        with wave.open(str(path), "rb") as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (gnani.TTS_SAMPLE_RATE, 1, 2):
                return None  # not a clip this app made
            return w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return None


async def _raw_pcm(text: str) -> AsyncIterator[bytes]:
    if (pcm := cached_pcm(text)) is not None:
        yield pcm
        return
    made = bytearray()
    async for chunk in gnani.synthesize_stream(text):
        made += chunk
        yield chunk
    _save(clip_key(text), bytes(made))


WINDOW = 640          # 20 ms of 16 kHz PCM16
VOICED_RMS = 400      # about -38 dBFS: quieter than this is silence or line noise
VOICED_RUN = 3        # 60 ms of sound in a row is speech; a lone click isn't
LEAD_KEEP = 4 * WINDOW   # 80 ms before the first word
TAIL_KEEP = 8 * WINDOW   # 160 ms after the last word: a natural end, not a gap
# Timbre pauses ~0.55-0.6 s at every comma and full stop, in every voice: reads like a script.
# People chatting on the phone pause ~0.2-0.3 s between short sentences.
MAX_PAUSE = 14 * WINDOW  # 280 ms


def _voiced(window: bytes) -> bool:
    samples = memoryview(window).cast("h")
    return (sum(s * s for s in samples) / len(samples)) ** 0.5 > VOICED_RMS


async def trimmed(chunks: AsyncIterator[bytes], max_pause: int | None = MAX_PAUSE) -> AsyncIterator[bytes]:
    """Drop Timbre's silence before the first word and after the last (up to ~1 s, sometimes with a
    click), and shorten pauses inside to `max_pause` bytes: both sound like reading, not talking."""
    buf = bytearray()      # bytes not yet cut into windows
    pending = bytearray()  # windows since the last confirmed speech: a pause, or the trailing silence
    run, started = 0, False
    async for chunk in chunks:
        buf += chunk
        while len(buf) >= WINDOW:
            window, buf = bytes(buf[:WINDOW]), buf[WINDOW:]
            pending += window
            run = run + 1 if _voiced(window) else 0
            if run >= VOICED_RUN:
                if not started:  # keep only a breath before the first word
                    started = True
                    pending = pending[-(VOICED_RUN * WINDOW + LEAD_KEEP):]
                elif max_pause is not None:  # a pause between words: no longer than max_pause
                    pause = len(pending) - VOICED_RUN * WINDOW  # (the last windows are the new word)
                    if pause > max_pause:
                        keep_end = max_pause // 2 // WINDOW * WINDOW  # end of the last word, then
                        del pending[keep_end:keep_end + pause - max_pause]  # the run-up to the next
                yield bytes(pending)
                pending = bytearray()
            elif not started and len(pending) > LEAD_KEEP + VOICED_RUN * WINDOW:
                del pending[:WINDOW]  # leading silence: never sent
    if started:
        yield bytes(pending[:TAIL_KEEP])


async def stream_pcm(text: str) -> AsyncIterator[bytes]:
    """Say `text` on a call: the cached clip at once, or Timbre's audio as it streams (then cached),
    without the silence around it."""
    async for chunk in trimmed(_raw_pcm(text)):
        yield chunk


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
