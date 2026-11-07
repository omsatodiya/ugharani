import React from "react";
import { AbsoluteFill, Easing, interpolate, Series, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { CALL_FRAMES, CallScene } from "./Call";
import { C, F, s } from "./theme";
import { Browser, DaySky, Icon, Mark, NightSky, Pill, Rise, useSpring } from "./ui";

// Scene lengths (frames at 30 fps). The call scene follows its real audio.
export const SCENES = {
  hook: s(4.2),
  question: s(3.6),
  problem: s(5),
  reveal: s(4.2),
  call: CALL_FRAMES,
  desk: s(7.5),
  rules: s(5),
  pipeline: s(5.2),
  outro: s(5),
};
export const TOTAL = Object.values(SCENES).reduce((a, b) => a + b, 0);

export const Launch: React.FC = () => (
  <AbsoluteFill style={{ background: C.navy950 }}>
    <Series>
      <Series.Sequence durationInFrames={SCENES.hook}><Hook /></Series.Sequence>
      <Series.Sequence durationInFrames={SCENES.question}><Question /></Series.Sequence>
      <Series.Sequence durationInFrames={SCENES.problem}><Problem /></Series.Sequence>
      <Series.Sequence durationInFrames={SCENES.reveal}><Reveal /></Series.Sequence>
      <Series.Sequence durationInFrames={SCENES.call}><CallScene /></Series.Sequence>
      <Series.Sequence durationInFrames={SCENES.desk}><Desk /></Series.Sequence>
      <Series.Sequence durationInFrames={SCENES.rules}><Rules /></Series.Sequence>
      <Series.Sequence durationInFrames={SCENES.pipeline}><Pipeline /></Series.Sequence>
      <Series.Sequence durationInFrames={SCENES.outro}><Outro /></Series.Sequence>
    </Series>
  </AbsoluteFill>
);

const useSquare = () => {
  const { width, height } = useVideoConfig();
  return width === height;
};

/** Words that pop in one by one, launch-video style. */
const Words: React.FC<{ text: string; start?: number; every?: number; size: number; color?: string; font?: string; highlight?: string[] }> = ({ text, start = 0, every = 4, size, color = "#fff", font = F.serif, highlight = [] }) => (
  <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: `0 ${size * 0.26}px`, fontFamily: font, fontSize: size, lineHeight: 1.08, color, letterSpacing: -1 }}>
    {text.split(" ").map((w, i) => (
      <Rise key={i} delay={start + i * every} y={size * 0.35}>
        <span style={{ color: highlight.includes(w) ? "#bcd3ff" : undefined, fontStyle: highlight.includes(w) ? "italic" : undefined }}>{w}</span>
      </Rise>
    ))}
  </div>
);

/** Fade the whole scene out at its end. */
const Out: React.FC<{ frames: number; children: React.ReactNode }> = ({ frames, children }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [frames - 8, frames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>;
};

// ---------- 1. hook ----------
const Hook: React.FC = () => {
  const sq = useSquare();
  return (
    <NightSky>
      <Out frames={SCENES.hook}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", padding: 120 }}>
          <Words text="Every trader in Gujarat who sells on credit" size={sq ? 76 : 92} every={3} />
          <div style={{ height: 18 }} />
          <Words text="pays someone to make one call." start={22} size={sq ? 76 : 92} every={3} highlight={["one", "call."]} />
        </AbsoluteFill>
      </Out>
    </NightSky>
  );
};

// ---------- 2. the call itself, in Gujarati ----------
const Question: React.FC = () => {
  const frame = useCurrentFrame();
  const p = useSpring(0, { damping: 14, stiffness: 120, mass: 0.9 });
  const sq = useSquare();
  return (
    <NightSky>
      <Out frames={SCENES.question}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 30 }}>
          <Pill tone="dark"><Icon name="phone" size={24} /> ઉઘરાણી · the payment follow-up call</Pill>
          <div style={{ fontFamily: F.guj, fontWeight: 700, fontSize: sq ? 92 : 124, color: "#fff", transform: `scale(${0.8 + 0.2 * p})`, opacity: Math.min(1, p),
            textShadow: "0 20px 60px rgba(47,107,255,0.45)", textAlign: "center", lineHeight: 1.25, padding: "0 60px" }}>
            "ભાઈ, પેમેન્ટ ક્યારે મોકલશો?"
          </div>
          <Rise delay={14}>
            <div style={{ fontFamily: F.serif, fontStyle: "italic", fontSize: 46, color: "rgba(255,255,255,0.7)" }}>"Brother, when will you send the payment?"</div>
          </Rise>
          <div style={{ position: "absolute", bottom: 90, fontFamily: F.sans, fontSize: 26, color: "rgba(255,255,255,0.5)", opacity: interpolate(frame, [40, 60], [0, 1], { extrapolateRight: "clamp" }) }}>
            asked hundreds of times a week
          </div>
        </AbsoluteFill>
      </Out>
    </NightSky>
  );
};

// ---------- 3. the problem ----------
const Problem: React.FC = () => {
  const sq = useSquare();
  const cards = [
    { icon: "rupee" as const, big: "₹10–15k", small: "a month for one staff member, just to make these calls" },
    { icon: "phone" as const, big: "100s", small: "of calls a week to dealers across Saurashtra" },
    { icon: "file" as const, big: "Paper", small: "promises noted on a sheet, follow-ups forgotten" },
  ];
  return (
    <NightSky>
      <Out frames={SCENES.problem}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 56 }}>
          <Rise><div style={{ fontFamily: F.serif, fontSize: sq ? 64 : 78, color: "#fff" }}>Ledgers went digital. <span style={{ color: "#bcd3ff", fontStyle: "italic" }}>The calls didn't.</span></div></Rise>
          <div style={{ display: "flex", flexDirection: sq ? "column" : "row", gap: 26 }}>
            {cards.map((c, i) => (
              <Rise key={c.big} delay={12 + i * 8} y={50}>
                <div style={{ width: sq ? 860 : 470, padding: 34, borderRadius: 28, background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.14)",
                  display: "flex", flexDirection: sq ? "row" : "column", alignItems: sq ? "center" : "flex-start", gap: 18 }}>
                  <div style={{ width: 64, height: 64, borderRadius: 18, display: "grid", placeItems: "center", background: "rgba(47,107,255,0.22)", color: "#9fb8ff" }}><Icon name={c.icon} size={32} /></div>
                  <div>
                    <div style={{ fontFamily: F.serif, fontSize: 64, color: "#fff", lineHeight: 1 }}>{c.big}</div>
                    <div style={{ fontFamily: F.sans, fontSize: 25, color: "rgba(255,255,255,0.7)", marginTop: 10, lineHeight: 1.4 }}>{c.small}</div>
                  </div>
                </div>
              </Rise>
            ))}
          </div>
        </AbsoluteFill>
      </Out>
    </NightSky>
  );
};

// ---------- 4. reveal ----------
const Reveal: React.FC = () => {
  const frame = useCurrentFrame();
  const p = useSpring(0, { damping: 12, stiffness: 110, mass: 0.9 });
  const glow = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: "clamp" });
  return (
    <NightSky light={0.15 * glow}>
      <Out frames={SCENES.reveal}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 34 }}>
          <div style={{ transform: `scale(${0.4 + 0.6 * p}) rotate(${(1 - p) * -20}deg)`, opacity: Math.min(1, p * 1.3) }}><Mark size={150} /></div>
          <Rise delay={10}><div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 104, color: "#fff", letterSpacing: -3 }}>Ugharani</div></Rise>
          <Rise delay={20}>
            <div style={{ fontFamily: F.serif, fontSize: 52, color: "rgba(255,255,255,0.85)", textAlign: "center" }}>
              Meet <span style={{ fontFamily: F.guj, color: "#bcd3ff" }}>કાવ્યા</span>. She makes the ઉઘરાણી call, <span style={{ fontStyle: "italic" }}>in Gujarati.</span>
            </div>
          </Rise>
        </AbsoluteFill>
      </Out>
    </NightSky>
  );
};

// ---------- 6. the owner's desk ----------
const Desk: React.FC = () => {
  const sq = useSquare();
  const half = s(3.6);
  const frame = useCurrentFrame();
  const first = frame < half;
  return (
    <DaySky>
      <Out frames={SCENES.desk}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 36 }}>
          <Rise key={first ? "a" : "b"} delay={first ? 0 : half}>
            <div style={{ fontFamily: F.serif, fontSize: sq ? 56 : 64, color: C.navy900, textAlign: "center", maxWidth: sq ? 920 : undefined, lineHeight: 1.1 }}>
              {first ? <>Notes write themselves, <i style={{ color: C.blue600 }}>seconds after the call.</i></> : <>You only take the calls <i style={{ color: C.blue600 }}>she hands over.</i></>}
            </div>
          </Rise>
          <Rise delay={first ? 6 : half + 4} y={60}>
            {first
              ? <Browser src={staticFile("screens/desk_calls.png")} url="ugharani.onrender.com/app/#calls" width={sq ? 980 : 1440} zoom={[1, 1.55]} focus={[0.78, 0.62]} from={14} dur={half - 20} />
              : <Browser src={staticFile("screens/desk_today.png")} url="ugharani.onrender.com/app/#today" width={sq ? 980 : 1440} zoom={[1.05, 1.3]} focus={[0.5, 0.35]} from={half + 6} dur={SCENES.desk - half - 10} />}
          </Rise>
        </AbsoluteFill>
      </Out>
    </DaySky>
  );
};

// ---------- 7. the owner's rules ----------
const Rules: React.FC = () => {
  const sq = useSquare();
  const may = ["A full payment within 7 days", "Parts, if all of it comes in 15 days", "RTGS, cheque, UPI or cash"];
  const never = ["Offer a discount", "Agree past your limit", "Threaten, or tell anyone else the dues"];
  return (
    <DaySky>
      <Out frames={SCENES.rules}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 44 }}>
          <Rise><div style={{ fontFamily: F.serif, fontSize: sq ? 60 : 72, color: C.navy900, textAlign: "center", maxWidth: sq ? 900 : undefined, lineHeight: 1.1 }}>You decide what she may agree to. <i style={{ color: C.blue600 }}>Code makes sure.</i></div></Rise>
          <div style={{ display: "flex", flexDirection: sq ? "column" : "row", gap: 24 }}>
            {[["She may", may, C.good, C.goodBg, "check"], ["She never", never, C.bad, C.badBg, "x"]].map(([title, items, color, bg, icon], col) => (
              <Rise key={title as string} delay={10 + (col as number) * 8} y={40}>
                <div style={{ width: sq ? 900 : 640, padding: 34, borderRadius: 28, background: bg as string, border: `1px solid ${color}33` }}>
                  <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 30, color: color as string, marginBottom: 18 }}>{title as string}</div>
                  {(items as string[]).map((t, i) => (
                    <Rise key={t} delay={20 + (col as number) * 8 + i * 5} y={14}>
                      <div style={{ display: "flex", alignItems: "center", gap: 14, fontFamily: F.sans, fontSize: 28, color: C.navy900, padding: "8px 0" }}>
                        <span style={{ color: color as string }}><Icon name={icon as "check" | "x"} size={28} stroke={2.6} /></span>{t}
                      </div>
                    </Rise>
                  ))}
                </div>
              </Rise>
            ))}
          </div>
        </AbsoluteFill>
      </Out>
    </DaySky>
  );
};

// ---------- 8. built on Gnani ----------
const Pipeline: React.FC = () => {
  const sq = useSquare();
  const frame = useCurrentFrame();
  const nodes = [
    { icon: "mic" as const, title: "Dealer's voice", sub: "phone audio", gnani: false },
    { icon: "ear" as const, title: "Gnani Prisma", sub: "live Gujarati STT", gnani: true },
    { icon: "brain" as const, title: "Her reply", sub: "streamed", gnani: false },
    { icon: "shield" as const, title: "Rules checker", sub: "your limits, in code", gnani: false },
    { icon: "volume" as const, title: "Gnani Timbre", sub: "voice: Tarika", gnani: true },
  ];
  const flow = interpolate(frame, [20, SCENES.pipeline - 20], [0, nodes.length], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.quad) });
  return (
    <NightSky>
      <Out frames={SCENES.pipeline}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 56 }}>
          <Rise><div style={{ fontFamily: F.serif, fontSize: sq ? 62 : 74, color: "#fff", textAlign: "center" }}>Built on <span style={{ color: "#bcd3ff", fontStyle: "italic" }}>Gnani</span>, end to end.</div></Rise>
          <div style={{ display: "flex", flexDirection: sq ? "column" : "row", alignItems: "center", gap: sq ? 14 : 18 }}>
            {nodes.map((n, i) => {
              const lit = flow > i;
              return (
                <React.Fragment key={n.title}>
                  {i > 0 && <div style={{ color: lit ? "#9fb8ff" : "rgba(255,255,255,0.25)", transform: sq ? "rotate(90deg)" : undefined }}><Icon name="arrow" size={30} /></div>}
                  <Rise delay={6 + i * 5} y={30}>
                    <div style={{ width: sq ? 620 : 300, padding: sq ? "16px 24px" : 26, borderRadius: 24, display: "flex", flexDirection: sq ? "row" : "column", alignItems: sq ? "center" : "flex-start", gap: 14,
                      background: n.gnani ? `linear-gradient(160deg, ${C.blue600}, ${C.navy700})` : "rgba(255,255,255,0.07)",
                      border: `1px solid ${lit ? "rgba(159,184,255,0.7)" : "rgba(255,255,255,0.14)"}`,
                      boxShadow: lit ? "0 0 40px -6px rgba(47,107,255,0.7)" : "none" }}>
                      <div style={{ width: 56, height: 56, borderRadius: 16, display: "grid", placeItems: "center", background: "rgba(255,255,255,0.12)", color: "#fff" }}><Icon name={n.icon} size={28} /></div>
                      <div>
                        <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 28, color: "#fff" }}>{n.title}</div>
                        <div style={{ fontFamily: F.sans, fontSize: 21, color: "rgba(255,255,255,0.7)" }}>{n.sub}</div>
                      </div>
                    </div>
                  </Rise>
                </React.Fragment>
              );
            })}
          </div>
          <Rise delay={40}><div style={{ fontFamily: F.sans, fontSize: 26, color: "rgba(255,255,255,0.65)" }}>She pauses in 0.25 s when talked over · speaks Gujarati and Hindi</div></Rise>
        </AbsoluteFill>
      </Out>
    </NightSky>
  );
};

// ---------- 9. outro ----------
const Outro: React.FC = () => {
  const p = useSpring(0, { damping: 13, stiffness: 120, mass: 0.9 });
  const sq = useSquare();
  return (
    <NightSky light={0.15}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 30 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 28, transform: `scale(${0.85 + 0.15 * p})`, opacity: Math.min(1, p) }}>
          <Mark size={110} />
          <div>
            <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 92, color: "#fff", letterSpacing: -3, lineHeight: 1 }}>Ugharani</div>
            <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 24, letterSpacing: 6, color: "rgba(255,255,255,0.6)", marginTop: 8 }}>AUTO ઉઘરાણી</div>
          </div>
        </div>
        <Rise delay={12}><div style={{ fontFamily: F.serif, fontSize: sq ? 50 : 58, color: "rgba(255,255,255,0.85)" }}>Let <span style={{ fontFamily: F.guj, color: "#bcd3ff" }}>કાવ્યા</span> make tomorrow's calls.</div></Rise>
        <Rise delay={22}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "18px 30px", borderRadius: 20, background: "#fff", color: C.navy900, fontFamily: F.sans, fontWeight: 700, fontSize: 36 }}>
            ugharani.onrender.com <span style={{ width: 46, height: 46, borderRadius: 12, display: "grid", placeItems: "center", background: C.navy900, color: "#fff" }}><Icon name="arrow" size={26} /></span>
          </div>
        </Rise>
        <Rise delay={32}><div style={{ fontFamily: F.sans, fontSize: 24, color: "rgba(255,255,255,0.55)", marginTop: 10 }}>Built on Gnani AI · #GnaniAI #GreatIndianAIInternshipChallenge</div></Rise>
      </AbsoluteFill>
    </NightSky>
  );
};
