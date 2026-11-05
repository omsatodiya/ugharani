"""Is the customer talking right now? A loudness detector on their 16 kHz PCM16 audio.

Gnani's own speech detector tells us about speech too, but only as a message from its server
(late, and with no "stopped"). This one runs on every 20 ms of audio as it arrives, at almost no
CPU cost, so the agent can pause within ~0.2 s of being talked over, and knows when they stop.

It can't tell the customer's voice from her own voice leaking back from the phone's speaker
(echo), so while she is audible it only fires on sound clearly louder than the echo it has been
hearing. What was said is still decided on Gnani's words (see live.py).
"""

from collections import deque

WINDOW = 640          # bytes: 20 ms of 16 kHz PCM16
MIN_RMS = 600         # about -35 dBFS: quieter is not someone talking into the phone
OVER_NOISE = 3.0      # ...and this many times the background noise
OVER_ECHO = 2.0       # ...and, while she talks, this many times her echo
ECHO_DECAY = 0.973    # per window: the echo level heard halves in ~0.5 s without new echo
START_OF = 12         # of the last 12 windows (240 ms)...
START_LOUD = 10       # ...this many loud: talking (a click or a short "હં" isn't)
STOP_QUIET = 15       # 300 ms of quiet in a row: they stopped
ECHO_LEARN = 0.6      # s: her first moments after a silence: her echo arriving, learned, never "start"


def rms(window: bytes) -> float:
    samples = memoryview(window).cast("h")
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


class Voice:
    """Feed it the customer's audio; it says when they start ("start") and stop ("stop") talking."""

    def __init__(self):
        self.active = False
        self._buf = b""
        self._floor = 0.0  # background noise level
        self._echo = 0.0   # her voice coming back, while she talks
        self._recent: deque[bool] = deque(maxlen=START_OF)
        self._quiet = 0

    def feed(self, pcm: bytes, echo: float | None = None) -> list[str]:
        """`echo`: how long her voice has been playing on the phone (None: it isn't).
        Returns the changes, in order."""
        self._buf += pcm[:len(pcm) // 2 * 2]  # (whole samples only: one stray byte would shift the rest)
        changes = []
        while len(self._buf) >= WINDOW:
            window, self._buf = self._buf[:WINDOW], self._buf[WINDOW:]
            if change := self._window(rms(window), echo):
                changes.append(change)
        return changes

    def _window(self, level: float, echo: float | None) -> str | None:
        over_echo = self._echo * OVER_ECHO if echo is not None else 0.0
        threshold = max(MIN_RMS, self._floor * OVER_NOISE, over_echo)
        loud = level > threshold
        if echo is not None and echo < ECHO_LEARN:  # she just started: this is her echo
            self._echo, loud = max(self._echo, level), False
        # The background: falls at once, rises slowly (a steady fan is learned in ~20 s; a few
        # seconds of speech barely move it)
        self._floor = level if level < self._floor else self._floor + (level - self._floor) * 0.001
        self._echo *= ECHO_DECAY
        if echo is not None and not loud and not self.active:
            self._echo = max(self._echo, level)
        self._recent.append(loud)
        if not self.active:
            if sum(self._recent) >= START_LOUD:
                self.active, self._quiet = True, 0
                return "start"
            return None
        self._quiet = 0 if loud else self._quiet + 1
        if self._quiet >= STOP_QUIET:
            self.active = False
            self._recent.clear()
            return "stop"
        return None
