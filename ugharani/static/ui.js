// Small UI pieces for the owner's desk, modelled on shadcn/ui (Date Picker, Switch) but in plain
// JS: no build step. Styles are in ui.css.

const SVG_NS = "http://www.w3.org/2000/svg";

/** A line icon from /icons.svg. */
export function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "i");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `/icons.svg#${name}`);
  svg.append(use);
  return svg;
}

const pad = (n) => String(n).padStart(2, "0");
export const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseIso = (s) => (s ? new Date(`${s}T00:00:00`) : null);
const WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

/**
 * shadcn's Date Picker: an outline button with a calendar icon; a popover with the month grid.
 * datePicker(host, { value, placeholder, onChange(isoOrNull), clearable })
 */
export function datePicker(host, { value = null, placeholder = "Pick a date", onChange = () => {}, clearable = false } = {}) {
  let selected = parseIso(value);
  let month = new Date((selected || new Date()).getFullYear(), (selected || new Date()).getMonth(), 1);

  host.classList.add("dp");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "dp-trigger";
  button.setAttribute("aria-haspopup", "dialog");
  const label = document.createElement("span");
  button.append(icon("calendar"), label);
  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "dp-clear";
  clear.setAttribute("aria-label", "Clear date");
  clear.append(icon("x"));
  const pop = document.createElement("div");
  pop.className = "dp-pop";
  pop.setAttribute("role", "dialog");
  pop.hidden = true;
  host.replaceChildren(button, ...(clearable ? [clear] : []), pop);

  function showLabel() {
    label.textContent = selected
      ? selected.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
      : placeholder;
    button.classList.toggle("empty", !selected);
    clear.hidden = !selected;
  }

  function render() {
    const head = document.createElement("div");
    head.className = "dp-head";
    const prev = navButton("chevron-left", "Previous month", -1);
    const next = navButton("chevron-right", "Next month", 1);
    const title = document.createElement("span");
    title.textContent = month.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
    head.append(prev, title, next);

    const grid = document.createElement("div");
    grid.className = "dp-grid";
    grid.setAttribute("role", "grid");
    for (const w of WEEKDAYS) {
      const h = document.createElement("span");
      h.className = "dp-wd";
      h.textContent = w;
      grid.append(h);
    }
    const start = new Date(month);
    start.setDate(1 - month.getDay());
    const today = isoDate(new Date());
    for (let i = 0; i < 42; i++) {
      const day = new Date(start);
      day.setDate(start.getDate() + i);
      const b = document.createElement("button");
      b.type = "button";
      b.className = "dp-day";
      b.textContent = day.getDate();
      const iso = isoDate(day);
      if (day.getMonth() !== month.getMonth()) b.classList.add("out");
      if (iso === today) b.classList.add("today");
      if (selected && iso === isoDate(selected)) b.classList.add("sel");
      b.onclick = () => {
        selected = day;
        showLabel();
        close();
        onChange(iso);
      };
      grid.append(b);
    }
    pop.replaceChildren(head, grid);
  }

  function navButton(name, aria, step) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "dp-nav";
    b.setAttribute("aria-label", aria);
    b.append(icon(name));
    b.onclick = () => {
      month = new Date(month.getFullYear(), month.getMonth() + step, 1);
      render();
    };
    return b;
  }

  function open() {
    if (selected) month = new Date(selected.getFullYear(), selected.getMonth(), 1);
    render();
    pop.hidden = false;
    button.setAttribute("aria-expanded", "true");
    setTimeout(() => document.addEventListener("click", outside), 0);
    document.addEventListener("keydown", onKey);
  }
  function close() {
    pop.hidden = true;
    button.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", outside);
    document.removeEventListener("keydown", onKey);
  }
  const outside = (e) => { if (!host.contains(e.target)) close(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };

  button.onclick = () => (pop.hidden ? open() : close());
  clear.onclick = () => {
    selected = null;
    showLabel();
    onChange(null);
  };
  showLabel();
  return {
    get value() { return selected ? isoDate(selected) : null; },
    set value(v) { selected = parseIso(v); showLabel(); },
  };
}

/**
 * A play / pause button for one audio clip, sharing one <audio> element: tapping another
 * clip's button stops this one, and the icon always shows what a tap will do.
 */
export function audioButton(button, player, getUrl) {
  button.classList.add("play-btn");
  const setIcon = (playing) => {
    button.replaceChildren(icon(playing ? "pause" : "play"));
    button.setAttribute("aria-label", playing ? "Pause" : "Play");
    button.classList.toggle("playing", playing);
  };
  const mine = () => player.dataset.owner === button.id;
  setIcon(false);
  for (const ev of ["play", "pause", "ended", "emptied"]) {
    player.addEventListener(ev, () => setIcon(mine() && !player.paused && !player.ended));
  }
  button.addEventListener("click", () => {
    const url = getUrl();
    if (!url) return;
    if (mine() && !player.paused) return player.pause();
    if (!mine() || !player.src.endsWith(url)) {
      player.dataset.owner = button.id;
      player.src = url;
    }
    player.play().catch(() => setIcon(false));
  });
  return {
    play() { button.click(); },
  };
}
