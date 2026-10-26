"""Prisma smoke test: transcribe a file via REST with ITN on, and check the amount survived.

Usage: uv run python scripts/stt_test.py [audio_file] [--expect 240000]
"""

import argparse
import sys
import time
from pathlib import Path

import httpx

from ugharani.amounts import find_amounts
from ugharani.config import get_settings


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Gujarati + ₹ on Windows consoles
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", nargs="?", type=Path, default=Path("out/tts_test.wav"))
    parser.add_argument("--expect", type=int, default=240000,
                        help="amount that should appear in the transcript (0 to skip)")
    args = parser.parse_args()

    s = get_settings()
    form = {
        "language_code": s.language,
        "format": "transcribe",  # enables ITN: numbers, ₹, dates -> digits
    }

    print(f"STT {args.audio} [{s.language}]")
    start = time.perf_counter()
    with args.audio.open("rb") as f:
        resp = httpx.post(
            f"{s.gnani_base_url}/stt/v3",
            headers=s.auth_headers,
            data=form,
            files={"audio_file": (args.audio.name, f)},
            timeout=60,
        )
    latency = time.perf_counter() - start

    payload = resp.json()
    if resp.status_code != 200 or not payload.get("success"):
        raise SystemExit(f"HTTP {resp.status_code}: {payload}")

    transcript = payload["transcript"]
    print(f"Transcript: {transcript}")
    print(f"Latency:    {latency * 1000:.0f} ms  (request_id={payload.get('request_id')})")

    if args.expect:
        found = find_amounts(transcript)
        ok = args.expect in found
        print(f"Amount {args.expect:,}: {'SURVIVED' if ok else 'LOST'} round trip (found {found})")


if __name__ == "__main__":
    main()
