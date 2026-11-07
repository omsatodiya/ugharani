// The landing page: the hero call plays out line by line (and loops), sections fade in on
// scroll, the bar turns light once past the night sky, and the demo shows calls left today.

const nav = document.getElementById("nav");
const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > window.innerHeight * 0.7);
window.addEventListener("scroll", onScroll, { passive: true });
onScroll();

// ---------- the example call ----------
const lines = [...document.querySelectorAll("#convo li")];
const wave = document.querySelector(".wave");
const timer = document.getElementById("timer");
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
let seconds = 0;

setInterval(() => {
  seconds += 1;
  timer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}, 1000);

function readingTime(li) {
  return li.classList.contains("guard") ? 1800 : 900 + li.textContent.length * 28;
}

async function play() {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  for (;;) {
    seconds = 0;
    lines.forEach((li) => li.classList.remove("in", "gone"));
    for (const [i, li] of lines.entries()) {
      // keep the card from growing forever: older lines leave as new ones come
      if (i >= 6) lines[i - 6].classList.add("gone");
      wave.classList.toggle("quiet", !li.classList.contains("k"));
      li.classList.add("in");
      await wait(readingTime(li));
    }
    wave.classList.add("quiet");
    await wait(3500);
  }
}

if (still) lines.forEach((li) => li.classList.add("in"));
else play();

// ---------- reveal on scroll ----------
const seen = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (e.isIntersecting) {
      e.target.classList.add("shown");
      seen.unobserve(e.target);
    }
  }
}, { threshold: 0.12 });
document.querySelectorAll(".reveal").forEach((el) => seen.observe(el));

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
