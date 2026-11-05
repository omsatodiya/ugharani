# Ugharani: auto ઉઘરાણી

Every Gujarat trader who sells on credit pays someone to phone dealers about pending payments
("ઉઘરાણી"). Ugharani is that person as a voice agent: **કાવ્યા** from Genius Polyplast, Gondal
calls the dealer, talks like a Saurashtra office girl on the phone (Gujarati, or Hindi if they
speak Hindi), gets a date, an amount and how they'll pay, and writes the owner's notes. She stays
inside the owner's limits: anything more ("30 દિવસ", a discount) goes to the owner.

Built on Gnani **Prisma v3** (live Gujarati speech to text) and **Timbre** (Tarika's voice), with
Gemini (free tier) writing her replies. Live demo: https://ugharani.onrender.com

## Try it in 2 minutes

1. On a laptop open https://ugharani.onrender.com: the owner's app (dues, calls, notes, rules).
2. On a phone open https://ugharani.onrender.com/phone.html, pick **રમેશભાઈ**, tap once (allows
   sound and the mic). The phone page stands in for the dealer's phone line.
3. Tap **આ ફોન પર કૉલ કરાવો** (or **ફોન કરો** in the owner's app). The phone rings; answer it.
4. Talk to her. Try: "હા બોલો", "એક મિનિટ", "શુક્રવારે આપી દઈશ", "થોડું ડિસ્કાઉન્ટ આપો",
   cutting in while she talks, or Hindi.
5. Hang up (or let her say goodbye). The owner's app shows the outcome, promise, notes, and
   anything the owner must do.

(Render's free server sleeps: the first load can take ~50 s.)

## How a call works

```
phone page (mic, 16 kHz PCM) ──websocket──▶ server ──▶ Gnani live STT (gu-IN) ──▶ transcript
     ▲                                        │  own speech detector: pause her in ~0.25 s
     │                                        ▼
     └──── her voice, sentence by sentence ◀── Timbre ◀── checker ◀── Gemini (streamed)
```

What makes it sound like a person (details in `docs/live-calls.md`):
- **Opening like a real call**: "હેલો રમેશભાઈ?", waits for their "હા", then who she is (with the
  recording notice said in passing).
- **Fast turns**: replies are streamed and spoken sentence by sentence; short acknowledgements
  ("જી.", "સારું.") and fillers play from bundled clips at once; Timbre's padded silences are cut.
- **Talked over**: she pauses within ~0.25 s; "હા"/"હં", a cough or her own echo let her go on
  from where she stopped; real words stop her, and Gemini is told what was actually heard.
- **Holding**: "એક મિનિટ" gets "હા જી, વાંધો નહીં." and up to a minute of patience.
- **Hindi**: answered in simple Hindi. **Silence**: "હેલો? સાંભળાય છે?", then a polite goodbye.

What keeps it safe for the business:
- The owner's limits (whole payment within 7 days, part payments only if all is in by 15 days)
  are settings, shown to her as dates. **Every sentence is checked in code** before it's spoken
  (`ugharani/guard.py`): discounts, interest, threats, rates, amounts on no bill and dates past
  the limit are never said; she hands over to the owner instead and the owner is told.
- Dues are never told to someone else who answers; "are you a robot?" gets an honest answer.
- Automatic calls only in the call hours (10-1, 4-7:30), not on Sundays or festival days.
- After the call: outcome, promised date and amount, payment mode, owner's to-do (callback,
  dispute, statement on WhatsApp), saved with the transcript.

Tests: `uv run pytest` (164 tests: calls with Gnani and Gemini faked, the checker, the rules),
`scripts/browser_check.py` (the real phone page in headless Chrome against a fake Gnani, with a
scripted mic that cuts in and coughs), `scripts/agent_chat.py` (Gemini plays tricky customers,
free), `scripts/live_call.py` (a real call, a second Timbre voice as the customer; uses credits).

The app also keeps the trader's credit ledger by voice (below): that's where the dues come from.

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

## Follow-up calls (auto ugharani)

The agent (કાવ્યા, from Genius Polyplast's accounts office) calls customers with pending payments.
The customer's phone is a web page for now: open `/phone.html`, pick a customer, tap once to
receive calls. `POST /calls {"customer": ...}` (or `POST /calls/run` for everyone due today) makes it ring.

An answered call streams over `/calls/{id}/live`: the page sends the mic as 16 kHz PCM16, the
server forwards it to Gnani's live STT (`gu-IN`, VAD-cut transcripts), Gemini writes the reply
(`ugharani/agent.py` has her job), Timbre speaks it sentence by sentence, and the page plays it
through a phone-line filter. A filler covers a slow reply; long silence gets "હેલો?" then a polite
goodbye; the transcript is saved when the call ends. `MAX_LIVE_CALLS` (default 2) caps calls at once.

```bash
uv run python scripts/agent_chat.py promise          # typed conversations, Gemini only (free)
uv run python scripts/fake_voice_server.py           # phone page with Gnani faked (free): tests the audio path
uv run python scripts/live_call.py                   # a real call, a 2nd Timbre voice as the customer (credits)
```

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
