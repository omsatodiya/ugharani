"""Timbre smoke test: synthesize a Gujarati sentence via the SSE endpoint and save a WAV.

Usage: uv run python scripts/tts_test.py [--text "..."] [--out out/tts_test.wav]
"""

import argparse
import sys
import base64
import json
import time
import wave
from pathlib import Path

import httpx

from ugharani.config import get_settings

# Gujarati script: with language=gu-IN, romanised text risks being read as English.
DEFAULT_TEXT = "રમેશભાઈ, તમારા ₹2,40,000 બાકી છે."
SAMPLE_RATE = 16000  # Prisma resamples to 16 kHz mono anyway


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Gujarati + ₹ on Windows consoles
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--out", type=Path, default=Path("out/tts_test.wav"))
    args = parser.parse_args()

    s = get_settings()
    body = {
        "text": args.text,
        "model": s.tts_model,
        "voice": s.tts_voice,
        "language": s.language,
        # raw PCM chunks are concatenated and wrapped in a WAV header locally
        "audio_config": {
            "sample_rate": SAMPLE_RATE,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "raw",
        },
    }

    print(f"TTS {s.tts_model}/{s.tts_voice} [{s.language}]: {args.text}")
    pcm = bytearray()
    ttfb = None
    event = None
    start = time.perf_counter()
    with httpx.stream(
        "POST", f"{s.gnani_base_url}/api/v1/tts/sse",
        headers=s.auth_headers, json=body, timeout=60,
    ) as resp:
        if resp.status_code != 200:
            raise SystemExit(f"HTTP {resp.status_code}: {resp.read().decode(errors='replace')}")
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):])
                if event == "error":
                    raise SystemExit(f"TTS error: {data}")
                if data.get("audio"):
                    if ttfb is None:
                        ttfb = time.perf_counter() - start
                    pcm += base64.b64decode(data["audio"])
                if event == "complete" or data.get("is_final"):
                    break
    total = time.perf_counter() - start

    if not pcm:
        raise SystemExit("No audio received.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)

    duration = len(pcm) / (SAMPLE_RATE * 2)
    print(f"Saved {args.out} ({duration:.2f}s audio)")
    print(f"Time to first audio chunk: {ttfb * 1000:.0f} ms")
    print(f"Total time:                {total * 1000:.0f} ms")


if __name__ == "__main__":
    main()
