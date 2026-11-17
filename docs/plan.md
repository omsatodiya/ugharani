# Plan: a Gujarati pilot that works, on a zero budget

Status: **draft for discussion** (2026-11-15). Nothing here is built yet.

Goal: કાવ્યા calls real Genius Polyplast dealers in Gujarati (Hindi when they speak it), never says
anything outside the owner's limits, sounds like a person on the phone, and every outcome reaches
the owner and is kept. Other languages come after, so Gujarati-specific words move into one place.

Constraint: everything free or open source. Where something cannot be free (phone minutes, a
DLT-registered business number), there is a free stand-in until money comes.

## Decisions so far

| Topic | Decision |
|---|---|
| Milestone | Pilot with real dealers |
| Phone line | A plug-in for phone lines. Proven free on a **Twilio trial** (calls to verified numbers only). **Exotel** added the same way when there's money. Dealers use the **browser phone, sent as a WhatsApp link**, meanwhile. |
| Server | Render free + the GitHub Actions pinger (already covers 7:30-23:30 IST) |
| Database | **Neon Postgres** free tier (Singapore); SQLite stays for tests and local runs |
| Speech | Gnani Prisma v3 (live STT) and Timbre (TTS), challenge credits (plenty) |
| Brain | Gemini free tier, two models raced (as now) |
| AI disclosure | Owner setting, **on by default**: she says she's an automatic assistant in the intro |
| Test audio | 3-5 real people via a recording page, plus free datasets (FLEURS, IndicVoices) |

## Architecture after the plan

```
 dealer ── browser phone (WhatsApp link) ──┐
 dealer ── Twilio / Exotel media stream ───┤  line adapters: audio in/out as 16 kHz PCM16
                                           ▼
                                  ugharani/lines/*.py
                                           │
                                    LiveCall (live.py)  ◀── lang/gu.py: every Gujarati word list
                                     │      │      │
                       Gnani live STT   Gemini   Timbre
                    (gu-IN,hi-IN,en-IN)    │
                                         guard.py ◀── dates.py + numbers (shared with extract.py)
                                           │
                                   Postgres (Neon) / SQLite: ledger, calls, notes, metrics
                                           │
                              owner's desk: dues, calls, notes, wa.me WhatsApp links, Excel import
```

New modules:
- `ugharani/lang/gu.py`: acknowledgements, fillers, listening words, yes words, hold phrases,
  banned terms and word endings, month names, number words, fixed lines, prompt examples, voice
  and STT locale. A language is one file. (`hi.py`, `mr.py` later.)
- `ugharani/dates.py`: one parser for spoken dates ("15 તારીખે", "સોમવારે", "આવતા અઠવાડિયે",
  "આવતા મહિને", "દિવાળી પછી", "પરમ દિવસે", "અગલે મહિને") used by the checker, the notes and the ledger.
- `ugharani/lines/`: `base.py` (the interface LiveCall needs: audio in, audio out, events,
  hang up), `browser.py` (today's websocket, moved), `twilio.py` (Media Streams: 8 kHz μ-law
  base64 JSON, resampled to 16 kHz), later `exotel.py` (8 kHz PCM base64).
- `ugharani/store.py`: picks Postgres (`DATABASE_URL`) or SQLite; the SQL written to run on both.

## Phase 0: housekeeping (half a day)

1. Line endings: the working tree is CRLF, the repo LF. Restore LF and add `.gitattributes`
   (`* text=auto eol=lf`) so it can't happen again. `.DS_Store` into `.gitignore`.
2. Tests that depend on today's date: freeze "today" in the live-call tests (the 2 failures).

Done when: `uv run pytest` is green on any day of the month; `git status` is clean.

## Phase 1: the checker never lets a wrong sentence through (1-2 days)

Every bug found on Nov 15 becomes a test first, then the fix.

| Gap | Fix |
|---|---|
| Amounts in words pass ("50 હજાર", "એક લાખ વીસ હજાર") | Check her sentences with the same number reader the ledger uses (`extract._number_groups`) |
| Relative dates pass ("આવતા મહિને", "એક મહિના પછી", "દિવાળી પછી", "અગલે મહિને") | `dates.py`; anything open-ended past the limit or unknown ("પછી" with no date) is blocked |
| Number words before દિવસ ("ત્રીસ દિવસમાં") | Same number reader |
| 7-day rule for the full amount not in code | A date past `promise_days` with the full balance (or no part payment agreed) is blocked |
| Discount said other ways ("10% ઓછા", "ઓછું કરી આપીશું", "માફ") | More terms and patterns, Gujarati and Hindi |
| Festival names: "દિવાળી", "નવરાત્રી", "ઉત્તરાયણ" | Resolved to their date this year (owner's holidays list + a small built-in table) |

Done when: a table of ~80 tricky sentences (`tests/test_guard.py`) all pass, and the generated
run passes: `scripts/guard_fuzz.py` asks Gemini (free tier) for 200 sentences that break a rule
(discounts, interest, threats, rates, unknown amounts, dates past the limits; Gujarati, Hindi and
mixed, digits and words) and 100 that don't, feeds each to `guard.problem()` with a fixed customer
(balance ₹1,20,000) and date, and saves the misses to `out/guard_fuzz.json`. Pass: every
rule-breaking sentence is blocked and at most 5% of the allowed ones are (a false block only costs
a hand-over). Misses that are real become rows in the sentence table.

## Phase 2: Gujarati conversation correctness (2-3 days)

1. **Language from Gnani, not word lists.** Built behind a setting, **off by default**: live STT
   with `language_code: gu-IN,hi-IN,en-IN`, `detected_language_code` per transcript. It is switched
   on only after Phase 3 shows Gujarati transcripts are not worse than with `gu-IN` alone. The word
   list stays as the fallback (and the default until then), without words shared with Gujarati
   ("પર", "કી", "કા"…).
2. **Hold vs call back.** "બે મિનિટ પછી ફોન કરો" / "પછી ફોન કરજો" is a callback (ask when,
   then goodbye), not a hold. Add "જરા રાહ જુઓ", "એક સેકન્ડ હં", "ચાલુ રાખો". Tests for each.
3. **Disclosure setting.** `disclose_ai` (default on): the intro becomes "હા નમસ્તે. હું
   જીનિયસ પોલીપ્લાસ્ટમાંથી કાવ્યા, ઓટોમેટિક આસિસ્ટન્ટ, બોલું છું." (exact wording to decide by ear),
   bundled as a clip.
4. **Notes checked in code.** The promised date and amount Gemini writes in the notes are checked
   against the transcript with `dates.py` and the number reader; a mismatch goes to the owner as
   "please check".
5. **Pass/fail conversation suite.** `scripts/agent_chat.py` scenarios become an automatic suite:
   for each, Gemini plays the customer 3 times and code checks: no checker stop needed (or the
   right one), no repeated sentence, confirmed once, the reply's language matches, the call ends,
   notes match what was agreed. Gemini free tier, run before every prompt change.
   New scenarios: "બે મિનિટ પછી ફોન કરો", "દિવાળી પછી", "અડધા હમણાં અડધા આવતા મહિને",
   "તમારો માણસ આવીને લઈ જાય", "ચેક બાઉન્સ થયો હતો", "UPI નંબર આપો", Kathiyawadi forms
   ("હાલો", "ઈ", "હંધુય"), Hinglish.

Done when: the suite passes 3 runs in a row; every scenario's notes are right.

## Phase 3: hearing Gujarati right (2-3 days, plus the people's time)

1. **Recording page** `/record.html`: a list of ~50 prompts (amounts "સાડા ત્રણ લાખ", "પોણા બે",
   dates "પરમ દિવસે", "આવતા ગુરુવારે", names, payment modes, UTR digits, Hindi lines); the
   person reads or answers each; saved as WAV with the expected text. Shared with 3-5 people.
   Controls: a consent screen first (what is recorded, why, who hears it, how to delete); the
   page and the clips need the owner's key (`?k=`), never public; clips stored outside git and
   deleted on request or when the evaluation is done; the prompts use made-up names, amounts and
   UTR numbers only, never a real account or payment identifier.
2. **Free datasets**: Google FLEURS (gu_in) and a Gujarati slice of AI4Bharat IndicVoices,
   downloaded to a local folder (not in git).
3. **Scorer** `scripts/stt_eval.py`: Prisma live (as on a call) on every clip; reports exact
   match of amounts and dates (what matters), names, and word error rate. Run on Kaggle/Colab
   free GPU with AI4Bharat IndicConformer as a second opinion where Prisma looks wrong.
4. **Fixes from the results**: `keyterms` (names, firms, cities, payment words, "RTGS", "NEFT",
   "UTR"), `substitution_map` for repeated mishearings, and the ledger's number reader for
   anything ITN leaves in words.

Done when: amounts and dates come out right on ≥95% of the recorded clips (target to agree once
we see the first numbers).

## Phase 4: faster replies (2 days)

Today ~2.2-2.6 s from the customer stopping to her first sound. Target: ≤1.5 s typical.

1. **Measure each stage on every call**, saved with the call: customer stopped → transcript →
   Gemini's first sentence → Timbre's first audio → phone plays. A call page shows it.
2. **`commit` frame**: when our speech detector sees ~300 ms of quiet and the words so far look
   finished, tell Gnani to close the utterance instead of waiting for its 500 ms.
3. **Ack at once**: for a plain answer turn, play "જી." from the clip when the transcript arrives,
   not when Gemini writes it (and drop Gemini's own).
4. No 0.4 s prebuffer for bundled clips; try Timbre's websocket mode against SSE for first-audio
   time; keep the system prompt identical across turns so Gemini can cache it.

Done when: the median on 10 real browser calls is ≤1.5 s and no turn is over 3 s.

## Phase 5: nothing is lost (1-2 days)

1. **Neon Postgres** behind `store.py`; schema migration script; SQLite stays for tests.
   Seed data only when the database is empty (not on every start).
2. **Call audio**: not stored by default (DPDP: keep less). Transcripts and notes are kept;
   an owner setting for how long (default 90 days), then deleted.
3. **Excel/CSV import** of outstanding bills (party, bill no., amount, due date, phone): a
   Tally "Outstanding" export or any sheet; preview and confirm before saving.
4. **WhatsApp without an API**: on the owner's to-do ("send statement"), a `wa.me` link opens
   WhatsApp with the dealer's number and a prepared Gujarati message; the owner taps send.
5. **Phone page as a WhatsApp link** for the pilot: a per-dealer link (signed, expires) the owner
   sends; the dealer taps it, the page rings, they talk.

Done when: restarting Render loses nothing; an imported sheet becomes the call queue.

## Phase 6: real phone lines, free (2-3 days)

1. `lines/` interface; the browser phone moved onto it (no behaviour change, tests unchanged).
2. **Twilio adapter**: outbound call via the REST API with `<Connect><Stream>`; Media Streams
   websocket; μ-law 8 kHz ↔ PCM16 16 kHz; `clear` and `mark` messages for interruptions; Gnani
   at 8 kHz tried against resampled 16 kHz.
3. Tune `vad.py` for a phone line (8 kHz noise, network echo cancellation: less echo, so the
   echo rules may relax; measure on real calls to your own phone).
4. Exotel adapter written against its Voicebot docs, tested when an account with streaming is
   available.

Done when: 5 calls from Twilio to your verified phone go end to end with notes saved.

## Phase 7: languages after Gujarati (later)

Hindi first (most dealers who don't speak Gujarati speak Hindi): `lang/hi.py`, Timbre's Hindi
voice, Hindi prompt and checker terms, the same suites. Then Marathi. Each language must pass
the Phase 1-3 suites before it's offered.

## Before calling real dealers

- The browser link pilot needs nothing registered: the dealer chooses to tap the link.
- Real calls to dealers need a DLT-registered business number (a fee) under Genius Polyplast's
  KYC, and its consent: postponed until there's money; Twilio trial calls go only to people who
  agreed to test.
- Owner sign-off on the exact wording of the intro, the hand-over line and the goodbye.

## Order and size

| Phase | What | Size |
|---|---|---|
| 0 | Housekeeping | ½ day |
| 1 | Checker | 1-2 days |
| 2 | Conversation correctness | 2-3 days |
| 3 | Hearing Gujarati | 2-3 days + recordings |
| 4 | Faster replies | 2 days |
| 5 | Nothing lost, import, WhatsApp links | 1-2 days |
| 6 | Phone lines (Twilio trial) | 2-3 days |

Phases 3 and 5 can start in parallel with 1-2 (the recording page first, so people can record
while the rest is built).

## Open questions

1. The intro with disclosure: exact wording, to decide by ear (two or three versions synthesised).
2. Accuracy target for Phase 3: agree after the first measurement.
3. Twilio trial account: you create it (needs a phone number to verify, no card for the trial).
4. Neon account: you create it (free, no card) and put `DATABASE_URL` in Render's settings.

## Implementation steps

Agreed 2026-11-15. Workflow: one branch per phase (`phase-N-name`), one commit per step below
(tests in the same commit as the change), pushed after each step; a pull request per phase,
merged to `main` once CI is green. Each step leaves `uv run pytest` green.

### Phase 0 — `phase-0-housekeeping`
- 0.1 Restore LF line endings; `.gitattributes` (`* text=auto eol=lf`); `.DS_Store` ignored.
- 0.2 Commit this plan (`docs/plan.md`).
- 0.3 Freeze "today" in the live-call tests so they pass on any date.
- 0.4 CI: GitHub Actions runs `uv run pytest` on every push to any branch (PRs show those
  checks); badge in the README.

### Phase 1 — `phase-1-checker`
- 1.1 `tests/test_guard.py`: the Nov 15 gaps as failing cases (marked xfail), so the fixes show.
- 1.2 Amounts in words in her sentences (shared number reader).
- 1.3 `ugharani/dates.py`: spoken dates (weekdays, "પરમ દિવસે", "આવતા અઠવાડિયે/મહિને", number
  words + દિવસ/અઠવાડિયા/મહિના, Hindi forms); guard uses it.
- 1.4 Open-ended dates ("દિવાળી પછી", "મહિના પછી") and festival names.
- 1.5 The 7-day rule for the full amount in code.
- 1.6 More discount/waiver wording ("% ઓછા", "ઓછું કરી", "માફ"), Gujarati and Hindi.
- 1.7 Sentence table grown to ~80 cases; docs/live-calls.md updated.
- 1.8 `scripts/guard_fuzz.py`: the generated run described in Phase 1; its misses fixed.
- 1.9 (added) A second opinion for what words can't pin down. Checking each sentence with Gemini
  before speaking measured too slow on the free tier (median 2.3 s); agreed instead: an after-call
  audit of all her lines (one request), shown to the owner. Results in docs/live-calls.md.

### Phase 2 — `phase-2-conversation`
- 2.1 `ugharani/lang/gu.py`: move the Gujarati word lists out of live.py/agent.py/guard.py (no
  behaviour change).
- 2.2 Hold vs call-back ("બે મિનિટ પછી ફોન કરો"); more hold phrases.
- 2.3 Hindi detection: drop words shared with Gujarati; tests.
- 2.4 Gnani multi-language (`gu-IN,hi-IN,en-IN`) + `detected_language_code`, behind a setting,
  default off until measured in Phase 3.
- 2.5 `disclose_ai` owner setting (default on), intro wording, clip bundled.
- 2.6 Notes checked in code against the transcript.
- 2.7 `scripts/agent_chat.py` → pass/fail suite with code checks; new scenarios.

#### Phase 2 design (agreed before building, 2026-11-17)

- **2.1 One home for the Gujarati words.** `ugharani/lang/gu.py` holds every phrase list the
  conversation code matches or says: her fixed lines (fillers, acknowledgements, "હેલો?", goodbyes),
  the listening noises and yeses, the hold words, the Hindi/Gujarati marker words, and the checker's
  word and phrase lists. `live.py`, `agent.py` and `guard.py` import them under their old names, so
  the tests pass unchanged: the proof that nothing moved but the words. The number and date readers
  (`extract.py`, `dates.py`) are already Gujarati-only modules and stay where they are.
- **2.2 Hold or call back.** Today "બે મિનિટ પછી ફોન કરો" matches the hold words ("બે મિનિટ"), so she
  says "હા જી, વાંધો નહીં." and waits a minute in silence on a line the customer has left. Now:
  - `asks_for_callback()`: "પછી ફોન કરો/કરજો", "થોડી વાર પછી ફોન", "સાંજે ફોન કરજો", "હું સામેથી ફોન
    કરું", Hindi "बाद में फोन करो", "busy છું". It wins over the hold words.
  - A call-back goes to Gemini with a note on the turn (as Hindi does): it is a call-back, not a
    hold; if they said when, say she'll call then and say goodbye; if not, ask once when.
  - More hold words: "જરા રાહ જુઓ", "રાહ જોજો", "એક સેકન્ડ હં", "ફોન/લાઈન ચાલુ રાખો", "લાઈન પર
    રહો", "બસ એક મિનિટ", "रुकिए". ("ચાલુ રાખો" alone can mean "go on talking": only with ફોન/લાઈન.)
  - After the call: a `callback` outcome is called again the next day instead of after
    `repeat_every_days`, and the time they asked for goes into the owner's to-do. (A same-day
    call-back at a set minute needs a scheduler; Phase 6 with the phone lines.)
- **2.3 Hindi without false alarms.** Drop the marker words Gujarati uses too: "પર" ("WhatsApp
  પર"), "કી", "કા" (Kathiyawadi "કાં"), "તક", "સાથ", "ઠીક" ("ઠીક છે"), "હમ" (a listening noise).
  Add Hindi-only forms ("દીજિએ", "કીજિએ", "જાએંગે", "દેખતે") and Gujarati-only ones ("આવશે",
  "કરું", "દઉં", "હતું"). One function scores a text, used for the customer and, in the suite,
  for her replies.
- **2.4 Gnani's own language, behind a switch.** `STT_MULTI_LANGUAGE=1` (default off) opens live
  STT with `language_code: gu-IN,hi-IN,en-IN`. Gnani then writes Hindi in Devanagari and reports
  `detected_language_code` per utterance (judged from the text's script). The call keeps the latest
  turn's code; `hi-IN` means Hindi, otherwise the word count decides as before. Off until Phase 3
  measures Gujarati transcripts with it (the checker and number reader read Gujarati script).
- **2.5 Saying she's automatic.** Owner setting `disclose_ai`, on by default, a switch under
  "Kavya's rules". On: "હા નમસ્તે. હું જીનિયસ પોલીપ્લાસ્ટની ઓટોમેટિક આસિસ્ટન્ટ કાવ્યા બોલું છું."
  (no commas: Timbre pauses at them). Off: today's intro. The prompt is told which was said. Both
  intros are bundled as clips.
- **2.6 Notes checked against the call.** After Gemini writes the notes, code checks the promised
  date (inside a span `dates.py` reads from some line of the call) and amount (said by someone in
  the call, or the balance). An unsupported value is dropped (a false promise would stop the
  follow-up calls) and the owner's to-do says what the notes claimed: "please check".
- **2.7 The conversation suite.** `scripts/agent_chat.py` runs each scenario N times (default 3)
  with Gemini as the customer, on a pinned date (Wednesday 4 November 2026, Diwali on the 8th),
  and checks in code:
  - the checker stopped nothing, or only what the scenario allows (a discount ask, a long date)
  - no sentence of hers said twice (acknowledgements aside)
  - after a yes to her confirmation, no second confirmation
  - her language matches the customer's (Hindi scenario: Hindi; the others: never Hindi)
  - the call ends within 10 turns
  - the notes have the expected outcome and pass the 2.6 check
  - a hold is answered as a live call would, with the fixed line and no Gemini request
  New scenarios: call-back, "દિવાળી પછી", half now half next month, "તમારો માણસ આવીને લઈ જાય",
  bounced cheque, "UPI નંબર આપો", Kathiyawadi, Hinglish. Exit 0 pass, 1 fail, 2 incomplete
  (Gemini unavailable). The free tier limits how often it can run in a day.

### Phase 3 — `phase-3-hearing`
- 3.1 Recording page `/record.html` + prompt list + saving clips with expected text, behind the
  owner's key, with the consent screen and deletion.
- 3.2 Dataset fetch script (FLEURS gu_in, IndicVoices slice) to a git-ignored folder.
- 3.3 `scripts/stt_eval.py`: amounts/dates exact match, names, WER; a report file.
- 3.4 Keyterms and substitution map from the results; re-measure.

### Phase 4 — `phase-4-speed`
- 4.1 Per-stage timings saved on each call; shown on the call page.
- 4.2 `commit` frame on our detector's end of speech.
- 4.3 Instant "જી." on the transcript.
- 4.4 Prebuffer skip for clips; Timbre websocket vs SSE trial.

### Phase 5 — `phase-5-storage`
- 5.1 `store.py`: SQL that runs on SQLite and Postgres; tests on both (Postgres in CI service).
- 5.2 Neon on Render; seed only an empty database.
- 5.3 Retention setting; old transcripts deleted.
- 5.4 Excel/CSV import with preview.
- 5.5 wa.me links on the owner's to-dos.
- 5.6 Signed per-dealer phone-page links.

### Phase 6 — `phase-6-lines`
- 6.1 `lines/base.py`; browser phone moved onto it.
- 6.2 Twilio outbound call + Media Streams adapter (μ-law 8 kHz ↔ PCM16 16 kHz).
- 6.3 VAD tuning for phone lines from real calls.
- 6.4 Exotel adapter from its docs.
