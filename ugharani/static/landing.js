// The landing page: the hero call plays out line by line (and loops), sections rise in as they
// scroll into view (Motion, see anim.js), the bar turns light once past the night sky, and the
// demo shows calls left today.

import { countUp, enter, pressable, ready, reveal } from "/anim.js";

const nav = document.getElementById("nav");
const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > window.innerHeight * 0.6);
window.addEventListener("scroll", onScroll, { passive: true });
onScroll();

// ---------- the example call ----------
const CALL = [
  ["k", "હેલો રમેશભાઈ?"],
  ["c", "હા બોલો."],
  ["k", "હા નમસ્તે. હું કાવ્યા બોલું છું જીનિયસ પોલીપ્લાસ્ટમાંથી."],
  ["k", "₹1,20,000 નું પેમેન્ટ બાકી છે, એ ક્યારે મોકલશો?"],
  ["c", "થોડું ડિસ્કાઉન્ટ આપો તો શુક્રવારે અડધા આપી દઉં."],
  ["guard", "Checker: a discount is outside your rules, so it's never offered"],
  ["k", "એ બાબતે હું શેઠને વાત કરી દઉં છું, એ તમને ફોન કરશે. તો શુક્રવારે ₹60,000, અને બાકીના?"],
  ["c", "બાકીના 14 તારીખે, RTGS."],
  ["k", "તો શુક્રવારે ₹60,000 અને 14 તારીખે ₹60,000 RTGS, બરાબર ને?"],
  ["c", "હા, બરાબર."],
  ["k", "સારું, આભાર રમેશભાઈ. આવજો."],
];
const convo = document.getElementById("convo");
const wave = document.getElementById("wave");
const timer = document.getElementById("timer");
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

// a speech-like waveform: thin bars, louder in the middle
for (let i = 0; i < 64; i++) {
  const bar = document.createElement("i");
  const shape = Math.sin((i / 63) * Math.PI) * 0.7 + 0.3;
  bar.style.setProperty("--h", `${Math.round(10 + shape * 30 * (0.5 + Math.random() * 0.5))}px`);
  bar.style.setProperty("--d", `${(-Math.random() * 1.2).toFixed(2)}s`);
  wave.append(bar);
}

let seconds = 0;
setInterval(() => {
  seconds += 1;
  timer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}, 1000);

function line([who, text]) {
  const li = document.createElement("li");
  li.className = who;
  if (who === "guard") {
    li.innerHTML = '<svg class="i"><use href="/icons.svg#shield"/></svg>';
    li.append(text);
  } else {
    li.textContent = text;
  }
  return li;
}

async function play() {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  for (;;) {
    seconds = 0;
    convo.replaceChildren();
    for (const item of CALL) {
      wave.classList.toggle("them", item[0] === "c");
      wave.classList.toggle("quiet", item[0] === "guard");
      const li = line(item);
      convo.append(li);
      enter(li, { y: 10, scale: item[0] === "guard" ? 0.9 : 0.97 });
      while (convo.children.length > 6) convo.firstElementChild.remove();
      await wait(item[0] === "guard" ? 1800 : 900 + item[1].length * 30);
    }
    wave.classList.add("quiet");
    await wait(3000);
  }
}

if (still) CALL.slice(-6).forEach((item) => convo.append(line(item)));
else play();

// ---------- motion: the hero comes in, then each section as it scrolls into view ----------
ready.then((m) => {
  document.documentElement.classList.remove("pre");
  if (!m) return;
  enter([".badge", ".hero h1", ".lede", ".cta-row", ".stage"], { y: 24, gap: 0.09 });
  enter(".stage .panel", { y: 30, delay: 0.35, gap: 0.12 });
  // .reveal items rise in together with their siblings, one after another
  const groups = new Map();
  for (const el of document.querySelectorAll(".reveal")) {
    const box = el.parentElement;
    groups.set(box, [...(groups.get(box) || []), el]);
  }
  for (const [box, kids] of groups) reveal(box, kids, { y: 22, gap: 0.08 });
  reveal(document.querySelector(".stats"), [...document.querySelectorAll(".stats > div")], { y: 16, gap: 0.08 });
  reveal(document.querySelector(".try-in"), [...document.querySelectorAll(".try-in > *")], { y: 18, gap: 0.07 });
  reveal(document.querySelector(".footer-in"), [...document.querySelectorAll(".footer-in > *")], { y: 18, gap: 0.08 });
  for (const b of document.querySelectorAll("[data-count]")) {
    const to = Number(b.dataset.count), unit = b.dataset.fmt;
    const fmt = (n) => unit === "s" ? `${n.toFixed(2)} s` : unit === "%" ? `${Math.round(n)}%` : String(Math.round(n));
    b.textContent = fmt(0);
    m.inView(b, () => countUp(b, to, fmt), { amount: 0.6 });
  }
  pressable(".btn");
});

// ---------- the live demo's budget ----------
fetch("/calls/hours")
  .then((r) => r.json())
  .then((h) => {
    if (h.demo_left == null) return;
    const left = document.getElementById("demo-left");
    left.hidden = false;
    left.textContent = h.demo_left > 0
      ? `${h.demo_left} demo calls left today on this public link.`
      : "Today's demo calls are used up. Watch the video, or come back tomorrow.";
  })
  .catch(() => {});
