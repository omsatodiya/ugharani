# Ugharani launch video

A 70-second launch video made with [Remotion](https://www.remotion.dev): React components
rendered to MP4, cut to music in kinetic type: one idea per beat on a dark canvas.

- **Voices** are real Gnani audio: Kavya in Timbre's Tarika voice, the dealer in Avinash's.
  The orb on screen moves with the actual waveform.
- **Music** is an original 120 BPM track synthesised in code (`scripts/video_music.py`),
  so there's nothing to license. A beat is exactly 15 frames, and every cut lands on one.
- **App screens** are screenshots of the real pages.

| Time | Scene |
|---|---|
| 0–8 s | "every month, every trader who sells on credit makes the same call." → "ભાઈ, પેમેન્ટ ક્યારે મોકલશો?" |
| 8–12 s | "Hundreds of calls. Every promise on paper." (drums come in) |
| 12–16 s | "Meet કાવ્યા", then the owner's call queue as a glowing bar, and the call button |
| 16–19 s | The phone rings (impact) |
| 19–46 s | The call, voiced end to end: she waits for "હા", stops when talked over, the checker strikes out a discount, then a split promise |
| 46–50 s | What the owner gets: the promise and a task |
| 50–66 s | The call log, "Listens · Thinks · Speaks, built on Gnani", "Your limits.", the owner's desk (drop) |
| 66–70 s | ઉઘરાણી → logo, link, #GnaniAI (impact) |

## Make it

```bash
# 1. voices (Timbre once per new line, then cached), music and app screenshots
uv run python scripts/video_audio.py
uv run --no-project --with numpy --with scipy python scripts/video_music.py
uv run python scripts/fake_voice_server.py      # in another terminal (demo data)
uv run python scripts/video_screens.py

# 2. preview and render
cd video
npm install
npm run studio                                  # live preview in the browser
npm run render                                  # both formats into out/
```

Two formats come from the same scenes: `Launch` (1920×1080, for X and YouTube) and
`LaunchSquare` (1080×1080, for the LinkedIn feed). The first cut, with light screens and
no music, is still there as `Classic` and `ClassicSquare`.

Fonts (Instrument Serif, Inter, Noto Sans Gujarati) load through `@remotion/google-fonts`.
Remotion is free for individuals and small teams; see its license for company use.
