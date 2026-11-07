// Shared animations for every page, built on Motion (motion.dev), loaded from a pinned CDN build.
// If Motion can't load, or the visitor prefers reduced motion, every helper does nothing and
// the page simply shows its final state: animation is never needed to read or use anything.

const MOTION = "https://cdn.jsdelivr.net/npm/motion@14.10.1/+esm";
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

let M = null;
export const ready = still
  ? Promise.resolve(null)
  : import(MOTION).then((m) => (M = m)).catch(() => null);

// One feel everywhere: a soft spring for movement, a short ease for fades.
const SPRING = { type: "spring", stiffness: 260, damping: 30, mass: 0.9 };
const EASE = [0.22, 1, 0.36, 1];

/** Elements from a selector, an element, a NodeList, or an array mixing them. */
const list = (els) => [].concat(typeof els === "string" || els instanceof Element ? [els] : [...(els || [])])
  .flatMap((e) => (typeof e === "string" ? [...document.querySelectorAll(e)] : [e]))
  .filter((e) => e instanceof Element);

/** Fade and rise in, children one after another. */
export function enter(els, { y = 14, delay = 0, gap = 0.06, scale = 1 } = {}) {
  const items = list(els);
  if (!M || !items.length) return;
  M.animate(items, { opacity: [0, 1], y: [y, 0], scale: [scale, 1] },
    { ...SPRING, opacity: { duration: 0.45, ease: EASE }, delay: M.stagger(gap, { startDelay: delay }) });
}

/** Like enter(), but waits until `container` scrolls into view (once); `kids` come in one by one. */
export function reveal(container, kids = [container], opts = {}) {
  if (!M || !container) return;
  if (container.getBoundingClientRect().top < innerHeight * 0.92) return enter(kids, opts);
  kids.forEach((k) => { k.style.opacity = "0"; });
  M.inView(container, () => { enter(kids, opts); }, { amount: 0.12 });
}

/** Animate a number up to its value: ₹ amounts and counts on the stat tiles. */
export function countUp(el, to, format = (n) => String(Math.round(n))) {
  if (!M || !Number.isFinite(to)) { el.textContent = format(to); return; }
  const from = Number(el.dataset.n || 0);
  el.dataset.n = to;
  M.animate(from, to, { duration: 0.8, ease: EASE, onUpdate: (v) => { el.textContent = format(v); } });
}

/** A popover or dialog opening: a quick fade with a little scale. */
export function pop(el, { y = -4 } = {}) {
  if (!M || !el) return;
  M.animate(el, { opacity: [0, 1], y: [y, 0], scale: [0.97, 1] }, { duration: 0.18, ease: EASE });
}

/** Swap from one panel to the next (tabs, phone screens). */
export function swap(el, { y = 10 } = {}) {
  if (!M || !el) return;
  M.animate(el, { opacity: [0, 1], y: [y, 0] }, { ...SPRING, opacity: { duration: 0.3, ease: EASE } });
}

/** Slide a highlight (the active tab) to sit behind `target` inside `track`. */
export function slideTo(pill, target, track) {
  if (!pill || !target) return;
  const t = target.getBoundingClientRect(), r = track.getBoundingClientRect();
  const to = { x: t.left - r.left, y: t.top - r.top, width: t.width, height: t.height };
  if (!M || !pill.dataset.placed) {
    Object.assign(pill.style, { width: `${to.width}px`, height: `${to.height}px`, transform: `translate(${to.x}px, ${to.y}px)` });
    pill.dataset.placed = "1";
    return;
  }
  M.animate(pill, { x: to.x, y: to.y, width: to.width, height: to.height }, SPRING);
}

/** A gentle press on buttons: scale down while held. */
export function pressable(selector) {
  if (!M?.press) return;
  M.press(selector, (el) => {
    M.animate(el, { scale: 0.96 }, { duration: 0.1 });
    return () => M.animate(el, { scale: 1 }, SPRING);
  });
}
