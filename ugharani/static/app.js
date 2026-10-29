// Ugharani PWA: record -> /entries/voice -> answer missing fields -> confirm -> /entries.
// Audio is recorded as 16 kHz mono WAV in the browser, a format Prisma takes on every platform.

const $ = (id) => document.getElementById(id);
const rupees = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const STATUS = { overdue: "મુદત વીતી", today: "આજે", upcoming: "જલદી" };
const FIELDS = { buyer: "કોણ", amount: "રકમ", due_date: "મુદત" };
const MAX_SECONDS = 30;

let draft = null;          // unconfirmed entry from the last recording
let reminder = null;       // reminder shown in the dialog
let recorder = null;       // active recording
let audioUnlocked = false;

// ---------- small helpers ----------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null) node.append(c);
  return node;
}

function formatDate(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString("gu-IN", { day: "numeric", month: "short" });
}

let toastTimer;
function toast(message) {
  const t = $("toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 3500);
}

function demoToday() {
  return $("today").value || null;
}

function withToday(path) {
  const today = demoToday();
  return today ? `${path}?today=${today}` : path;
}

async function api(path, options) {
  const resp = await fetch(path, options);
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body);
    throw new Error(detail || `HTTP ${resp.status}`);
  }
  return body;
}

// ---------- playback ----------

// iOS only lets audio play after a tap; play a silent clip on the first tap to unlock it.
const SILENT_WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=";
function unlockAudio() {
  if (audioUnlocked) return;
  audioUnlocked = true;
  const p = $("player");
  p.src = SILENT_WAV;
  p.play().catch(() => {});
}

function play(url, button) {
  if (!url) return;
  const p = $("player");
  p.src = url;
  p.play().catch(() => button && (button.hidden = false));  // autoplay blocked: leave the ▶ button
}

function bindPlay(button, url) {
  button.hidden = !url;
  button.onclick = () => play(url);
}

// ---------- recording (WAV, 16 kHz mono) ----------

async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const source = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  proc.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  source.connect(proc);
  proc.connect(ctx.destination);
  const started = Date.now();
  const timer = setInterval(() => {
    const secs = Math.floor((Date.now() - started) / 1000);
    $("mic-label").textContent = `રોકો ${secs}s`;
    if (secs >= MAX_SECONDS) stopRecording();
  }, 250);
  return { stream, ctx, source, proc, chunks, started, timer };
}

function finishRecording(r) {
  clearInterval(r.timer);
  r.proc.disconnect();
  r.source.disconnect();
  r.stream.getTracks().forEach((t) => t.stop());
  const rate = r.ctx.sampleRate;
  r.ctx.close();
  const seconds = (Date.now() - r.started) / 1000;
  return { wav: encodeWav(downsample(r.chunks, rate, 16000), 16000), seconds };
}

function downsample(chunks, from, to) {
  const input = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
  let offset = 0;
  for (const c of chunks) { input.set(c, offset); offset += c.length; }
  const ratio = from / to;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio), end = Math.min(Math.floor((i + 1) * ratio), input.length);
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = sum / Math.max(1, end - start);  // average = simple low-pass before decimating
  }
  return out;
}

function encodeWav(samples, rate) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => [...s].forEach((ch, i) => v.setUint8(o + i, ch.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Blob([buf], { type: "audio/wav" });
}

function setMic(state) {
  const mic = $("mic");
  mic.classList.toggle("recording", state === "recording");
  mic.classList.toggle("busy", state === "busy");
  mic.disabled = state === "busy";
  $("mic-label").textContent = { idle: draft?.missing ? "જવાબ" : "બોલો", recording: "રોકો", busy: "…" }[state];
  mic.setAttribute("aria-label", { idle: "Tap to speak", recording: "Tap to stop", busy: "Working" }[state]);
}

async function onMic() {
  unlockAudio();
  if (recorder) return stopRecording();
  try {
    recorder = await startRecording();
    setMic("recording");
  } catch (e) {
    recorder = null;
    toast("માઇકની પરવાનગી આપો · Allow microphone access");
  }
}

async function stopRecording() {
  if (!recorder) return;
  const { wav, seconds } = finishRecording(recorder);
  recorder = null;
  if (seconds < 0.8) {
    setMic("idle");
    return toast("થોડું લાંબું બોલો · Hold on a little longer");
  }
  setMic("busy");
  try {
    await sendRecording(wav);
  } catch (e) {
    toast(`ભૂલ · ${e.message}`);
  } finally {
    setMic("idle");
  }
}

// ---------- the entry conversation ----------

async function sendRecording(wav) {
  const form = new FormData();
  form.append("audio", wav, "entry.wav");
  if (draft?.missing) form.append("draft", JSON.stringify(draft.fields));
  const body = await api("/entries/voice", { method: "POST", body: form });
  draft = { fields: body.draft, missing: body.missing.length ? body.missing : null };
  showConvo(body);
  play(body.audio, $("play-reply"));
}

function showConvo(body) {
  $("convo").hidden = false;
  $("heard").textContent = `તમે બોલ્યા: “${body.transcript}”`;
  const d = body.draft;
  const values = {
    buyer: d.buyer,
    amount: d.amount != null ? rupees.format(d.amount) : null,
    due_date: d.due_date ? formatDate(d.due_date) : null,
  };
  const rows = [el("dt", {}, "પ્રકાર"), el("dd", {}, d.kind === "payment" ? "જમા (payment)" : "ઉધાર માલ (credit)")];
  for (const [key, label] of Object.entries(FIELDS)) {
    if (key === "due_date" && d.kind === "payment") continue;
    rows.push(el("dt", {}, label), values[key] ? el("dd", {}, values[key]) : el("dd", { class: "missing" }, "— બાકી"));
  }
  $("draft").replaceChildren(...rows);
  $("reply-say").textContent = body.say;
  bindPlay($("play-reply"), body.audio);
  $("answer-hint").hidden = !body.missing.length;
  $("confirm").hidden = !!body.missing.length;
  $("convo").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function clearConvo() {
  draft = null;
  $("convo").hidden = true;
  setMic("idle");
}

async function onSave() {
  if (!draft || draft.missing) return;
  $("save").disabled = true;
  try {
    await api("/entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft.fields),
    });
    clearConvo();
    toast("સાચવ્યું ✓ · Saved");
    await refresh();
  } catch (e) {
    toast(`ભૂલ · ${e.message}`);
  } finally {
    $("save").disabled = false;
  }
}

// ---------- summary, balances, reminders ----------

async function refresh() {
  const [summary, balances] = await Promise.all([api(withToday("/summary")), api("/balances")]);
  $("summary-say").textContent = summary.say;
  bindPlay($("play-summary"), summary.audio);
  $("due-items").replaceChildren(
    ...summary.items.map((i) =>
      el("li", {},
        el("div", { class: "who" },
          el("div", { class: "name" }, i.buyer),
          el("div", { class: "meta" }, el("span", { class: `chip ${i.status}` }, STATUS[i.status]), formatDate(i.due_date))),
        el("span", { class: "amt" }, rupees.format(i.amount)),
        el("button", { class: "btn small", onclick: () => openReminder(i.buyer) }, "યાદ અપાવો"),
      ),
    ),
  );
  const open = balances.filter((b) => b.balance > 0);
  $("balances").replaceChildren(
    ...(open.length
      ? open.map((b) =>
          el("li", {},
            el("div", { class: "who" },
              el("div", { class: "name" }, b.buyer),
              b.earliest_due ? el("div", { class: "meta" }, `પહેલી મુદત ${formatDate(b.earliest_due)}`) : null),
            el("span", { class: "amt" }, rupees.format(b.balance)),
          ),
        )
      : [el("li", {}, el("span", { class: "empty" }, "હજી કોઈ ઉધાર નથી · No open credit yet"))]),
  );
}

async function openReminder(buyer) {
  unlockAudio();
  try {
    reminder = await api(withToday(`/reminders/${encodeURIComponent(buyer)}`));
  } catch (e) {
    return toast(`ભૂલ · ${e.message}`);
  }
  $("reminder-say").textContent = reminder.say;
  $("play-reminder").hidden = !reminder.audio;
  $("reminder").showModal();
  play(reminder.audio);
}

async function shareReminder() {
  if (!reminder) return;
  // Send from the trader's own WhatsApp: share sheet with the voice clip, else a text link.
  try {
    if (reminder.audio && navigator.canShare) {
      const blob = await (await fetch(reminder.audio)).blob();
      const file = new File([blob], "ugharani-yaadi.wav", { type: "audio/wav" });
      if (navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], text: reminder.say });
        return;
      }
    }
  } catch (e) {
    if (e.name === "AbortError") return;  // trader closed the share sheet
  }
  window.open(`https://wa.me/?text=${encodeURIComponent(reminder.say)}`, "_blank", "noopener");
}

// ---------- start ----------

function init() {
  try {
    const saved = localStorage.getItem("ugharani-today");
    if (saved) $("today").value = saved;
  } catch {}
  $("today").addEventListener("change", () => {
    try { localStorage.setItem("ugharani-today", $("today").value); } catch {}
    refresh().catch((e) => toast(`ભૂલ · ${e.message}`));
  });
  $("mic").addEventListener("click", onMic);
  $("save").addEventListener("click", onSave);
  $("cancel").addEventListener("click", clearConvo);
  $("play-reminder").addEventListener("click", () => play(reminder?.audio));
  $("share-reminder").addEventListener("click", shareReminder);
  $("close-reminder").addEventListener("click", () => $("reminder").close());
  if (!navigator.mediaDevices?.getUserMedia) {
    $("mic").disabled = true;
    toast("આ બ્રાઉઝરમાં માઇક નથી ચાલતું · This browser can't record");
  }
  refresh().catch((e) => {
    $("summary-say").textContent = "સર્વર સાથે જોડાણ નથી · Can't reach the server";
    toast(e.message);
  });
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
}

init();
