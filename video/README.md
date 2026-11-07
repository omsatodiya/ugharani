# Ugharani launch video

A 77-second launch video made with [Remotion](https://www.remotion.dev): React components
rendered to MP4. Every voice in it is real Gnani audio: Kavya in Timbre's Tarika voice, the
dealer in Avinash's. The app screens are screenshots of the real pages.

| Scene | What it shows |
|---|---|
| Hook | "Every trader in Gujarat who sells on credit pays someone to make one call." |
| The question | "ભાઈ, પેમેન્ટ ક્યારે મોકલશો?" with its English meaning |
| Problem | ₹10–15k a month, hundreds of calls, promises on paper |
| Reveal | The Ugharani mark, "Meet કાવ્યા" |
| The call | The dealer's phone and a live transcript with subtitles, voiced end to end: she waits for "હા", stops when talked over, the checker strikes out a discount, then a split promise |
| Owner's desk | Zoom into the call log (notes and the owner's task), then Today |
| Rules | What she may and may never agree to |
| Built on Gnani | Prisma → reply → rules checker → Timbre |
| Outro | Logo, the link, #GnaniAI |

## Make it

```bash
# 1. voices (Timbre once per new line, then cached) and app screenshots
uv run python scripts/video_audio.py
uv run python scripts/fake_voice_server.py      # in another terminal (demo data)
uv run python scripts/video_screens.py

# 2. preview and render
cd video
npm install
npm run studio                                  # live preview in the browser
npx remotion render Launch out/ugharani-launch-16x9.mp4
npx remotion render LaunchSquare out/ugharani-launch-1x1.mp4
```

Two formats come from the same scenes: `Launch` (1920×1080, for X and YouTube) and
`LaunchSquare` (1080×1080, for the LinkedIn feed). There's no music, so add a track when
posting. Fonts (Instrument Serif, Inter, Noto Sans Gujarati) load through
`@remotion/google-fonts`.

Remotion is free for individuals and small teams; see its license for company use.
