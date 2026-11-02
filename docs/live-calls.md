# Live follow-up calls: design

How a call works today and what Nov 3 adds (interruptions, Hindi and mixed speech).

## Pipeline

```
 phone page (browser)                    server (FastAPI)                         services
 ───────────────────                     ────────────────                         ────────
 mic ─ AudioWorklet ─ 16 kHz PCM16 ──ws──▶ /calls/{id}/live ── 1024-byte frames ──▶ Gnani live STT
                                          │                  ◀── speech_start, transcript ─┘
                                          │  LiveCall (ugharani/live.py)
                                          │    turn-taking, echo, interruptions
                                          │    history ──▶ Gemini (stream) ──▶ sentences ──▶ segments
                                          │                                              │
 speaker ◀ phone-line filter ◀ PCM16 ◀──ws─┤◀── trimmed, 0.4 s held back ◀── Timbre (stream, cached)
          ◀── events: line, duck, unduck, clear, end
```

The browser phone stands in for a phone line: `LiveCall` only sees PCM frames in and out, so a
telephony media stream (Exotel, Twilio) can replace the page without touching the agent.

## Turn-taking

| Situation | What the agent does |
|---|---|
| Call answered | waits up to 1.2 s for the customer's "હેલો", then the opening (bundled clip) |
| Customer finishes a sentence | Gemini streams the reply; "જી." plays from a clip at once, the rest follows in one piece |
| Customer adds more before the reply starts | the reply is restarted with everything they said |
| Reply slow (> 1.6 s) | a filler ("જી,") from a clip |
| Silence 8 s | "હેલો? સાંભળાય છે?", then after another 8 s a polite goodbye |
| Agent says `<END>` | finishes speaking, then hangs up |
| 4 minutes | wraps up politely |

## Interruptions (barge-in), added Nov 3

A person on the phone stops when the other side starts talking over them, unless it is just
"હા" / "હં" (listening noises). The agent should do the same, without being fooled by its own
voice leaking from the phone's speaker into its mic (echo).

Signals: Gnani sends `speech_start` when its VAD hears voice, and a `transcript` when the
utterance ends (after 500 ms of silence). The server knows exactly what audio it has sent and
when the phone will play it (`_speaking_until`), and which text each piece of audio carries.

Decision, in two steps:

1. **`speech_start` while the agent is audible → duck.** The phone lowers her voice to 25 %
   (a person hesitating), so the customer is not talked over at full volume. Nothing is lost:
   the audio keeps playing. If no transcript follows within 2 s, the volume comes back.
2. **`transcript` that started over the agent → decide:**
   - **echo**: the text matches what the agent was saying (character-bigram overlap ≥ 0.5 with
     the agent's lines of the last 15 s) → ignore, unduck
   - **backchannel**: one or two listening words ("હા", "હં", "જી", "ઓકે", "बराबर") while she is
     still talking → ignore, unduck
   - **interruption**: anything else → `clear` (the phone drops the agent's unplayed audio), the
     current reply task is cancelled, her line in the history is cut to what was actually played
     (by time, word-aligned) and marked with "…", and the customer's words get a fresh reply.
   - if she had already finished by the time the transcript came, it's a normal turn.

Why not stop on `speech_start` alone: on phones with weak echo cancellation, her own voice
triggers VAD at the start of every sentence and she would stop herself. Ducking costs nothing if
it was echo; stopping is only done on words that are clearly not hers.

Phone side: `duck` / `unduck` ramp the line volume (80 ms); `clear` stops every scheduled
buffer and resets the playback clock.

## Hindi and mixed speech, Nov 3

Customers in Saurashtra answer in Gujarati, Hindi, or a mix with English trade words. Gnani's
live endpoint takes exactly one locale (`gu-IN`); Prisma v3 writes Hindi words in Gujarati
script, which Gemini understands. To verify with real audio:

- a scripted call where the customer speaks Hindi (Timbre, `hi-IN`), checking the transcripts
  and that the agent answers in simple Hindi (written in Gujarati script, read by the Gujarati
  voice)
- if `gu-IN` garbles Hindi, try `indic-auto` and compare on the same audio

## Tests

| Layer | How | Cost |
|---|---|---|
| unit / integration | `tests/test_live.py`: fake STT (scripted `speech_start` / transcripts), fake Timbre, fake Gemini, through the real websocket route | free |
| wording | `scripts/agent_chat.py hindi …`: Gemini plays the customer | free (Gemini) |
| browser audio path | `scripts/fake_voice_server.py` + the phone page in Chrome | free |
| real end to end | `scripts/live_call.py <scenario>`: a script is the phone; a 2nd Timbre voice is the customer; `ECHO=0.3` leaks the agent's audio back into the mic like a phone speaker | Gnani credits |

`live_call.py` scenarios: `promise` (the happy path), `interrupt` (customer cuts in mid-reply
with "already paid", with echo leaking), `hindi` (customer speaks Hindi).

Budget for Nov 3: at most 3 real scripted calls (~20 Timbre requests, 3 short STT sessions).

## What the real calls showed (Nov 3)

Four scripted real calls (one more than budgeted, because the first exposed a bug):

| Call | Found | Fix |
|---|---|---|
| interrupt, echo 0.3 | **Feedback loop**: her filler ("અચ્છા,") leaked into the mic, was heard as the customer, restarted her reply, which played another filler… she never answered. Fillers weren't on the timeline, and the echo check only ran when > 0.4 s of her audio was left. | Fillers go on the timeline; every transcript that started while she was audible (or ≤ 0.2 s after) is checked for echo; no ducking in the first 0.6 s of her talking (that's her echo starting); at most one filler per 4 s. |
| interrupt, echo 0.3 (fixed) | Echo rejected 7 times on real Gnani transcripts (whole sentences, "જી.", "બરાબર", even "UTR" spelled in English). With echo present, Gnani merged her echo and the customer's words into one segment, so it became a normal turn after she finished, not a barge-in. | That fallback is fine; on phones with working echo cancellation the customer's own voice starts the segment. |
| hindi | Gnani (`gu-IN`) writes Hindi phonetically in Gujarati script ("અગલે સોમવાર કો 50,000 ભેજ દૂંગા") and Gemini understands it, but **answered in Gujarati**. A real barge-in fired (`clear`, her line saved as "બરાબર. તો 9 નવેમ્બરે …"). ~1.2 s silence after "બરાબર." while Timbre started a long sentence. | `agent.speaks_hindi` detects Hindi (Devanagari, or Hindi words in Gujarati script) and a note on the customer's latest turn asks for Hindi; the first sentence after the acknowledgement is synthesised alone (Timbre starts short text faster). |
| hindi (fixed) | She answers in Hindi: "ઠીક હૈ, તો અગલે સોમવાર કો ₹50,000 ઓર મહિને કે આખિર તક બાકી કા પેમેન્ટ, બરાબર ને?" One double confirmation. | Prompt: confirm only once; a "હા" said while she is still asking counts. Also: "હા" heard as she finishes a question is its answer, not a listening noise. |

Earlier (Nov 2-3): the phone ran dry mid-word (fixed by holding 0.4 s back per segment and trimming
Timbre's 0.3-1.1 s of padded silence); first audio is 1.3-1.6 s after the transcript, ~2.2-2.6 s
after the customer stops talking.
