"""Voice lines for the launch video (video/), as trimmed 16 kHz WAVs plus their durations.

    uv run python scripts/video_audio.py            # uses cached/bundled clips; makes missing ones

Kavya speaks in Tarika's voice (bundled clips where they exist), the dealer in Avinash's. Every
new line costs one Timbre request once; the result is cached in out/ and copied to video/public.
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from ugharani import gnani, speech  # noqa: E402

OUT = Path("video/public/audio")
DEALER_CACHE = Path("out/customer_voice")
DEALER = "Avinash"

# name: (who, text)
LINES = {
    "k_hello": ("kavya", "હેલો રમેશભાઈ?"),
    "c_ha_bolo": ("dealer", "હા, બોલો."),
    "k_intro": ("kavya", "હા નમસ્તે. હું કાવ્યા બોલું છું જીનિયસ પોલીપ્લાસ્ટમાંથી."),
    "k_ask": ("kavya", "₹1,20,000 નું પેમેન્ટ બાકી છે, ઑક્ટોબરનું બિલ છે, એ ક્યારે મોકલશો?"),
    "c_discount": ("dealer", "થોડું ડિસ્કાઉન્ટ આપો તો શુક્રવારે અડધા આપી દઉં."),
    "k_handover": ("kavya", "એ બાબતે હું શેઠને વાત કરી દઉં છું, એ તમને ફોન કરશે."),
    "k_rest": ("kavya", "તો શુક્રવારે ₹60,000, અને બાકીના ક્યારે?"),
    "c_rest": ("dealer", "બાકીના 14 તારીખે, RTGS કરી દઈશ."),
    "k_confirm": ("kavya", "તો શુક્રવારે ₹60,000 અને 14 તારીખે ₹60,000 RTGS, બરાબર ને?"),
    "c_yes": ("dealer", "હા, બરાબર."),
    "k_bye": ("kavya", "સારું, આભાર રમેશભાઈ. આવજો."),
}


async def kavya(text: str) -> bytes:
    return b"".join([c async for c in speech.stream_pcm(text)])  # cached or bundled, else 1 request


async def dealer(text: str) -> bytes:
    DEALER_CACHE.mkdir(parents=True, exist_ok=True)
    path = DEALER_CACHE / f"{DEALER}-{hashlib.sha256(text.encode()).hexdigest()[:12]}.pcm"
    if not path.exists():
        print(f"  (Timbre, {DEALER}) {text}")
        path.write_bytes(b"".join([c async for c in gnani.synthesize_stream(text, voice=DEALER)]))
    return b"".join([c async for c in speech.trimmed(_once(path.read_bytes()))])


async def _once(pcm: bytes):
    yield pcm


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    durations = {}
    for name, (who, text) in LINES.items():
        pcm = await (kavya(text) if who == "kavya" else dealer(text))
        (OUT / f"{name}.wav").write_bytes(gnani._wav(pcm))
        durations[name] = {"who": who, "text": text, "seconds": round(len(pcm) / 32000, 3)}
        print(f"{name:12s} {durations[name]['seconds']:5.2f}s  {text}")
    Path("video/src/lines.json").parent.mkdir(parents=True, exist_ok=True)
    Path("video/src/lines.json").write_text(json.dumps(durations, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
