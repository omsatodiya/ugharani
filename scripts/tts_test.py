"""Timbre smoke test: synthesize a Gujarati sentence via the SSE endpoint and save a WAV.

Usage: uv run python scripts/tts_test.py [--text "..."] [--out out/tts_test.wav]
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from ugharani.config import get_settings
from ugharani.gnani import TTS_SAMPLE_RATE, GnaniError, synthesize

# Gujarati script: with language=gu-IN, romanised text risks being read as English.
DEFAULT_TEXT = "રમેશભાઈ, તમારા ₹2,40,000 બાકી છે."


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Gujarati + ₹ on Windows consoles
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--out", type=Path, default=Path("out/tts_test.wav"))
    args = parser.parse_args()

    s = get_settings()
    print(f"TTS {s.tts_model}/{s.tts_voice} [{s.language}]: {args.text}")
    start = time.perf_counter()
    try:
        wav = asyncio.run(synthesize(args.text))
    except GnaniError as e:
        raise SystemExit(str(e))
    total = time.perf_counter() - start

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(wav)
    duration = (len(wav) - 44) / (TTS_SAMPLE_RATE * 2)  # minus the WAV header
    print(f"Saved {args.out} ({duration:.2f}s audio)")
    print(f"Total time: {total * 1000:.0f} ms")


if __name__ == "__main__":
    main()
