"""Write the launch video's music: an original 120 BPM track, synthesised from scratch.

    uv run --with numpy --with scipy python scripts/video_music.py

Nothing is sampled or downloaded, so there is no licence to worry about. One beat is
exactly 15 frames at 30 fps, and the sections line up with the scenes in video/src/Kinetic.tsx:

    0-8 s    intro: pad and a soft pluck
    8-16 s   build: drums and bass come in, a riser into 16 s
    16-19 s  impact: "Calling ..." (the phone rings)
    19-50 s  the call: pad and a quiet pluck only, under the voices
    50-66 s  drop: everything back in, a riser into 66 s
    66-70 s  impact on the logo, then the tail
"""

from pathlib import Path
import subprocess

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 44100
BPM = 120
BEAT = 60 / BPM
BAR = 4 * BEAT
TOTAL = 70.0
N = int(TOTAL * SR)
OUT = Path(__file__).resolve().parent.parent / "video" / "public" / "music.mp3"

rng = np.random.default_rng(7)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def lowpass(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def highpass(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bandpass(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def saw(f, n, phase=0.0):
    t = np.arange(n) / SR
    return 2 * ((f * t + phase) % 1.0) - 1


def add(track, start, sig):
    i = int(start * SR)
    if i >= len(track):
        return
    j = min(len(track), i + len(sig))
    track[i:j] += sig[: j - i]


# F major, vi-IV-I-V: Dm7, Bbmaj7, Fmaj7, Cadd9 -- one chord a bar.
CHORDS = [
    ([50, 57, 60, 65], 38),
    ([46, 53, 57, 62], 34),
    ([53, 57, 60, 64], 41),
    ([48, 55, 62, 64], 36),
]


def chord_at(bar):
    return CHORDS[bar % 4]


def level(t):
    """How busy the track is at time t: 0 = call (quiet), 1 = intro, 2 = full."""
    if 19 <= t < 50:
        return 0
    if t < 8:
        return 1
    return 2


bars = int(TOTAL / BAR) + 1

# --- pad: detuned saws, low-passed, slow swell per chord ---------------------------
padL = np.zeros(N)
padR = np.zeros(N)
for b in range(bars):
    notes, _ = chord_at(b)
    start = b * BAR
    n = int((BAR + 0.6) * SR)
    env = np.minimum(1, np.arange(n) / (0.35 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.6 * SR))
    for k, m in enumerate(notes):
        for side, cents in ((padL, -7), (padR, 7)):
            v = saw(hz(m) * 2 ** (cents / 1200), n, phase=rng.random()) + 0.6 * saw(hz(m) * 2 ** (-cents / 2400), n, phase=rng.random())
            add(side, start, v * env * 0.05)
padL = lowpass(padL, 1400)
padR = lowpass(padR, 1400)

# --- pluck arp: eighth notes over two octaves -------------------------------------
PATTERN = [0, 1, 2, 3, 2, 1, 3, 2]
arp = np.zeros(N)
for b in range(bars):
    notes, _ = chord_at(b)
    for i in range(8):
        t = b * BAR + i * BEAT / 2
        if t >= TOTAL - 2.5:
            break
        m = notes[PATTERN[i]] + 12 + (12 if i in (3, 6) and level(t) == 2 else 0)
        n = int(0.45 * SR)
        tt = np.arange(n) / SR
        tone = np.sin(2 * np.pi * hz(m) * tt) + 0.35 * np.sin(4 * np.pi * hz(m) * tt) + 0.12 * np.sin(6 * np.pi * hz(m) * tt)
        g = {0: 0.05, 1: 0.07, 2: 0.08}[level(t)] * (1.0 if i % 2 == 0 else 0.75)
        add(arp, t, tone * np.exp(-tt * 9) * g)
arp = lowpass(arp, 3800)
# a dotted-eighth ping-pong echo
d = int(0.75 * BEAT * SR)
arpL = arp.copy()
arpR = arp.copy() * 0.6
for k in range(1, 5):
    g = 0.38 ** k
    target = arpR if k % 2 else arpL
    target[d * k:] += arp[: N - d * k] * g

# --- drums, bass and the side-chain -------------------------------------------------
kick = np.zeros(N)
hats = np.zeros(N)
clap = np.zeros(N)
bass = np.zeros(N)
duck = np.ones(N)

kn = int(0.4 * SR)
kt = np.arange(kn) / SR
freq = 45 + 85 * np.exp(-kt * 30)
kick_one = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-kt * 9)
kick_one += 0.25 * np.exp(-kt * 300) * rng.standard_normal(kn) * 0.3

hn = int(0.05 * SR)
hat_one = highpass(rng.standard_normal(hn), 7000) * np.exp(-np.arange(hn) / SR * 70)

cn = int(0.25 * SR)
clap_one = bandpass(rng.standard_normal(cn), 900, 3000) * np.exp(-np.arange(cn) / SR * 18)

pump = 1 - 0.6 * np.exp(-np.arange(int(BEAT * SR)) / SR * 9)

beats = int(TOTAL / BEAT)
for i in range(beats):
    t = i * BEAT
    if level(t) != 2 or t >= TOTAL - 4 or 14.5 <= t < 16 or 64.5 <= t < 66:
        continue
    add(kick, t, kick_one * 0.9)
    j = int(t * SR)
    duck[j : j + len(pump)] = np.minimum(duck[j : j + len(pump)], pump[: max(0, min(len(pump), N - j))])
    add(hats, t + BEAT / 2, hat_one * (0.12 if t >= 50 else 0.08))
    if i % 2 == 1 and t >= 50:
        add(clap, t, clap_one * 0.22)
    # bass: root on every beat, octave pop on the off-beat
    _, root = chord_at(int(t / BAR))
    bn = int(BEAT * 0.9 * SR)
    bt = np.arange(bn) / SR
    tone = np.tanh(2.2 * np.sin(2 * np.pi * hz(root) * bt)) * np.minimum(1, bt / 0.01) * np.exp(-bt * 2.5)
    add(bass, t, tone * 0.16)
bass = lowpass(bass, 600)

# --- risers and impacts ---------------------------------------------------------------
fx = np.zeros(N)
for end in (16.0, 50.0, 66.0):
    n = int(2.0 * SR)
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    for seg in range(20):  # a rising band-pass, in chunks
        a, b = seg * n // 20, (seg + 1) * n // 20
        f = 400 * 2 ** (seg / 20 * 4)
        out[a:b] = bandpass(noise, f, min(f * 2.5, 18000))[a:b]
    add(fx, end - 2.0, out * np.linspace(0, 1, n) ** 2 * (0.18 if end != 50 else 0.1))
for t, g in ((16.0, 1.0), (66.0, 1.2), (50.0, 0.5)):
    n = int(2.5 * SR)
    tt = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-tt * 8)) / SR) * np.exp(-tt * 2.2)
    air = lowpass(rng.standard_normal(n), 5000) * np.exp(-tt * 3) * 0.25
    add(fx, t, (boom * 0.55 + air) * g)

# --- mix ---------------------------------------------------------------------------------
def gain_curve():
    t = np.arange(N) / SR
    g = np.ones(N)
    g[(t >= 19) & (t < 50)] = 0.55
    g *= np.clip((TOTAL - t) / 3.0, 0, 1) ** 1.5  # fade at the end
    g *= np.clip(t / 0.6, 0, 1)  # fade in
    return g

G = gain_curve()
L = (padL * duck + arpL * 0.9 + bass * duck + kick + hats + clap + fx) * G
R = (padR * duck + arpR * 0.9 + bass * duck + kick + hats * 0.8 + clap + fx) * G

# a simple stereo reverb on everything but the low end
ir_n = int(2.4 * SR)
irt = np.arange(ir_n) / SR
irL = rng.standard_normal(ir_n) * np.exp(-irt * 2.6)
irR = rng.standard_normal(ir_n) * np.exp(-irt * 2.6)
irL /= np.sqrt((irL ** 2).sum())
irR /= np.sqrt((irR ** 2).sum())
send = highpass((padL + padR + arpL + arpR + clap) * G, 250)
L += fftconvolve(send, irL)[:N] * 0.35
R += fftconvolve(send, irR)[:N] * 0.35

mix = np.stack([L, R], axis=1)
mix = np.tanh(mix * 1.4) / np.tanh(1.4)
mix *= 0.89 / np.abs(mix).max()

pcm = (mix * 32767).astype(np.int16)
OUT.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(
    ["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
     "-c:a", "libmp3lame", "-b:a", "192k", str(OUT)],
    input=pcm.tobytes(), check=True,
)
print(f"wrote {OUT} ({TOTAL:.0f} s)")
