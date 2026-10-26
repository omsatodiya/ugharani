# Ugharani

A Gujarati/Hinglish voice credit ledger for Surat traders. A trader calls in and says
something like *"Rameshbhai ne be lakh chaalis hazaar nu maal aapyu, saath divas"*, and
Ugharani records the buyer, amount and due date. Later it sends payment reminders as calls or voice notes.
Built on Gnani's **Prisma v2.5** (speech-to-text) and **Timbre v3.0** (text-to-speech).

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # then set GNANI_API_KEY (get one at https://app.gnani.ai/voice/)
```

## Smoke tests (text → speech → text)

```bash
# 1. Timbre: synthesise a Gujarati sentence with an amount, save to out/tts_test.wav
uv run python scripts/tts_test.py
uv run python scripts/tts_test.py --text "Rameshbhai, tamara ₹2,40,000 baaki che"

# 2. Prisma: transcribe it (gu-IN, ITN on) and check ₹2,40,000 survived
uv run python scripts/stt_test.py
uv run python scripts/stt_test.py path/to/recording.wav --expect 240000
```

## Health endpoint

```bash
uv run uvicorn ugharani.main:app --reload
curl http://localhost:8000/health
```
