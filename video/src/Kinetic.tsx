/**
 * The launch video, cut to music: one idea per beat on a dark canvas.
 * 120 BPM, so a beat is 15 frames. Times below are in seconds and line up with the
 * sections of public/music.mp3 (see scripts/video_music.py).
 */
import React from "react";
import { AbsoluteFill, Audio, Easing, interpolate, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { useAudioData, visualizeAudio } from "@remotion/media-utils";
import lines from "./lines.json";
import { C, F, FPS, s } from "./theme";
import { Browser, Icon, Mark } from "./ui";

export const TOTAL_KINETIC = s(70);

const BG = "#05070f";
const GRAD = "linear-gradient(95deg, #5b8cff 0%, #9b7bff 45%, #f08a24 100%)";
const DOTS = ["#5b8cff", "#9b7bff", "#f08a24", "#ff6b8b", "#3ccf9f"];
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.16, 1, 0.3, 1);

// --- small pieces -------------------------------------------------------------------

/** Text that comes in sharp and fast: a short blur, a small rise. */
const Pop: React.FC<{ children: React.ReactNode; size?: number; delay?: number; grad?: boolean; weight?: number; color?: string; style?: React.CSSProperties }> = ({ children, size = 72, delay = 0, grad, weight = 600, color = "#fff", style }) => {
  const f = useCurrentFrame() - delay;
  const p = interpolate(f, [0, 9], [0, 1], { ...clamp, easing: ease });
  return (
    <div style={{
      fontFamily: F.sans, fontSize: size, fontWeight: weight, letterSpacing: "-0.03em", lineHeight: 1.15, color, textAlign: "center",
      opacity: interpolate(f, [0, 4], [0, 1], clamp), filter: `blur(${(1 - p) * 14}px)`, transform: `translateY(${(1 - p) * 22}px) scale(${0.96 + p * 0.04})`,
      ...(grad ? { backgroundImage: GRAD, WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent", paddingBottom: size * 0.12 } : {}),
      ...style,
    }}>{children}</div>
  );
};

const Center: React.FC<{ children: React.ReactNode; gap?: number }> = ({ children, gap = 18 }) => (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap }}>{children}</AbsoluteFill>
);

/** Coloured dots drifting outwards; `burst` makes them fly from the centre. */
const Particles: React.FC<{ count?: number; burst?: boolean; seed?: number }> = ({ count = 26, burst, seed = 1 }) => {
  const f = useCurrentFrame();
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {Array.from({ length: count }, (_, i) => {
        const r = (k: number) => { const x = Math.sin((i + 1) * 12.9898 * (seed + k) + seed * 78.233) * 43758.5453; return x - Math.floor(x); };
        const angle = r(1) * Math.PI * 2;
        const dist = (0.25 + r(2) * 0.55) * Math.min(width, height) * 0.75;
        const p = burst ? interpolate(f, [0, 24], [0, 1], { ...clamp, easing: ease }) : 1;
        const drift = f * (0.2 + r(3) * 0.5);
        const x = width / 2 + Math.cos(angle) * (dist * p + drift);
        const y = height / 2 + Math.sin(angle) * (dist * p + drift) * 0.8;
        const size = 4 + r(4) * 9;
        const tw = 0.45 + 0.55 * Math.abs(Math.sin(f / 14 + i));
        return <div key={i} style={{ position: "absolute", left: x, top: y, width: size, height: size, borderRadius: "50%", background: DOTS[i % DOTS.length], opacity: tw * interpolate(f, [0, 6], [0, 1], clamp) }} />;
      })}
    </AbsoluteFill>
  );
};

/** Letters that start scattered and fall into place. */
const Scatter: React.FC<{ text: string; size?: number }> = ({ text, size = 80 }) => {
  const f = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  return (
    <Center>
      <div style={{ display: "flex", fontFamily: F.sans, fontSize: size, fontWeight: 600, letterSpacing: "-0.03em", color: "#fff", whiteSpace: "pre" }}>
        {[...text].map((ch, i) => {
          const r = (k: number) => { const x = Math.sin((i + 3) * 91.17 * k) * 9973.1; return x - Math.floor(x); };
          const p = spring({ frame: f - 6 - i * 1.5, fps, config: { damping: 20, stiffness: 70, mass: 0.9 } });
          const dx = (r(1) - 0.5) * width * 0.8, dy = (r(2) - 0.5) * height * 0.8;
          return <span key={i} style={{ display: "inline-block", transform: `translate(${dx * (1 - p)}px, ${dy * (1 - p)}px) rotate(${(r(3) - 0.5) * 80 * (1 - p)}deg)`, opacity: interpolate(f, [0, 8], [0, 1], clamp) }}>{ch}</span>;
        })}
      </div>
    </Center>
  );
};

const Dot: React.FC<{ delay: number }> = ({ delay }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f - delay, fps, config: { damping: 9, stiffness: 180 } });
  return <span style={{ display: "inline-block", width: 18, height: 18, borderRadius: "50%", background: C.saffron, marginLeft: 6, transform: `scale(${p})` }} />;
};

// --- the opening, 0-19 s ------------------------------------------------------------------

const Word: React.FC<{ text: React.ReactNode; size?: number; grad?: boolean; ghost?: string }> = ({ text, size, grad, ghost }) => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill>
      {ghost && (
        <Center>
          <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 420, letterSpacing: "-0.05em", color: "transparent", WebkitTextStroke: "2px rgba(255,255,255,0.09)", transform: `translateY(${60 - f * 1.2}px)` }}>{ghost}</div>
        </Center>
      )}
      <Center><Pop size={size} grad={grad}>{text}</Pop></Center>
    </AbsoluteFill>
  );
};

/** The owner's call queue as one glowing bar: a dealer, an amount, and the call button. */
const QueueBar: React.FC = () => {
  const f = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const w = Math.min(1080, width * 0.88);
  const text = "રમેશભાઈ  ·  ₹1,20,000 pending  ·  Oct bill";
  const typed = Math.round(interpolate(f, [8, 38], [0, text.length], clamp));
  const inP = spring({ frame: f, fps, config: { damping: 18, stiffness: 120 } });
  const press = f >= 46 ? spring({ frame: f - 46, fps, config: { damping: 8, stiffness: 260 } }) : 0;
  const glow = interpolate(f, [0, 20], [0, 1], clamp);
  return (
    <Center>
      <div style={{ width: w * (0.6 + 0.4 * inP), padding: 2, borderRadius: 999, backgroundImage: GRAD, opacity: inP,
        boxShadow: `0 0 ${60 * glow}px rgba(155,123,255,${0.45 * glow}), 0 0 ${140 * glow}px rgba(240,138,36,${0.18 * glow})` }}>
        <div style={{ height: 112, borderRadius: 999, background: "#0b0f1c", display: "flex", alignItems: "center", padding: "0 18px 0 44px", gap: 20 }}>
          <div style={{ flex: 1, fontFamily: F.sans, fontSize: 38, fontWeight: 500, color: "#e8edff", whiteSpace: "nowrap", overflow: "hidden" }}>
            {text.slice(0, typed)}
            <span style={{ display: "inline-block", width: 3, height: 40, marginLeft: 4, verticalAlign: "middle", background: "#fff", opacity: Math.floor(f / 8) % 2 ? 0.2 : 1 }} />
          </div>
          <div style={{ width: 80, height: 80, borderRadius: "50%", backgroundImage: GRAD, display: "grid", placeItems: "center", transform: `scale(${1 - 0.12 * Math.sin(press * Math.PI)})`,
            boxShadow: `0 0 ${f >= 46 ? 50 : 0}px rgba(240,138,36,0.7)` }}>
            <Icon name="phone" size={36} color="#fff" />
          </div>
        </div>
      </div>
    </Center>
  );
};

/** Rings going out from the call, one a beat, while it rings. */
const Ringing: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f, fps, config: { damping: 14, stiffness: 120 } });
  return (
    <AbsoluteFill>
      <svg width="100%" height="100%" style={{ position: "absolute" }}>
        <defs>
          <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#5b8cff" /><stop offset="50%" stopColor="#9b7bff" /><stop offset="100%" stopColor="#f08a24" />
          </linearGradient>
        </defs>
        {Array.from({ length: 7 }, (_, k) => {
          const age = f - k * 15;
          if (age < 0) return null;
          const t = Math.min(1, age / 45);
          return <circle key={k} cx="50%" cy="50%" r={170 + t * 380} fill="none" stroke="url(#ring)" strokeWidth={3 - t * 2} opacity={(1 - t) * 0.9} />;
        })}
        <circle cx="50%" cy="50%" r={170 * p} fill="none" stroke="url(#ring)" strokeWidth={3} />
      </svg>
      <Center gap={26}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "20px 34px", borderRadius: 999, backgroundImage: "linear-gradient(95deg, #f08a24, #ff6b8b 60%, #9b7bff)", transform: `scale(${p})`,
          boxShadow: "0 20px 80px -10px rgba(240,138,36,0.6)", fontFamily: F.sans, fontSize: 34, fontWeight: 600, color: "#fff" }}>
          <div style={{ transform: `rotate(${Math.sin(f / 2) * (f % 30 < 15 ? 12 : 0)}deg)` }}><Icon name="phone" size={34} color="#fff" /></div>
          Calling રમેશભાઈ
          <span style={{ letterSpacing: 2 }}>{".".repeat(1 + (Math.floor(f / 8) % 3))}</span>
        </div>
      </Center>
    </AbsoluteFill>
  );
};

const Opening: React.FC = () => (
  <AbsoluteFill>
    <Sequence durationInFrames={s(2)}><Particles count={18} /><Scatter text="every month," /></Sequence>
    <Sequence from={s(2)} durationInFrames={s(1)}><Word text="every trader" /></Sequence>
    <Sequence from={s(3)} durationInFrames={s(1)}><Word text="who sells on credit" /></Sequence>
    <Sequence from={s(4)} durationInFrames={s(1)}><Word text="makes" /></Sequence>
    <Sequence from={s(5)} durationInFrames={s(1)}><Word text={<>the same call<Dot delay={7} /></>} /></Sequence>
    <Sequence from={s(6)} durationInFrames={s(2)}>
      <Center gap={14}>
        <Pop size={104} grad weight={700}>ભાઈ, પેમેન્ટ ક્યારે મોકલશો?</Pop>
        <Pop size={34} delay={10} weight={500} color="rgba(220,228,255,0.6)">“Bhai, when will you send the payment?”</Pop>
      </Center>
    </Sequence>
    <Sequence from={s(8)} durationInFrames={s(1)}><Word text="Hundreds" ghost="100s" /></Sequence>
    <Sequence from={s(9)} durationInFrames={s(1)}><Word text="of calls." ghost="100s" /></Sequence>
    <Sequence from={s(10)} durationInFrames={s(1)}><Word text="Every promise" /></Sequence>
    <Sequence from={s(11)} durationInFrames={s(1)}><Word text="on paper." /></Sequence>
    <Sequence from={s(12)} durationInFrames={s(1)}><Word text="Meet" /></Sequence>
    <Sequence from={s(13)} durationInFrames={s(1.2)}>
      <Center gap={10}>
        <Pop size={190} grad weight={700}>કાવ્યા</Pop>
        <Pop size={36} delay={8} weight={500} color="rgba(220,228,255,0.65)">She makes the calls for you.</Pop>
      </Center>
    </Sequence>
    <Sequence from={s(14.2)} durationInFrames={s(1.8)}><QueueBar /></Sequence>
    <Sequence from={s(16)} durationInFrames={s(3.4)}><Ringing /></Sequence>
  </AbsoluteFill>
);

// --- the call, 19.4-46 s -------------------------------------------------------------------

type Name = keyof typeof lines;
const ENGLISH: Partial<Record<Name, string>> = {
  k_hello: "Hello, Rameshbhai?",
  c_ha_bolo: "Yes, go ahead.",
  k_intro: "Namaste. This is Kavya from Genius Polyplast.",
  k_ask: "₹1,20,000 is pending from the October bill, when will you…",
  c_discount: "Give me a small discount and I'll pay half on Friday.",
  k_handover: "I'll speak to Sheth about that, he'll call you.",
  k_rest: "So ₹60,000 on Friday, and the rest when?",
  c_rest: "The rest on the 14th, by RTGS.",
  k_bye: "Great, thank you Rameshbhai. Bye.",
};

// (line, gap before it, cut after N seconds). k_ask is cut when the dealer talks over her.
const PLAN: [Name, number, number?][] = [
  ["k_hello", 0.5], ["c_ha_bolo", 0.3], ["k_intro", 0.3], ["k_ask", 0.15, 2.55], ["c_discount", -0.25],
  ["k_handover", 1.4], ["k_rest", 0.2], ["c_rest", 0.2], ["k_bye", 0.3],
];
type Beat = { name: Name; from: number; frames: number; kavya: boolean; cut: boolean };
const BEATS: Beat[] = (() => {
  let t = 0;
  return PLAN.map(([name, gap, cut]) => {
    t += gap;
    const sec = cut ?? lines[name].seconds;
    const b = { name, from: s(t), frames: s(sec), kavya: lines[name].who === "kavya", cut: cut !== undefined };
    t += sec;
    return b;
  });
})();
const at = (n: Name) => BEATS.find((b) => b.name === n)!;
export const CALL_LEN = s(26.6);

const CALLOUTS: { from: number; to: number; icon: Parameters<typeof Icon>[0]["name"]; text: string; tone: string }[] = [
  { from: 0, to: at("k_intro").from + s(2.5), icon: "ear", text: "Waits for their “હા” before she speaks", tone: "#8fb0ff" },
  { from: at("c_discount").from, to: at("c_discount").from + s(2.1), icon: "pause", text: "Talked over? She stops in 0.25 s", tone: "#8fb0ff" },
  { from: at("c_discount").from + s(2.1), to: at("k_handover").from + s(2.4), icon: "shield", text: "Discounts are the owner's call. Blocked.", tone: "#ff8a8a" },
  { from: at("k_rest").from, to: at("k_bye").from, icon: "calendar", text: "A date, an amount and a mode, every time", tone: "#7ee2b8" },
  { from: at("k_bye").from, to: CALL_LEN, icon: "check", text: "Promise saved. Owner's task created.", tone: "#7ee2b8" },
];

/** A glowing orb that breathes with the real voice. */
const Orb: React.FC<{ src?: string; kavya: boolean; quiet?: boolean }> = ({ src, kavya, quiet }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const data = useAudioData(src ?? staticFile("audio/k_hello.wav"));
  let amp = 0.04 + 0.03 * Math.sin(f / 6);
  if (src && data && !quiet) {
    const v = visualizeAudio({ fps, frame: f, audioData: data, numberOfSamples: 16 });
    amp = Math.min(1, (v.slice(0, 8).reduce((a, b) => a + b, 0) / 8) * 4);
  }
  const col = kavya ? ["#5b8cff", "#9b7bff"] : ["#f08a24", "#ff6b8b"];
  return (
    <div style={{ position: "relative", width: 260, height: 260, display: "grid", placeItems: "center" }}>
      <div style={{ position: "absolute", inset: -80, borderRadius: "50%", background: `radial-gradient(circle, ${col[0]}55 0%, transparent 65%)`, transform: `scale(${1 + amp * 0.5})` }} />
      <div style={{ width: 200, height: 200, borderRadius: "50%", backgroundImage: `radial-gradient(circle at 30% 25%, #ffffffcc 0%, ${col[0]} 35%, ${col[1]} 75%, #1a1033 100%)`,
        transform: `scale(${1 + amp * 0.28})`, boxShadow: `0 0 ${60 + amp * 90}px ${col[0]}aa` }} />
    </div>
  );
};

/** The line being said: words light up as they're spoken. */
const Line: React.FC<{ b: Beat }> = ({ b }) => {
  const f = useCurrentFrame();
  const { width } = useVideoConfig();
  const words = lines[b.name].text.split(" ");
  const full = lines[b.name].seconds;
  const lit = interpolate(f, [2, s(full) - 4], [0, words.length], clamp);
  return (
    <div style={{ maxWidth: Math.min(1500, width * 0.86), display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
      <Pop size={56} weight={600}>
        {words.map((w, i) => {
          const spoken = f < b.frames || !b.cut ? lit > i : false;
          return <span key={i} style={{ opacity: spoken ? 1 : 0.25, transition: "none" }}>{w}{i < words.length - 1 ? " " : ""}</span>;
        })}
        {b.cut && f >= b.frames && <span style={{ color: "#8fb0ff" }}>—</span>}
      </Pop>
      <Pop size={30} weight={500} delay={4} color="rgba(220,228,255,0.6)">{ENGLISH[b.name]}</Pop>
    </div>
  );
};

/** The draft reply the checker struck out, in the silence before she answers. */
const Struck: React.FC = () => {
  const f = useCurrentFrame();
  const strike = interpolate(f, [12, 24], [0, 1], { ...clamp, easing: ease });
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
      <Pop size={22} weight={600} color="#ff8a8a" style={{ letterSpacing: "0.12em", textTransform: "uppercase" }}>draft reply</Pop>
      <div style={{ position: "relative" }}>
        <Pop size={56} weight={600} color={strike > 0.9 ? "#ff8a8a" : "#fff"}>તો 2% ડિસ્કાઉન્ટ આપી દઈએ.</Pop>
        <div style={{ position: "absolute", left: -10, top: "52%", height: 5, borderRadius: 3, background: "#ff5a5a", width: `calc(${strike * 100}% + 20px)` }} />
      </div>
      <Pop size={30} weight={500} delay={4} color="rgba(255,170,170,0.7)">“Fine, take 2% off.” Never said out loud.</Pop>
    </div>
  );
};

const CallScene: React.FC = () => {
  const f = useCurrentFrame();
  const { height } = useVideoConfig();
  const current = [...BEATS].reverse().find((b) => f >= b.from) ?? BEATS[0];
  const next = BEATS[BEATS.indexOf(current) + 1];
  const checking = current.name === "c_discount" && f >= current.from + current.frames;
  const callout = CALLOUTS.find((c) => f >= c.from && f < c.to);
  const secs = Math.floor(f / FPS);
  const kavya = checking ? true : current.kavya;
  const end = interpolate(f, [CALL_LEN - 10, CALL_LEN], [1, 0], clamp);
  return (
    <AbsoluteFill style={{ opacity: Math.min(end, interpolate(f, [0, 8], [0, 1], clamp)) }}>
      {BEATS.map((b) => (
        <Sequence key={b.name} from={b.from} durationInFrames={b.frames}>
          <Audio src={staticFile(`audio/${b.name}.wav`)} volume={(x) => (b.cut ? interpolate(x, [b.frames - 4, b.frames], [1, 0], clamp) : 1)} />
        </Sequence>
      ))}
      <AbsoluteFill style={{ background: `radial-gradient(50% 45% at 50% 40%, ${kavya ? "rgba(91,140,255,0.16)" : "rgba(240,138,36,0.14)"}, transparent 70%)` }} />

      <div style={{ position: "absolute", top: 56, left: 0, right: 0, display: "flex", justifyContent: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 22px", borderRadius: 999, border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", fontFamily: F.sans, fontSize: 24, fontWeight: 500, color: "rgba(230,236,255,0.8)" }}>
          <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#ff5a5a", opacity: Math.floor(f / 15) % 2 ? 0.4 : 1 }} />
          Live call · 00:{String(secs).padStart(2, "0")}
        </div>
      </div>

      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 26, paddingBottom: height * 0.02 }}>
        <div style={{ height: 70 }}>
          {callout && (
            <Sequence from={callout.from} layout="none">
              <Pop size={30} weight={600} color={callout.tone}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 12, padding: "12px 24px", borderRadius: 999, background: "rgba(255,255,255,0.05)", border: `1px solid ${callout.tone}55` }}>
                  <Icon name={callout.icon} size={28} color={callout.tone} />{callout.text}
                </span>
              </Pop>
            </Sequence>
          )}
        </div>
        <Sequence from={current.from} durationInFrames={(next?.from ?? CALL_LEN) - current.from} layout="none">
          <Orb src={staticFile(`audio/${current.name}.wav`)} kavya={kavya} quiet={checking} />
        </Sequence>
        <div style={{ fontFamily: F.sans, fontSize: 28, fontWeight: 600, color: kavya ? "#a9c1ff" : "#ffc48a", letterSpacing: "0.02em" }}>
          {kavya ? "કાવ્યા · AI agent" : "રમેશભાઈ · dealer"}
        </div>
        <div style={{ minHeight: 190, display: "flex", alignItems: "flex-start", justifyContent: "center" }}>
          {checking ? (
            <Sequence from={current.from + current.frames} layout="none"><Struck /></Sequence>
          ) : (
            <Sequence from={current.from} layout="none"><Line b={current} /></Sequence>
          )}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// --- after the call, 46-70 s ------------------------------------------------------------------

const Outcome: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f, fps, config: { damping: 16, stiffness: 120 } });
  const row = (icon: Parameters<typeof Icon>[0]["name"], text: string, col: string, d: number) => (
    <div style={{ display: "flex", alignItems: "center", gap: 18, opacity: interpolate(f, [d, d + 6], [0, 1], clamp), transform: `translateX(${interpolate(f, [d, d + 10], [-20, 0], { ...clamp, easing: ease })}px)` }}>
      <div style={{ width: 52, height: 52, borderRadius: 14, background: `${col}22`, display: "grid", placeItems: "center" }}><Icon name={icon} size={28} color={col} /></div>
      <span style={{ fontFamily: F.sans, fontSize: 34, fontWeight: 500, color: "#eef2ff" }}>{text}</span>
    </div>
  );
  return (
    <Center>
      <div style={{ padding: "40px 48px", borderRadius: 28, background: "linear-gradient(180deg, #10162a, #0b0f1c)", border: "1px solid rgba(255,255,255,0.09)", display: "flex", flexDirection: "column", gap: 22,
        transform: `translateY(${(1 - p) * 40}px) scale(${0.94 + 0.06 * p})`, opacity: p, boxShadow: "0 40px 120px -30px rgba(91,140,255,0.35)" }}>
        <div style={{ fontFamily: F.sans, fontSize: 24, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: "rgba(220,228,255,0.5)" }}>રમેશભાઈ · after the call</div>
        {row("rupee", "₹60,000 on Friday", "#7ee2b8", 8)}
        {row("calendar", "₹60,000 on the 14th, by RTGS", "#7ee2b8", 14)}
        {row("hand", "Asked for a discount: you call him", C.saffron, 20)}
      </div>
    </Center>
  );
};

const LOG: { icon: Parameters<typeof Icon>[0]["name"]; who: string; what: string; tag: string; col: string }[] = [
  { icon: "phone", who: "રમેશભાઈ", what: "₹60,000 Fri + ₹60,000 on the 14th · RTGS", tag: "Promised", col: "#7ee2b8" },
  { icon: "hand", who: "Your task", what: "Call રમેશભાઈ about the discount", tag: "For you", col: C.saffron },
  { icon: "phone", who: "કાંતાબેન", what: "₹40,000 by Wednesday · UPI", tag: "Promised", col: "#7ee2b8" },
  { icon: "clock", who: "મહેશભાઈ", what: "Busy at the shop · call back at 4 pm", tag: "Callback", col: "#8fb0ff" },
  { icon: "phoneOff", who: "દિનેશભાઈ", what: "No answer · tries again tomorrow", tag: "Retry", col: "rgba(220,228,255,0.55)" },
];

const CallLog: React.FC = () => {
  const f = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const w = Math.min(1000, width * 0.88);
  return (
    <Center gap={16}>
      <Pop size={30} weight={600} color="rgba(220,228,255,0.55)" style={{ marginBottom: 10 }}>Every call, written down for you</Pop>
      {LOG.map((r, i) => {
        const p = spring({ frame: f - 4 - i * 7, fps, config: { damping: 18, stiffness: 140 } });
        return (
          <div key={i} style={{ width: w * (0.92 + 0.08 * p), height: 92, borderRadius: 22, background: "#0e1322", border: "1px solid rgba(255,255,255,0.08)", display: "flex", alignItems: "center", gap: 20, padding: "0 26px",
            opacity: p, transform: `translateY(${(1 - p) * 60}px)`, filter: `blur(${(1 - p) * 8}px)` }}>
            <div style={{ width: 52, height: 52, borderRadius: 14, background: `${r.col}22`, display: "grid", placeItems: "center", flexShrink: 0 }}><Icon name={r.icon} size={26} color={r.col} /></div>
            <div style={{ flex: 1, minWidth: 0, fontFamily: F.sans }}>
              <div style={{ fontSize: 28, fontWeight: 600, color: "#fff" }}>{r.who}</div>
              <div style={{ fontSize: 22, color: "rgba(220,228,255,0.6)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.what}</div>
            </div>
            <span style={{ fontFamily: F.sans, fontSize: 20, fontWeight: 600, color: r.col, padding: "8px 16px", borderRadius: 999, background: `${typeof r.col === "string" && r.col.startsWith("#") ? r.col : "#ffffff"}1a`, flexShrink: 0 }}>{r.tag}</span>
          </div>
        );
      })}
    </Center>
  );
};

const STACK: { icon: Parameters<typeof Icon>[0]["name"]; label: string; by: string; bg: string }[] = [
  { icon: "ear", label: "Listens", by: "Gnani Prisma", bg: "radial-gradient(circle at 30% 25%, #9cc0ff, #2f6bff 60%, #1d2f7a)" },
  { icon: "brain", label: "Thinks", by: "Gemini + rules", bg: "radial-gradient(circle at 30% 25%, #d9c8ff, #8b5cf6 60%, #3b1f7a)" },
  { icon: "volume", label: "Speaks", by: "Gnani Timbre", bg: "radial-gradient(circle at 30% 25%, #ffd2a8, #f08a24 60%, #8a3d0b)" },
];

const Stack: React.FC = () => {
  const f = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const spread = spring({ frame: f - 22, fps, config: { damping: 16, stiffness: 90 } });
  const gap = Math.min(300, width * 0.28);
  return (
    <AbsoluteFill>
      <Particles count={22} seed={4} />
      <Center gap={70}>
        <div style={{ position: "relative", width: 10, height: 240 }}>
          {STACK.map((c, i) => {
            const p = spring({ frame: f - i * 4, fps, config: { damping: 12, stiffness: 160 } });
            const x = (i - 1) * (70 + (gap - 70) * spread);
            return (
              <div key={i} style={{ position: "absolute", left: x - 85, top: 0, width: 170, display: "flex", flexDirection: "column", alignItems: "center", gap: 18, zIndex: i === 1 ? 2 : 1 }}>
                <div style={{ width: 170, height: 170, borderRadius: "50%", backgroundImage: c.bg, display: "grid", placeItems: "center", transform: `scale(${p})`, boxShadow: "0 20px 60px -10px rgba(0,0,0,0.6)" }}>
                  <Icon name={c.icon} size={66} color="#fff" />
                </div>
                <div style={{ opacity: spread, textAlign: "center", fontFamily: F.sans }}>
                  <div style={{ fontSize: 32, fontWeight: 600, color: "#fff" }}>{c.label}</div>
                  <div style={{ fontSize: 22, color: "rgba(220,228,255,0.55)", whiteSpace: "nowrap" }}>{c.by}</div>
                </div>
              </div>
            );
          })}
        </div>
        <Sequence from={40} layout="none"><Pop size={64}>Built on <span style={{ backgroundImage: GRAD, WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent" }}>Gnani</span>.</Pop></Sequence>
      </Center>
    </AbsoluteFill>
  );
};

const Limits: React.FC = () => (
  <AbsoluteFill>
    <Sequence durationInFrames={s(1)}><Word text="No discounts." /></Sequence>
    <Sequence from={s(1)} durationInFrames={s(1)}><Word text="No new dates." /></Sequence>
    <Sequence from={s(2)}>
      <Particles count={30} burst seed={9} />
      <Center gap={30}>
        <Pop size={170} grad weight={700}>Your limits.</Pop>
        <Sequence from={14} layout="none">
          <Pop size={32} weight={500} color="rgba(220,228,255,0.65)">Checked in code before she says a word.</Pop>
        </Sequence>
      </Center>
    </Sequence>
  </AbsoluteFill>
);

const Desk: React.FC = () => {
  const f = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const p = spring({ frame: f, fps, config: { damping: 20, stiffness: 70 } });
  const w = width > 1500 ? 1240 : 940;
  return (
    <Center gap={34}>
      <Pop size={52}>Every rupee, <span style={{ backgroundImage: GRAD, WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent" }}>on your desk.</span></Pop>
      <div style={{ transform: `perspective(1800px) rotateX(${(1 - p) * 24}deg) translateY(${(1 - p) * 260}px) scale(${0.9 + 0.1 * p})`, opacity: Math.min(1, p * 1.4), transformOrigin: "50% 0%",
        boxShadow: "0 0 140px -30px rgba(91,140,255,0.45)", borderRadius: 20 }}>
        <Browser src={staticFile("screens/desk_today.png")} url="ugharani.onrender.com/app" width={w} zoom={[1, 1.12]} focus={[0.5, 0.2]} from={10} dur={110} />
      </div>
    </Center>
  );
};

const Outro: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const bloom = interpolate(f, [0, 16], [0, 1], { ...clamp, easing: ease });
  const swap = s(1.4);
  const p = spring({ frame: f - swap, fps, config: { damping: 14, stiffness: 120 } });
  const out = interpolate(f, [s(3.4), s(4)], [1, 0], clamp);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <Particles count={28} burst seed={13} />
      {f < swap ? (
        <Center>
          <div style={{ fontFamily: F.guj, fontSize: 200, fontWeight: 700, backgroundImage: GRAD, WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent",
            filter: `blur(${(1 - bloom) * 30}px)`, transform: `scale(${1.25 - 0.25 * bloom})`, opacity: bloom * interpolate(f, [swap - 6, swap], [1, 0], clamp), paddingBottom: 30 }}>ઉઘરાણી</div>
        </Center>
      ) : (
        <Center gap={30}>
          <div style={{ display: "flex", alignItems: "center", gap: 30, transform: `scale(${0.85 + 0.15 * p})`, opacity: p }}>
            <Mark size={130} />
            <div style={{ fontFamily: F.serif, fontSize: 130, color: "#fff", letterSpacing: "-0.01em", lineHeight: 1.1 }}>Ugharani</div>
          </div>
          <Sequence from={swap + 10} layout="none"><Pop size={38} weight={500} color="rgba(220,228,255,0.75)">ugharani.onrender.com</Pop></Sequence>
          <Sequence from={swap + 18} layout="none">
            <Pop size={26} weight={600} color="rgba(220,228,255,0.6)">
              <span style={{ padding: "10px 22px", borderRadius: 999, border: "1px solid rgba(255,255,255,0.15)" }}>Built on Gnani · #GnaniAI</span>
            </Pop>
          </Sequence>
        </Center>
      )}
    </AbsoluteFill>
  );
};

const After: React.FC = () => (
  <AbsoluteFill>
    <Sequence durationInFrames={s(2)}><Outcome /></Sequence>
    <Sequence from={s(2)} durationInFrames={s(1)}><Word text="Every call" /></Sequence>
    <Sequence from={s(3)} durationInFrames={s(1)}><Word text={<>ends up here<Dot delay={6} /></>} /></Sequence>
    <Sequence from={s(4)} durationInFrames={s(4)}><CallLog /></Sequence>
    <Sequence from={s(8)} durationInFrames={s(3)}><Stack /></Sequence>
    <Sequence from={s(11)} durationInFrames={s(5)}><Limits /></Sequence>
    <Sequence from={s(16)} durationInFrames={s(4)}><Desk /></Sequence>
    <Sequence from={s(20)}><Outro /></Sequence>
  </AbsoluteFill>
);

// --- the whole thing ---------------------------------------------------------------------------

const CALL_AT = s(19.4);
const AFTER_AT = s(46);

export const Kinetic: React.FC = () => (
  <AbsoluteFill style={{ background: BG }}>
    <Audio src={staticFile("music.mp3")} volume={(f) => interpolate(f, [CALL_AT - 10, CALL_AT + 10, AFTER_AT - 15, AFTER_AT], [0.9, 0.5, 0.5, 0.9], clamp)} />
    <Sequence durationInFrames={CALL_AT}><Opening /></Sequence>
    <Sequence from={CALL_AT} durationInFrames={CALL_LEN}><CallScene /></Sequence>
    <Sequence from={AFTER_AT}><After /></Sequence>
  </AbsoluteFill>
);
