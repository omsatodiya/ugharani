"""Make the same call lines in several Timbre voices / speeds, to choose one by ear.

    uv run python scripts/voice_samples.py                       # default set (12 Timbre requests)
    uv run python scripts/voice_samples.py Riyaa@1.05 Tarika@1.0 # voice@speed options of your own

Writes out/voice_samples/<voice>@<speed>-<n>.wav, trimmed like on a call, plus index.html to play
them side by side. Each sample is a paid Timbre request; files that exist are not made again.
"""

import asyncio
import hashlib
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from ugharani import gnani, speech  # noqa: E402

LINES = [
    "હેલો રમેશભાઈ?",
    "હા નમસ્તે. હું કાવ્યા બોલું છું જીનિયસ પોલીપ્લાસ્ટમાંથી. કૉલ રેકોર્ડ થાય છે હં.",
    "જી. તમારું ₹1,20,000 નું પેમેન્ટ બાકી છે, તો એ ક્યારે મોકલશો?",
]
DEFAULT = ["Shivani@1.0", "Riyaa@1.0", "Tarika@1.0", "Kalpana@1.0"]
OUT = Path("out/voice_samples")


async def trimmed(pcm: bytes) -> bytes:
    async def once():
        yield pcm
    return b"".join([c async for c in speech.trimmed(once())])


async def main(options: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    made = 0
    rows = []
    for option in options:
        voice, _, speed = option.partition("@")
        speed = float(speed or 1.0)
        cells = []
        for n, text in enumerate(LINES, 1):
            key = hashlib.sha256(text.encode()).hexdigest()[:6]
            path = OUT / f"{voice}@{speed}-{n}-{key}.wav"
            if not path.exists():
                pcm = b"".join([c async for c in gnani.synthesize_stream(text, voice=voice, speed=speed)])
                path.write_bytes(gnani._wav(await trimmed(pcm)))
                made += 1
                print(f"made {path.name}")
            cells.append(f'<td><audio controls preload="none" src="{path.name}"></audio></td>')
        rows.append(f"<tr><th>{html.escape(voice)} · {speed}</th>{''.join(cells)}</tr>")
    heads = "".join(f"<th>{n}. {html.escape(t)}</th>" for n, t in enumerate(LINES, 1))
    (OUT / "index.html").write_text(f"""<!doctype html><meta charset="utf-8">
<title>Kavya voice samples</title>
<style>body{{font-family:system-ui,"Noto Sans Gujarati",sans-serif;margin:24px}}
table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:8px;text-align:left;vertical-align:top}}
th{{max-width:260px;font-weight:600}}</style>
<h1>કાવ્યા: which voice?</h1>
<p>Same lines, each voice. Listen as if you are the dealer picking up the phone.</p>
<table><tr><th>Voice · speed</th>{heads}</tr>{''.join(rows)}</table>
""", encoding="utf-8")
    print(f"{made} Timbre requests; open {OUT.resolve() / 'index.html'}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or DEFAULT))
