// The customer's phone in the demo: rings when Genius Polyplast's agent calls, then holds the call.
// Open as /phone.html?c=<customer name>; without ?c= it asks whose phone this is.

const $ = (id) => document.getElementById(id);
const customer = new URLSearchParams(location.search).get("c");
const ownerKey = new URLSearchParams(location.search).get("k"); // the owner's demo key, if any
const withKey = (path) => (ownerKey ? `${path}${path.includes("?") ? "&" : "?"}k=${encodeURIComponent(ownerKey)}` : path);
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
  // Ask for the microphone now, not in the middle of a ringing call.
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());
  } catch {
    $("ready").textContent = "માઇક્રોફોનની પરવાનગી જરૂરી છે · Microphone permission needed";
  }
  $("arm").hidden = true;
  $("ready").hidden = false;
  $("call-now").hidden = false;
  poll();
}

async function callNow() {
  // Ask the server to place the call; the phone then rings through the normal polling.
  const button = $("call-now");
  button.disabled = true;
  $("call-now-msg").hidden = false;
  $("call-now-msg").textContent = "કૉલ લાગી રહ્યો છે… · Placing the call…";
  try {
    await post(withKey("/calls"), { customer });
    $("call-now-msg").hidden = true;
  } catch (e) {
    $("call-now-msg").textContent = e.message; // e.g. nothing pending for this customer
  } finally {
    setTimeout(() => { button.disabled = false; }, 5000);
  }
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
  try {
    await startLive(call.id);
  } catch (e) {
    console.warn("live audio failed", e);
    hangup("failed");
  }
}

// ---------- the live call: mic -> server -> agent's voice back, through a phone-line filter ----------

let live = null; // {ws, stream, mic, worklet, line, sources, playAt, opened, held (paused: her unplayed audio)}

function phoneLine() {
  // 300-3400 Hz, like a phone line, with a little hiss so the line never sounds dead.
  const hp = audio.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 300;
  const lp = audio.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 3400;
  const squash = audio.createDynamicsCompressor();
  squash.threshold.value = -24; squash.ratio.value = 4;
  const volume = audio.createGain();
  volume.gain.value = $("speaker").classList.contains("on") ? 1.8 : 1.0;
  hp.connect(lp).connect(squash).connect(volume).connect(audio.destination);

  const hiss = audio.createBuffer(1, audio.sampleRate * 2, audio.sampleRate);
  const d = hiss.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  const noise = audio.createBufferSource();
  noise.buffer = hiss; noise.loop = true;
  const quiet = audio.createGain(); quiet.gain.value = 0.006;
  noise.connect(quiet).connect(hp);
  noise.start();

  // Her voice goes through its own gain, so it can dip when the customer talks over her.
  const voice = audio.createGain();
  voice.connect(hp);
  return { input: voice, voice, volume, noise };
}

function duck(on) {
  // A quick, smooth dip (no click): like someone hesitating when talked over.
  live.line.voice.gain.setTargetAtTime(on ? 0.25 : 1.0, audio.currentTime, 0.03);
}

function clearPlayback() {
  // The customer interrupted: drop everything she hasn't said yet.
  for (const s of live.sources) { try { s.stop(); } catch {} }
  live.sources.clear();
  live.held = null;
  live.playAt = audio.currentTime;
  live.line.voice.gain.cancelScheduledValues(audio.currentTime);
  duck(false);
}

const FADE = 0.03;       // s: stopping or starting mid-word without a click
const REWIND_MAX = 0.4;  // s: on resume, go back to the gap before the word she was cut in

function quietPoint(data, at) {
  // The start of the last ~40 ms gap before sample `at`, within REWIND_MAX; else `at` itself.
  const win = 320, need = 2; // 20 ms windows at 16 kHz
  let quiet = 0;
  for (let end = at; end - win >= Math.max(0, at - REWIND_MAX * 16000); end -= win) {
    let sum = 0;
    for (let i = end - win; i < end; i++) sum += data[i] * data[i];
    quiet = Math.sqrt(sum / win) < 0.012 ? quiet + 1 : 0;
    if (quiet >= need) return end - win;
  }
  return at;
}

function pausePlayback() {
  // Talked over: stop at once (a quick fade), but keep what she hasn't said, to go on from there.
  if (live.held) return;
  const at = audio.currentTime + FADE;
  live.line.voice.gain.cancelScheduledValues(audio.currentTime);
  live.line.voice.gain.setTargetAtTime(0, audio.currentTime, FADE / 3);
  const held = [];
  for (const s of [...live.sources].sort((a, b) => a.at - b.at)) {
    const end = s.at + s.buffer.duration;
    if (end > at) {
      let from = Math.max(0, at - s.at);
      if (from > 0) from = quietPoint(s.buffer.getChannelData(0), Math.floor(from * 16000)) / 16000;
      held.push({ buffer: s.buffer, from });
    }
    s.onended = null;
    try { s.stop(at); } catch {}
  }
  live.sources.clear();
  live.held = held;
  live.playAt = at;
}

function resumePlayback() {
  // Go on from the gap before the word she stopped in, as a person picks up their sentence.
  const held = live.held;
  if (!held) return;
  live.held = null;
  live.line.voice.gain.cancelScheduledValues(audio.currentTime);
  live.line.voice.gain.setTargetAtTime(1.0, audio.currentTime + 0.02, FADE / 3);
  live.playAt = audio.currentTime + 0.02;
  for (const h of held) schedule(h.buffer, h.from);
}

function schedule(clip, from = 0) {
  const src = audio.createBufferSource();
  src.buffer = clip;
  src.connect(live.line.input);
  live.playAt = Math.max(live.playAt, audio.currentTime + 0.06); // a small jitter buffer
  src.at = live.playAt - from; // when its sample 0 would play
  src.start(live.playAt, from);
  live.playAt += clip.duration - from;
  live.sources.add(src);
  src.onended = () => live?.sources.delete(src);
}

function play(buf) {
  // The server sends 16 kHz PCM16; the browser resamples a 16 kHz buffer on playback.
  const pcm = new Int16Array(buf);
  if (!pcm.length) return;
  const clip = audio.createBuffer(1, pcm.length, 16000);
  const out = clip.getChannelData(0);
  for (let i = 0; i < pcm.length; i++) out[i] = pcm[i] / 32768;
  if (live.held) live.held.push({ buffer: clip, from: 0 }); // (paused: kept for later)
  else schedule(clip);
}

async function startLive(id) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
  });
  if (!audio.audioWorklet) throw new Error("no AudioWorklet in this browser");
  await audio.audioWorklet.addModule("/mic-worklet.js");
  const mic = audio.createMediaStreamSource(stream);
  const worklet = new AudioWorkletNode(audio, "mic-capture");
  const sink = audio.createGain(); sink.gain.value = 0; // keeps the worklet running, silently
  mic.connect(worklet).connect(sink).connect(audio.destination);
  worklet.port.postMessage({ muted: $("mute").classList.contains("on") });

  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${withKey(`/calls/${id}/live`)}`);
  ws.binaryType = "arraybuffer";
  live = { ws, stream, mic, worklet, line: phoneLine(), sources: new Set(), playAt: 0, opened: false, held: null };
  worklet.port.onmessage = (e) => { if (ws.readyState === WebSocket.OPEN) ws.send(e.data); };
  ws.onopen = () => { if (live) live.opened = true; };
  ws.onmessage = (e) => {
    if (typeof e.data !== "string") return play(e.data);
    const msg = JSON.parse(e.data);
    if (msg.type === "line") console.log(`[call] ${msg.who}: ${msg.text}`);
    else if (msg.type === "duck") duck(true);
    else if (msg.type === "unduck") duck(false);
    else if (msg.type === "clear") clearPlayback();
    else if (msg.type === "pause") pausePlayback();
    else if (msg.type === "resume") resumePlayback();
    else if (msg.type === "end") hangup("completed", { byAgent: true });
  };
  ws.onclose = (e) => {
    if (live?.ws !== ws) return; // we hung up ourselves
    // Closed by the server: the call is over and saved. Never opened: the server refused it.
    if (!live.opened) console.warn("live call refused", e.code);
    hangup(live.opened ? "completed" : "failed", { byAgent: live.opened });
  };
}

function stopLive() {
  if (!live) return;
  const { ws, stream, mic, worklet, line, sources } = live;
  live = null;
  for (const s of sources) { try { s.stop(); } catch {} }
  line.noise.stop();
  mic.disconnect(); worklet.disconnect();
  stream.getTracks().forEach((t) => t.stop());
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "hangup" }));
    ws.close();
  } else if (ws.readyState === WebSocket.CONNECTING) {
    ws.onopen = () => ws.close();
  }
}

function duration() {
  const s = Math.floor((Date.now() - startedAt) / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

async function hangup(status = "completed", { byAgent = false } = {}) {
  clearInterval(tickTimer);
  // A live call is the server's to close and save; it only needs to hear we hung up.
  const serverOwns = live?.opened || byAgent;
  stopLive();
  const id = serverOwns ? null : call?.id;
  if (!call) return;
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
  $("call-now").addEventListener("click", callNow);
  $("accept").addEventListener("click", answer);
  $("decline").addEventListener("click", () => endRinging("declined"));
  $("hangup").addEventListener("click", () => hangup());
  $("mute").addEventListener("click", (e) => {
    const on = e.currentTarget.classList.toggle("on");
    live?.worklet.port.postMessage({ muted: on });
  });
  $("speaker").addEventListener("click", (e) => {
    const on = e.currentTarget.classList.toggle("on");
    if (live) live.line.volume.gain.value = on ? 1.8 : 1.0;
  });
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState === "visible" && wakeLock?.released) {
      try { wakeLock = await navigator.wakeLock.request("screen"); } catch {}
    }
  });
  show("lock");
}
