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

## Ledger (text only, no API calls)

Rule-based extraction pulls out buyer, amount and due date and saves the entry to SQLite (`ugharani.db`).

```bash
uv run python scripts/ledger.py add "Rameshbhai ne be lakh chaalis hazaar nu maal aapyu, saath divas"
uv run python scripts/ledger.py add "રમેશભાઈએ ₹50,000 જમા કરાવ્યા"   # payment received
uv run python scripts/ledger.py list
uv run python scripts/ledger.py balances
uv run pytest
```

## API

```bash
uv run uvicorn ugharani.main:app --reload

curl http://localhost:8000/health
curl -F "audio=@out/tts_test.wav" http://localhost:8000/entries/voice   # 1 Prisma call + 1 Timbre call (cached)
curl -H "Content-Type: application/json" -d '<draft from above>' http://localhost:8000/entries
curl http://localhost:8000/entries
curl http://localhost:8000/balances
curl "http://localhost:8000/summary?today=2026-11-30"                     # 1 Timbre call per new sentence
curl http://localhost:8000/reminders/Rameshbhai
```

Voice entry is a short conversation, and nothing is saved until the trader confirms:

1. `POST /entries/voice` transcribes the clip with Prisma (gu-IN, ITN on, known buyer names
   sent as `bias_list`) and returns a `draft`, the `missing` fields, and what to `say` back,
   with an `audio` URL for it spoken by Timbre.
2. If a field is missing, `say` asks for it ("કેટલા દિવસની મુદત?"). Record the answer and send it
   with the `draft` form field (the previous draft as JSON), and it fills the gap.
3. Once nothing is missing, `say` reads the entry back ("રમેશભાઈને ₹2,40,000નો માલ, 60 દિવસની મુદત. બરાબર?").
   `POST /entries` with the draft saves it.

`GET /summary` lists what is overdue, due today and due in the next 3 days, plus a spoken summary.
`GET /reminders/{buyer}` gives a polite reminder for one buyer, for the trader to send themselves.
Payments settle a buyer's oldest credits first. Both take `?today=YYYY-MM-DD` so a demo can jump ahead.

Every Timbre clip is cached in `out/tts/` by sentence, so repeating a sentence costs no credits.
`GET /audio/{key}.wav` serves those clips.

## App and deploy

`uv run uvicorn ugharani.main:app` also serves the PWA at http://localhost:8000: tap the mic,
speak an entry, answer any question, confirm. The browser records 16 kHz WAV for Prisma.
Phones only allow the mic over HTTPS, so test on a phone against the deployed app.

Deployed on Render's free tier with the `Dockerfile` (`render.yaml` describes the service;
set `GNANI_API_KEY` in the Render dashboard). The free disk is wiped whenever the service
sleeps, so the image starts from sample buyers (`DEMO_SEED=1`) and ships clips of fixed
sentences in `ugharani/clips/`:

```bash
uv run python scripts/ledger.py seed                 # sample buyers, locally
uv run python scripts/bundle_clips.py                # copy cached fixed clips into ugharani/clips/
uv run python scripts/bundle_clips.py --synthesize   # also make missing ones (1 Timbre call each)
```

`GNANI_DAILY_LIMIT` (default 150) caps Prisma + Timbre calls per server per day, so a public
link can't drain the credits.
