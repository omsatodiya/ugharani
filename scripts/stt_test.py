"""Prisma smoke test: transcribe a file via REST with ITN on, and check the amount survived.

Usage: uv run python scripts/stt_test.py [audio_file] [--expect 240000]
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from ugharani.amounts import find_amounts
from ugharani.config import get_settings
from ugharani.gnani import GnaniError, transcribe


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Gujarati + ₹ on Windows consoles
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", nargs="?", type=Path, default=Path("out/tts_test.wav"))
    parser.add_argument("--expect", type=int, default=240000,
                        help="amount that should appear in the transcript (0 to skip)")
    args = parser.parse_args()

    print(f"STT {args.audio} [{get_settings().language}]")
    start = time.perf_counter()
    try:
        payload = asyncio.run(transcribe(args.audio.read_bytes(), args.audio.name))
    except GnaniError as e:
        raise SystemExit(str(e))
    latency = time.perf_counter() - start

    transcript = payload["transcript"]
    print(f"Transcript: {transcript}")
    print(f"Latency:    {latency * 1000:.0f} ms  (request_id={payload.get('request_id')})")

    if args.expect:
        found = find_amounts(transcript)
        ok = args.expect in found
        print(f"Amount {args.expect:,}: {'SURVIVED' if ok else 'LOST'} round trip (found {found})")


if __name__ == "__main__":
    main()
