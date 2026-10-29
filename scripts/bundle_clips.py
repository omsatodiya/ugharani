"""Copy the clips of fixed sentences into ugharani/clips/, which ships with the app.

A free host wipes its disk on every restart; bundled clips mean a fresh server
doesn't pay Timbre again for sentences it always says.

Usage: uv run python scripts/bundle_clips.py [--synthesize]
  --synthesize   make missing clips with Timbre (1 paid call each); default only copies cached ones
"""

import argparse
import asyncio
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from ugharani import db, reminders, speech
from ugharani.seed import seed


def fixed_sentences() -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        conn = db.connect(str(Path(tmp) / "seed.db"))
        seed(conn, today=date.today())
        summary = reminders.summary_text(reminders.due_items(conn, date.today()))
        conn.close()
    return [summary, reminders.summary_text([]), *speech.QUESTIONS.values()]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Gujarati on Windows consoles
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthesize", action="store_true")
    args = parser.parse_args()

    sentences = fixed_sentences()
    missing = [s for s in sentences if not speech.clip_path(speech.clip_key(s)).exists()]
    if missing and args.synthesize:
        print(f"Synthesising {len(missing)} clips ({len(missing)} Timbre calls)")
        for s in missing:
            asyncio.run(speech.speak(s))

    speech.BUNDLED_DIR.mkdir(exist_ok=True)
    for s in sentences:
        key = speech.clip_key(s)
        src, dst = speech.clip_path(key), speech.BUNDLED_DIR / f"{key}.wav"
        if src == dst:
            print(f"bundled   {s}")
        elif src.exists():
            shutil.copy(src, dst)
            print(f"copied    {s}")
        else:
            print(f"MISSING   {s}")


if __name__ == "__main__":
    main()
