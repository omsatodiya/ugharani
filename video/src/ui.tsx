import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, F } from "./theme";

/** 0 -> 1 with a soft spring, starting at `delay` frames. */
export function useSpring(delay = 0, config = { damping: 200, stiffness: 120, mass: 0.9 }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config });
}

/** Fade + rise in at `delay`, fade out over the last `out` frames before `end` (if given). */
export const Rise: React.FC<{ delay?: number; y?: number; end?: number; out?: number; style?: React.CSSProperties; children: React.ReactNode }> = ({ delay = 0, y = 30, end, out = 10, style, children }) => {
  const frame = useCurrentFrame();
  const p = useSpring(delay);
  const fadeOut = end ? interpolate(frame, [end - out, end], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 1;
  return (
    <div style={{ opacity: Math.min(p, 1) * fadeOut, transform: `translateY(${(1 - p) * y}px)`, ...style }}>{children}</div>
  );
};

/** The night sky: navy gradient, a few stars, two slow glows. */
export const NightSky: React.FC<{ children?: React.ReactNode; light?: number }> = ({ children, light = 0 }) => {
  const frame = useCurrentFrame();
  const drift = Math.sin(frame / 90) * 40;
  return (
    <AbsoluteFill style={{ background: `linear-gradient(180deg, ${C.navy950} 0%, ${C.navy900} 55%, ${C.navy800} 100%)`, overflow: "hidden" }}>
      <AbsoluteFill style={{ opacity: 0.55, backgroundImage: STARS }} />
      <div style={{ position: "absolute", width: 1100, height: 700, left: `calc(50% - 550px + ${drift}px)`, top: -380, borderRadius: "50%", background: "rgba(47,107,255,0.35)", filter: "blur(90px)" }} />
      <div style={{ position: "absolute", width: 1300, height: 600, left: `calc(50% - 650px - ${drift}px)`, bottom: -420, borderRadius: "50%", background: `rgba(120,160,255,${0.22 + light})`, filter: "blur(100px)" }} />
      {children}
    </AbsoluteFill>
  );
};

const STARS = [
  [12, 18, 1.5], [28, 8, 1], [44, 22, 2], [63, 12, 1], [78, 26, 1.5], [90, 9, 2], [6, 40, 1], [52, 4, 1],
  [35, 30, 1], [84, 38, 1.5], [18, 70, 1], [70, 80, 1.5], [93, 62, 1], [40, 88, 1], [58, 66, 1],
].map(([x, y, r]) => `radial-gradient(${r}px ${r}px at ${x}% ${y}%, #fff 50%, transparent 51%)`).join(",");

/** The light day sky behind the app scenes. */
export const DaySky: React.FC<{ children?: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ background: `radial-gradient(60% 40% at 85% 0%, rgba(255,255,255,0.9), transparent 70%), linear-gradient(180deg, ${C.sky200} 0%, ${C.sky100} 35%, ${C.sky50} 80%)` }}>
    {children}
  </AbsoluteFill>
);

export const Mark: React.FC<{ size?: number }> = ({ size = 96 }) => (
  <div style={{ width: size, height: size, borderRadius: size * 0.3, position: "relative", display: "grid", placeItems: "center",
    background: `linear-gradient(145deg, ${C.blue500}, ${C.navy900})`, color: "#fff", fontFamily: F.guj, fontWeight: 700, fontSize: size * 0.56,
    boxShadow: `0 ${size * 0.2}px ${size * 0.5}px -${size * 0.15}px rgba(47,107,255,0.8), inset 0 1px 0 rgba(255,255,255,0.25)` }}>
    ઉ
    <div style={{ position: "absolute", top: -size * 0.07, right: -size * 0.07, width: size * 0.26, height: size * 0.26, borderRadius: "50%", background: C.saffron, boxShadow: `0 0 0 ${size * 0.05}px ${C.navy900}` }} />
  </div>
);

/** A small rounded label. */
export const Pill: React.FC<{ tone?: "blue" | "good" | "bad" | "warn" | "dark"; children: React.ReactNode; style?: React.CSSProperties }> = ({ tone = "blue", children, style }) => {
  const t = {
    blue: [C.sky100, C.blue600], good: [C.goodBg, C.good], bad: [C.badBg, C.bad], warn: [C.warnBg, C.warn],
    dark: ["rgba(255,255,255,0.1)", "#cfe0ff"],
  }[tone];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 18px", borderRadius: 999, background: t[0], color: t[1],
      fontFamily: F.sans, fontWeight: 600, fontSize: 24, border: `1px solid ${tone === "dark" ? "rgba(255,255,255,0.18)" : "transparent"}`, ...style }}>{children}</span>
  );
};

/** Line icons (Lucide style), same as the app's icons.svg. */
export const Icon: React.FC<{ name: keyof typeof PATHS; size?: number; color?: string; stroke?: number }> = ({ name, size = 28, color = "currentColor", stroke = 2 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round">
    {PATHS[name]}
  </svg>
);

const PATHS = {
  phone: <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" />,
  phoneOff: <><path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7a2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91" /><path d="M22 2 2 22" /></>,
  shield: <><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" /><path d="m9 12 2 2 4-4" /></>,
  check: <path d="M20 6 9 17l-5-5" />,
  x: <><path d="M18 6 6 18" /><path d="m6 6 12 12" /></>,
  mic: <><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M19 10v1a7 7 0 0 1-14 0v-1" /><path d="M12 18v4" /></>,
  ear: <><path d="M6 8.5a6.5 6.5 0 1 1 13 0c0 6-6 6-6 10a3.5 3.5 0 1 1-7 0" /><path d="M15 8.5a2.5 2.5 0 0 0-5 0v1a2 2 0 1 1 0 4" /></>,
  brain: <><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" /><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" /><path d="M12 5v13" /></>,
  volume: <><path d="M11 5 6 9H2v6h4l5 4V5z" /><path d="M15.54 8.46a5 5 0 0 1 0 7.07" /><path d="M19.07 4.93a10 10 0 0 1 0 14.14" /></>,
  file: <><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z" /><path d="M14 2v5h5" /><path d="M16 13H8" /><path d="M16 17H8" /></>,
  hand: <><path d="M18 11V6a2 2 0 0 0-4 0" /><path d="M14 10V4a2 2 0 0 0-4 0v2" /><path d="M10 10.5V6a2 2 0 0 0-4 0v8" /><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15" /></>,
  clock: <><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></>,
  pause: <><rect x="6" y="4" width="4" height="16" rx="1" /><rect x="14" y="4" width="4" height="16" rx="1" /></>,
  arrow: <><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></>,
  calendar: <><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4" /><path d="M8 2v4" /><path d="M3 10h18" /></>,
  rupee: <><path d="M6 3h12" /><path d="M6 8h12" /><path d="m6 13 8.5 8" /><path d="M6 13h3" /><path d="M9 13c6.67 0 6.67-10 0-10" /></>,
  languages: <><path d="m5 8 6 6" /><path d="m4 14 6-6 2-3" /><path d="M2 5h12" /><path d="M7 2h1" /><path d="m22 22-5-10-5 10" /><path d="M14 18h6" /></>,
};

/** A browser window around a screenshot, with an optional slow zoom towards a point. */
export const Browser: React.FC<{ src: string; url: string; width: number; zoom?: [number, number]; focus?: [number, number]; from?: number; dur?: number }> = ({ src, url, width, zoom = [1, 1], focus = [0.5, 0.3], from = 0, dur = 90 }) => {
  const frame = useCurrentFrame();
  const z = interpolate(frame, [from, from + dur], zoom, { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  const h = width * (900 / 1440);
  return (
    <div style={{ width, borderRadius: 20, overflow: "hidden", background: "#fff", boxShadow: "0 50px 120px -40px rgba(11,31,77,0.55), 0 0 0 1px rgba(11,31,77,0.08)" }}>
      <div style={{ height: 52, display: "flex", alignItems: "center", gap: 10, padding: "0 20px", background: "#f1f5fb", borderBottom: `1px solid ${C.line}` }}>
        {["#ff5f57", "#febc2e", "#28c840"].map((c) => <span key={c} style={{ width: 14, height: 14, borderRadius: "50%", background: c }} />)}
        <div style={{ marginLeft: 20, flex: 1, height: 32, borderRadius: 10, background: "#fff", border: `1px solid ${C.line}`, display: "flex", alignItems: "center", padding: "0 14px", fontFamily: F.sans, fontSize: 17, color: C.muted }}>{url}</div>
      </div>
      <div style={{ height: h, overflow: "hidden", position: "relative" }}>
        <Img src={src} style={{ width: "100%", transform: `scale(${z})`, transformOrigin: `${focus[0] * 100}% ${focus[1] * 100}%` }} />
      </div>
    </div>
  );
};
