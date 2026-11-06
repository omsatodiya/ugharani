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

// Days from the real today, matching the spoken read-back ("30 દિવસની મુદત").
function daysFromToday(iso) {
  const now = new Date();
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((Date.parse(iso + "T00:00:00Z") - today) / 86400000);
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
  $("mic-label").textContent = { idle: draft?.missing ? "જવાબ" : draft ? "સુધારો" : "બોલો", recording: "રોકો", busy: "…" }[state];
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
  // A follow-up recording either answers the question or fixes a misheard field ("ના, સાઠ દિવસ").
  if (draft) form.append("draft", JSON.stringify(draft.fields));
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
    due_date: d.due_date ? `${daysFromToday(d.due_date)} દિવસ · ${formatDate(d.due_date)}` : null,
  };
  const rows = [el("dt", {}, "પ્રકાર"), el("dd", {}, d.kind === "payment" ? "જમા (payment)" : "ઉધાર માલ (credit)")];
  for (const [key, label] of Object.entries(FIELDS)) {
    if (key === "due_date" && d.kind === "payment") continue;
    rows.push(el("dt", {}, label), values[key] ? el("dd", {}, values[key]) : el("dd", { class: "missing" }, "— બાકી"));
  }
  $("draft").replaceChildren(...rows);
  $("reply-say").textContent = body.say;
  bindPlay($("play-reply"), body.audio);
  $("answer-hint").textContent = body.missing.length
    ? "જવાબ બોલવા માટે માઇક દબાવો · Tap the mic to answer"
    : "કંઈ ખોટું હોય તો માઇક દબાવી ફક્ત તે જ બોલો, જેમ કે “ના, સાઠ દિવસ” · Wrong? Tap the mic and say just the fix";
  $("answer-hint").hidden = false;
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

// ---------- calls: who's due, what came of each call, what the owner must do ----------

const OUTCOME = {
  promised: ["વાયદો", "good"], paid: ["ચૂકવ્યું કહે છે", "good"], dispute: ["વાંધો", "bad"],
  callback: ["ફરી ફોન", "warn"], handover: ["તમે ફોન કરો", "bad"], refused: ["ના પાડી", "bad"],
  unclear: ["અધૂરું", "quiet"],
};
const CALL_STATUS = {
  ringing: ["રિંગ વાગે છે", "warn"], in_progress: ["વાત ચાલુ", "warn"], missed: ["ઉપાડ્યો નહીં", "quiet"],
  declined: ["કાપ્યો", "quiet"], failed: ["ન લાગ્યો", "quiet"], completed: ["પૂરો", "quiet"],
};
const REASON = { overdue: "મુદત વીતી", due_today: "આજે મુદત", retry: "ફરી પ્રયત્ન", promise_missed: "વાયદો ચૂક્યા" };
let callsTimer;
let hours = null;

// The owner's demo key (?k=... once): calls made with it don't count against the public budget.
const ownerKey = (() => {
  const k = new URLSearchParams(location.search).get("k");
  try {
    if (k) localStorage.setItem("ugharani-key", k);
    return k || localStorage.getItem("ugharani-key");
  } catch { return k; }
})();
const withKey = (path) => (ownerKey ? `${path}${path.includes("?") ? "&" : "?"}k=${encodeURIComponent(ownerKey)}` : path);

function when(iso) {
  return new Date(iso).toLocaleString("gu-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function chip([label, kind]) {
  return el("span", { class: `chip ${kind}` }, label);
}

function phoneLink(name) {
  // The demo's stand-in for the customer's phone: open it (on another device) to take the call.
  return el("a", { class: "btn small", href: withKey(`/phone.html?c=${encodeURIComponent(name)}`), target: "_blank",
                   "aria-label": "Customer's phone" }, "📱");
}

async function callNow(name, button) {
  button.disabled = true;
  try {
    await api(withKey("/calls"), { method: "POST", headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ customer: name }) });
    toast(`${name}ને ફોન લાગી રહ્યો છે · Calling (open their phone 📱)`);
  } catch (e) {
    toast(`ભૂલ · ${e.message}`);
  }
  refreshCalls();
}

async function runCalls() {
  const params = new URLSearchParams();
  if (demoToday()) params.set("today", demoToday());
  if (!hours?.open) params.set("anytime", "true"); // outside call hours: a demo run
  if (ownerKey) params.set("k", ownerKey);
  try {
    const rung = await api(`/calls/run?${params}`, { method: "POST" });
    toast(rung.length ? `${rung.length} ફોન લાગી રહ્યા છે · Calling ${rung.length}` : "આજે કોઈને ફોન કરવાનો નથી · Nobody to call");
  } catch (e) {
    toast(`ભૂલ · ${e.message}`);
  }
  refreshCalls();
}

function callItem(c) {
  const live = c.status === "ringing" || c.status === "in_progress";
  const tag = c.outcome ? OUTCOME[c.outcome] : CALL_STATUS[c.status];
  const promise = c.promised_date
    ? [c.promised_amount && rupees.format(c.promised_amount), formatDate(c.promised_date), c.payment_mode]
        .filter(Boolean).join(" · ")
    : null;
  const turns = (c.transcript || []).map((t) =>
    el("p", { class: "turn" }, el("b", {}, t.who === "agent" ? "કાવ્યા: " : `${c.customer}: `), t.text));
  const writing = c.status === "completed" && !c.summary && turns.length;
  return el("li", {},
    el("div", { class: "row" },
      el("div", { class: "who" },
        el("div", { class: "name" }, c.customer),
        el("div", { class: "meta" }, chip(tag), when(c.created_at), c.trigger === "auto" ? " · ઓટો" : "")),
      el("span", { class: "amt" }, rupees.format(c.amount_due)),
      live ? phoneLink(c.customer) : null),
    c.summary ? el("p", { class: "note" }, c.summary) : null,
    writing ? el("p", { class: "note why" }, "નોંધ લખાય છે… · Writing the notes…") : null,
    promise ? el("p", { class: "promise" }, `વાયદો: ${promise}`) : null,
    c.owner_action ? el("p", { class: "action" }, `➜ ${c.owner_action}`) : null,
    turns.length ? el("details", {}, el("summary", {}, `વાતચીત · Conversation (${turns.length})`), ...turns) : null,
  );
}

function tasksFrom(calls) {
  // The latest call per customer: what is left for the owner to do.
  const seen = new Set(), tasks = [];
  for (const c of calls) {
    if (seen.has(c.customer)) continue;
    seen.add(c.customer);
    const why = c.owner_action
      || (c.outcome === "handover" ? "તમે ફોન કરો · Call them" : null)
      || (c.outcome === "dispute" ? "વાંધો ઉકેલો · Settle the dispute" : null);
    if (!why && !c.flags?.length) continue;
    tasks.push(el("li", {},
      el("div", { class: "who" },
        el("div", { class: "name" }, c.customer),
        el("div", {}, why || "કાવ્યાએ એક વાત ટાળી, તમે ફોન કરો · Kavya held back, call them"),
        c.flags?.length ? el("div", { class: "why" }, `ચેકરે ${c.flags.length} વાક્ય રોક્યું · Checker stopped ${c.flags.length}`) : null),
      el("span", { class: "amt" }, rupees.format(c.amount_due))));
  }
  return tasks;
}

async function refreshCalls() {
  clearTimeout(callsTimer);
  let calls = [];
  try {
    const [queue, log, h] = await Promise.all([api(withToday("/calls/queue")), api("/calls"), api(withKey("/calls/hours"))]);
    calls = log;
    hours = h;
    const busy = new Set(log.filter((c) => c.status === "ringing" || c.status === "in_progress").map((c) => c.customer));
    $("demo-left").hidden = h.demo_left == null;
    $("demo-left").textContent = `આજે ડેમો ફોન બાકી: ${h.demo_left} · Demo calls left today: ${h.demo_left}`;
    $("hours-note").hidden = h.open;
    $("hours-note").textContent = `ઓટો ફોન ${h.hours.replace(",", " અને ")} વચ્ચે જ જાય${h.sunday ? "" : ", રવિવારે નહીં"}; અત્યારે "બધાને ફોન" ડેમો તરીકે જશે. · Outside call hours: "Call all" runs as a demo.`;
    $("run-calls").disabled = !queue.length;
    $("queue").replaceChildren(...(queue.length
      ? queue.map((q) => el("li", {},
          el("div", { class: "who" },
            el("div", { class: "name" }, q.customer),
            el("div", { class: "meta" }, el("span", { class: "chip overdue" }, REASON[q.reason] || q.reason), formatDate(q.due_date))),
          el("span", { class: "amt" }, rupees.format(q.amount)),
          busy.has(q.customer) ? phoneLink(q.customer)
            : el("button", { class: "btn small", onclick: (e) => callNow(q.customer, e.currentTarget) }, "ફોન કરો")))
      : [el("li", {}, el("span", { class: "empty" }, "આજે કોઈને ફોન કરવાનો નથી · Nobody to call today"))]));
    $("call-log").replaceChildren(...(log.length
      ? log.slice(0, 20).map(callItem)
      : [el("li", {}, el("span", { class: "empty" }, "હજી કોઈ ફોન નથી કર્યો · No calls yet"))]));
    const tasks = tasksFrom(log);
    $("todo").hidden = !tasks.length;
    $("tasks").replaceChildren(...tasks);
  } catch (e) {
    toast(`ભૂલ · ${e.message}`);
  }
  // While a call is on, or its notes are being written, keep the log fresh.
  const active = calls.some((c) => c.status === "ringing" || c.status === "in_progress" ||
                                   (c.status === "completed" && !c.summary && c.transcript?.length));
  callsTimer = setTimeout(refreshCalls, active ? 3000 : 20000);
}

// ---------- the owner's rules for Kavya ----------

const RULE_KEYS = ["promise_days", "split_days", "call_hours", "holidays", "call_on_sunday", "auto_calls", "tone"];

function rulesSay(r) {
  return `કાવ્યા આખા પેમેન્ટ માટે ${r.promise_days} દિવસ સુધીનો વાયદો, અને ભાગમાં છેલ્લો ભાગ ${r.split_days} દિવસમાં હોય તો હા પાડે. ` +
    `ડિસ્કાઉન્ટ, વ્યાજ કે લાંબી મુદત: "${r.owner_name} તમને ફોન કરશે." · She agrees to these on her own; anything more comes to you.`;
}

async function loadRules() {
  const r = await api("/settings");
  const form = $("rules-form");
  for (const k of RULE_KEYS) {
    const input = form.elements[k];
    if (input.type === "checkbox") input.checked = !!r[k];
    else input.value = r[k];
  }
  $("rules-say").textContent = rulesSay(r);
}

async function saveRules(e) {
  e.preventDefault();
  const form = $("rules-form");
  const changes = {};
  for (const k of RULE_KEYS) {
    const input = form.elements[k];
    changes[k] = input.type === "checkbox" ? input.checked : input.type === "number" ? Number(input.value) : input.value;
  }
  try {
    const r = await api("/settings", { method: "PUT", headers: { "Content-Type": "application/json" },
                                       body: JSON.stringify(changes) });
    $("rules-say").textContent = rulesSay(r);
    toast("નિયમો સચવાયા · Rules saved");
    refreshCalls();
  } catch (err) {
    toast(`ભૂલ · ${err.message}`);
  }
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
    refreshCalls();
  });
  $("run-calls").addEventListener("click", runCalls);
  $("rules-form").addEventListener("submit", saveRules);
  loadRules().catch(() => {});
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
  refreshCalls();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
}

init();
