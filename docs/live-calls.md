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
