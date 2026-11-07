import React from "react";
import { AbsoluteFill, Audio, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import lines from "./lines.json";
import { C, F, s } from "./theme";
import { Icon, NightSky, Pill, Rise, useSpring } from "./ui";

type Name = keyof typeof lines;

// What the dealer hears, in order: (line, gap before it in seconds, cut after N seconds).
// k_ask is cut off when the dealer talks over her: that's the point of the scene.
const PLAN: [Name, number, number?][] = [
  ["k_hello", 1.4],
  ["c_ha_bolo", 0.35],
  ["k_intro", 0.3],
  ["k_ask", 0.15, 2.55],
  ["c_discount", -0.25],
  ["k_handover", 2.1],   // (the checker's moment, in silence, before it)
  ["k_rest", 0.15],
  ["c_rest", 0.35],
  ["k_confirm", 0.3],
  ["c_yes", 0.2],
  ["k_bye", 0.3],
];

const ENGLISH: Record<Name, string> = {
  k_hello: "Hello, Rameshbhai?",
  c_ha_bolo: "Yes, go ahead.",
  k_intro: "Namaste. This is Kavya from Genius Polyplast.",
  k_ask: "₹1,20,000 is pending from the October bill, when will you…",
  c_discount: "Give me a small discount and I'll pay half on Friday.",
  k_handover: "I'll speak to Sheth about that, he'll call you.",
  k_rest: "So ₹60,000 on Friday, and the rest when?",
  c_rest: "The rest on the 14th, by RTGS.",
  k_confirm: "So ₹60,000 Friday and ₹60,000 on the 14th, RTGS, right?",
  c_yes: "Yes, that's right.",
  k_bye: "Great, thank you Rameshbhai. Bye.",
};

export type Beat = { name: Name; from: number; frames: number; who: string; text: string; cut: boolean };

export const BEATS: Beat[] = (() => {
  let t = 0;
  return PLAN.map(([name, gap, cut]) => {
    t += gap;
    const seconds = cut ?? lines[name].seconds;
    const beat = { name, from: s(t), frames: s(seconds), who: lines[name].who, text: lines[name].text, cut: cut !== undefined };
    t += seconds;
    return beat;
  });
})();
export const CALL_FRAMES = BEATS[BEATS.length - 1].from + BEATS[BEATS.length - 1].frames + s(1.2);
const at = (name: Name) => BEATS.find((b) => b.name === name)!;

// Callouts shown beside the call at its key moments.
const CALLOUTS: { from: number; to: number; icon: Parameters<typeof Icon>[0]["name"]; title: string; body: string; tone: "blue" | "bad" | "good" }[] = [
  { from: at("k_hello").from, to: at("k_intro").from + s(2), icon: "ear", title: "Waits for their \"હા\"", body: "Then says who she is, like your staff would", tone: "blue" },
  { from: at("c_discount").from, to: at("c_discount").from + s(2.2), icon: "pause", title: "Talked over? She stops.", body: "In 0.25 s, and listens", tone: "blue" },
  { from: at("c_discount").from + s(2.4), to: at("k_rest").from + s(1.5), icon: "shield", title: "\"Discount\" is outside your rules", body: "Never said. The owner gets a task.", tone: "bad" },
  { from: at("k_confirm").from, to: CALL_FRAMES, icon: "calendar", title: "A date, an amount, a mode", body: "₹60,000 Fri + ₹60,000 on the 14th · RTGS", tone: "good" },
];

export const CallScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const square = width === height;
  const answered = frame >= s(1.1);
  const speaking = BEATS.find((b) => frame >= b.from && frame < b.from + b.frames);
  const shown = BEATS.filter((b) => frame >= b.from).slice(-(square ? 4 : 5));
  const callout = CALLOUTS.find((c) => frame >= c.from && frame < c.to);
  const checker = frame >= at("c_discount").from + s(2.4) && frame < at("k_handover").from + s(0.2);

  return (
    <NightSky>
      {BEATS.map((b) => (
        <Sequence key={b.name} from={b.from} durationInFrames={b.frames}>
          <Audio src={staticFile(`audio/${b.name}.wav`)} volume={(f) => (b.cut ? interpolate(f, [b.frames - 4, b.frames], [1, 0], { extrapolateLeft: "clamp" }) : 1)} />
        </Sequence>
      ))}

      <AbsoluteFill style={{ flexDirection: square ? "column" : "row", alignItems: "center", justifyContent: "center", gap: square ? 28 : 90, padding: square ? 60 : 0 }}>
        {!square && <Phone answered={answered} speaking={speaking} />}
        <div style={{ width: square ? 960 : 860, display: "flex", flexDirection: "column", gap: 22 }}>
          {square && <CallHeader answered={answered} speaking={speaking} />}
          <div style={{ height: square ? 560 : 640, display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: 16, maskImage: "linear-gradient(transparent 0, #000 90px)" }}>
            {shown.map((b) => <Bubble key={b.name} beat={b} />)}
          </div>
          <div style={{ height: 120 }}>
            {callout && <Callout key={callout.title} {...callout} />}
          </div>
        </div>
      </AbsoluteFill>
      {checker && <Checker />}
    </NightSky>
  );
};

const Bubble: React.FC<{ beat: Beat }> = ({ beat }) => {
  const frame = useCurrentFrame();
  const p = useSpring(beat.from, { damping: 18, stiffness: 160, mass: 0.7 });
  const kavya = beat.who === "kavya";
  const live = frame < beat.from + beat.frames;
  return (
    <div style={{ alignSelf: kavya ? "flex-start" : "flex-end", maxWidth: "86%", opacity: Math.min(1, p), transform: `translateY(${(1 - p) * 24}px) scale(${0.94 + 0.06 * p})`, transformOrigin: kavya ? "left bottom" : "right bottom" }}>
      <div style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 600, color: kavya ? "#9fb8ff" : "#ffc58a", margin: kavya ? "0 0 6px 6px" : "0 6px 6px 0", textAlign: kavya ? "left" : "right", letterSpacing: 0.4 }}>
        {kavya ? "KAVYA · AI" : "RAMESHBHAI · DEALER"}{live && " ●"}
      </div>
      <div style={{ padding: "16px 22px", borderRadius: 26, borderBottomLeftRadius: kavya ? 8 : 26, borderBottomRightRadius: kavya ? 26 : 8,
        background: kavya ? "#fff" : C.saffron, color: kavya ? C.navy900 : "#fff",
        boxShadow: "0 18px 40px -20px rgba(0,0,0,0.6)" }}>
        <div style={{ fontFamily: F.guj, fontSize: 32, fontWeight: 600, lineHeight: 1.4 }}>{beat.cut ? "₹1,20,000 નું પેમેન્ટ બાકી છે, ઑક્ટોબરનું બિલ છે, એ —" : beat.text}</div>
        <div style={{ fontFamily: F.sans, fontSize: 21, opacity: 0.7, marginTop: 4 }}>{ENGLISH[beat.name]}</div>
      </div>
    </div>
  );
};

const Callout: React.FC<(typeof CALLOUTS)[number]> = ({ from, icon, title, body, tone }) => {
  const p = useSpring(from, { damping: 16, stiffness: 140, mass: 0.8 });
  const color = { blue: C.blue500, bad: "#ff6b70", good: "#34d399" }[tone];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20, padding: "18px 24px", borderRadius: 22, background: "rgba(255,255,255,0.08)",
      border: `1px solid ${color}55`, opacity: Math.min(1, p), transform: `translateX(${(1 - p) * -40}px)`, backdropFilter: "blur(8px)" }}>
      <div style={{ width: 60, height: 60, borderRadius: 16, display: "grid", placeItems: "center", background: `${color}26`, color }}>
        <Icon name={icon} size={32} />
      </div>
      <div>
        <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 30, color: "#fff" }}>{title}</div>
        <div style={{ fontFamily: F.sans, fontSize: 22, color: "rgba(255,255,255,0.7)", marginTop: 2 }}>{body}</div>
      </div>
    </div>
  );
};

/** The rules checker stopping a sentence: a red card over the call. */
const Checker: React.FC = () => {
  const start = at("c_discount").from + s(2.4);
  const frame = useCurrentFrame();
  const p = useSpring(start, { damping: 14, stiffness: 150, mass: 0.7 });
  const strike = interpolate(frame, [start + s(0.6), start + s(1.1)], [0, 100], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", background: `rgba(6,18,51,${0.55 * Math.min(1, p)})` }}>
      <div style={{ width: 980, padding: 36, borderRadius: 30, background: "#fff", transform: `scale(${0.85 + 0.15 * p})`, opacity: Math.min(1, p), boxShadow: "0 40px 100px -30px rgba(0,0,0,0.7)" }}>
        <Pill tone="bad"><Icon name="shield" size={24} /> Rules checker</Pill>
        <div style={{ fontFamily: F.sans, fontSize: 24, color: C.muted, margin: "22px 0 10px" }}>The reply Gemini wrote:</div>
        <div style={{ position: "relative", display: "inline-block", fontFamily: F.guj, fontSize: 44, fontWeight: 600, color: C.bad }}>
          "તો 2% ડિસ્કાઉન્ટ આપી દઈએ."
          <div style={{ position: "absolute", left: 0, top: "52%", height: 5, width: `${strike}%`, background: C.bad, borderRadius: 3 }} />
        </div>
        <div style={{ display: "flex", gap: 14, marginTop: 28, flexWrap: "wrap" }}>
          <Pill tone="bad"><Icon name="x" size={22} /> Discount: outside your rules</Pill>
          <Pill tone="good"><Icon name="check" size={22} /> Said instead: "શેઠ તમને ફોન કરશે"</Pill>
          <Pill tone="warn"><Icon name="hand" size={22} /> Task for the owner</Pill>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Wave: React.FC<{ active: boolean; color: string; bars?: number; h?: number }> = ({ active, color, bars = 28, h = 60 }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5, height: h }}>
      {Array.from({ length: bars }, (_, i) => {
        const shape = Math.sin((i / (bars - 1)) * Math.PI) * 0.7 + 0.3;
        const wobble = active ? 0.35 + 0.65 * Math.abs(Math.sin(frame / 3.1 + i * 1.7) * Math.cos(frame / 5.3 + i)) : 0.12;
        return <span key={i} style={{ width: 5, borderRadius: 3, height: Math.max(4, h * shape * wobble), background: color, opacity: active ? 0.95 : 0.4 }} />;
      })}
    </div>
  );
};

const CallHeader: React.FC<{ answered: boolean; speaking?: Beat }> = ({ answered, speaking }) => {
  const frame = useCurrentFrame();
  const secs = Math.max(0, Math.floor((frame - s(1.1)) / 30));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20, padding: "18px 24px", borderRadius: 24, background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.12)" }}>
      <div style={{ width: 64, height: 64, borderRadius: "50%", display: "grid", placeItems: "center", background: `linear-gradient(145deg, ${C.blue500}, ${C.navy800})`, color: "#fff", fontFamily: F.guj, fontSize: 28, fontWeight: 700 }}>ક</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontFamily: F.sans, fontSize: 28, fontWeight: 700, color: "#fff" }}>Kavya → Rameshbhai</div>
        <div style={{ fontFamily: F.sans, fontSize: 20, color: "rgba(255,255,255,0.65)" }}>{answered ? `00:${String(secs).padStart(2, "0")} · live call` : "Calling…"}</div>
      </div>
      <Wave active={!!speaking} color={speaking?.who === "dealer" ? C.saffron : C.blue500} bars={20} h={44} />
    </div>
  );
};

/** The dealer's phone: incoming call, then the call screen with a live waveform. */
const Phone: React.FC<{ answered: boolean; speaking?: Beat }> = ({ answered, speaking }) => {
  const frame = useCurrentFrame();
  const enter = useSpring(0);
  const ring = answered ? 0 : (frame % 24) / 24;
  const secs = Math.max(0, Math.floor((frame - s(1.1)) / 30));
  return (
    <div style={{ width: 430, height: 880, borderRadius: 64, padding: 14, background: "#0a0f1f", boxShadow: "0 0 0 3px #2a3550, 0 60px 120px -40px rgba(0,0,0,0.9)",
      transform: `translateY(${(1 - enter) * 80}px) rotate(${(1 - enter) * -4}deg)`, opacity: Math.min(1, enter) }}>
      <div style={{ position: "relative", width: "100%", height: "100%", borderRadius: 52, overflow: "hidden",
        background: `radial-gradient(80% 50% at 50% 0%, rgba(47,107,255,0.4), transparent 70%), linear-gradient(180deg, ${C.navy800}, ${C.navy950})`,
        display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 90, color: "#fff" }}>
        <div style={{ position: "absolute", top: 14, width: 120, height: 32, borderRadius: 18, background: "#0a0f1f" }} />
        <div style={{ fontFamily: F.sans, fontSize: 20, opacity: 0.75 }}>{answered ? `00:${String(secs).padStart(2, "0")}` : "Incoming call"}</div>
        <div style={{ marginTop: 34, width: 150, height: 150, borderRadius: "50%", display: "grid", placeItems: "center", fontFamily: F.sans, fontSize: 52, fontWeight: 600,
          background: `linear-gradient(145deg, ${C.blue500}, ${C.navy800})`,
          boxShadow: `0 0 0 ${10 + ring * 34}px rgba(47,107,255,${0.35 * (1 - ring)}), 0 0 0 10px rgba(255,255,255,0.06)` }}>GP</div>
        <div style={{ marginTop: 28, fontFamily: F.serif, fontSize: 46 }}>Genius Polyplast</div>
        <div style={{ fontFamily: F.guj, fontSize: 22, opacity: 0.7 }}>ગોંડલ, રાજકોટ · મોબાઇલ</div>
        <div style={{ marginTop: 60 }}>
          <Wave active={!!speaking} color={speaking?.who === "dealer" ? C.saffron : "#8fb0ff"} />
        </div>
        <div style={{ fontFamily: F.sans, fontSize: 19, marginTop: 14, opacity: 0.7, height: 24 }}>
          {speaking ? (speaking.who === "kavya" ? "Kavya is speaking" : "You are speaking") : answered ? "Listening…" : ""}
        </div>
        <div style={{ marginTop: "auto", marginBottom: 70, display: "flex", gap: answered ? 0 : 120 }}>
          {!answered && <RoundButton color="#ef4444" icon="phoneOff" />}
          <RoundButton color={answered ? "#ef4444" : "#22c55e"} icon={answered ? "phoneOff" : "phone"} bounce={!answered} />
        </div>
      </div>
    </div>
  );
};

const RoundButton: React.FC<{ color: string; icon: "phone" | "phoneOff"; bounce?: boolean }> = ({ color, icon, bounce }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ width: 92, height: 92, borderRadius: "50%", display: "grid", placeItems: "center", background: color, color: "#fff",
      transform: `translateY(${bounce ? -Math.abs(Math.sin(frame / 6)) * 12 : 0}px)`, boxShadow: "0 14px 30px rgba(0,0,0,0.45)" }}>
      <Icon name={icon} size={40} />
    </div>
  );
};
