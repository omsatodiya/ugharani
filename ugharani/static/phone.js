// The customer's phone in the demo: rings when Genius Polyplast's agent calls, then holds the call.
// Open as /phone.html?c=<customer name>; without ?c= it asks whose phone this is.

const $ = (id) => document.getElementById(id);
const customer = new URLSearchParams(location.search).get("c");
const RING_TIMEOUT_MS = 30000;

let audio = null;       // AudioContext, unlocked by the first tap
let ringer = null;      // interval id while ringing
let call = null;        // {id} of the ringing/active call
let seen = new Set();   // call ids already shown, so a declined call doesn't ring again
let ringTimer = null, tickTimer = null, wakeLock = null, startedAt = 0;

function show(id) {
  for (const s of document.querySelectorAll(".screen")) s.hidden = s.id !== id;
}

async function api(path, options) {
  const resp = await fetch(path, options);
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(body.detail || `HTTP ${resp.status}`);
  return body;
}

const post = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function initials(name) {
  return name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

// ---------- lock screen ----------

function tickClock() {
  const now = new Date();
  $("clock").textContent = now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
  $("date").textContent = now.toLocaleDateString("gu-IN", { weekday: "long", day: "numeric", month: "long" });
}

async function arm() {
  // Browsers only allow sound after a tap: unlock audio now, so the phone can ring later.
  audio = new (window.AudioContext || window.webkitAudioContext)();
  await audio.resume();
  try { wakeLock = await navigator.wakeLock?.request("screen"); } catch {}
  $("arm").hidden = true;
  $("ready").hidden = false;
  poll();
}

// ---------- ringtone: a soft marimba phrase, made in the browser (no audio file) ----------

function note(freq, at, length = 0.35) {
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(0.5, at + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
  osc.connect(gain).connect(audio.destination);
  osc.start(at);
  osc.stop(at + length + 0.05);
}

function phrase() {
  const t = audio.currentTime + 0.05;
  [784, 988, 1175, 988, 784, 988].forEach((f, i) => note(f, t + i * 0.16));
  navigator.vibrate?.([600, 300, 600]);
}

function startRinging() {
  phrase();
  ringer = setInterval(phrase, 2200);
}

function stopRinging() {
  clearInterval(ringer);
  ringer = null;
  navigator.vibrate?.(0);
}

// ---------- incoming call ----------

let caller = { name: "", place: "" };

async function poll() {
  try {
    const info = await api(`/phone/incoming?customer=${encodeURIComponent(customer)}`);
    caller = info.caller;
    $("owner").textContent = info.customer;
    if (info.call && !call && !seen.has(info.call.id)) ring(info.call);
  } catch {}
  setTimeout(poll, call ? 4000 : 1500);
}

function ring(incoming) {
  call = incoming;
  seen.add(incoming.id);
  for (const id of ["ring-avatar", "call-avatar"]) $(id).textContent = initials(caller.name);
  $("ring-name").textContent = caller.name;
  $("ring-place").textContent = `${caller.place} · મોબાઇલ`;
  show("ringing");
  startRinging();
  ringTimer = setTimeout(() => endRinging("missed"), RING_TIMEOUT_MS);
}

async function endRinging(status) {
  clearTimeout(ringTimer);
  stopRinging();
  const id = call?.id;
  call = null;
  show("lock");
  if (id) await post(`/calls/${id}/status`, { status }).catch(() => {});
}

async function answer() {
  clearTimeout(ringTimer);
  stopRinging();
  $("call-name").textContent = caller.name;
  $("call-timer").textContent = "કનેક્ટ થઈ રહ્યું છે…";
  show("incall");
  try {
    await post(`/calls/${call.id}/status`, { status: "in_progress" });
  } catch {
    return hangup("failed");
  }
  startedAt = Date.now();
  tickTimer = setInterval(() => ($("call-timer").textContent = duration()), 500);
  // Step 3 connects the live audio here.
}

function duration() {
  const s = Math.floor((Date.now() - startedAt) / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

async function hangup(status = "completed") {
  clearInterval(tickTimer);
  const id = call?.id;
  call = null;
  $("end-name").textContent = caller.name;
  $("end-text").textContent = startedAt ? `કૉલ પૂરો થયો · ${duration()}` : "કૉલ પૂરો થયો";
  startedAt = 0;
  show("ended");
  if (id) await post(`/calls/${id}/status`, { status }).catch(() => {});
  setTimeout(() => show("lock"), 2500);
}

// ---------- start ----------

async function pickCustomer() {
  show("pick");
  const people = await api("/customers").catch(() => []);
  $("pick-list").replaceChildren(...people.map((p) => {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = `/phone.html?c=${encodeURIComponent(p.name)}`;
    a.textContent = [p.name, p.firm, p.city].filter(Boolean).join(" · ");
    li.append(a);
    return li;
  }));
}

if (!customer) {
  pickCustomer();
} else {
  tickClock();
  setInterval(tickClock, 10000);
  $("arm").addEventListener("click", arm);
  $("accept").addEventListener("click", answer);
  $("decline").addEventListener("click", () => endRinging("declined"));
  $("hangup").addEventListener("click", () => hangup());
  $("mute").addEventListener("click", (e) => e.currentTarget.classList.toggle("on"));
  $("speaker").addEventListener("click", (e) => e.currentTarget.classList.toggle("on"));
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState === "visible" && wakeLock?.released) {
      try { wakeLock = await navigator.wakeLock.request("screen"); } catch {}
    }
  });
  show("lock");
}
