"""Drive the real phone page in headless Chrome, end to end, with Chrome's fake microphone.

    uv run python scripts/fake_voice_server.py        # free: Gnani faked (or a real server: costs credits)
    uv run python scripts/browser_check.py [customer]

Arms the phone, taps "call this phone", answers, lets the call run, and checks what the page did:
microphone frames flowing, the agent's audio played, any duck / clear (interruptions), and the
call ending and being saved. Exits non-zero if something is wrong.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import websockets

sys.stdout.reconfigure(encoding="utf-8")

SERVER = os.getenv("SERVER", "http://localhost:8000")
PORT = 9333
CHROME = next((p for p in [os.getenv("CHROME", ""),
                           r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                           shutil.which("google-chrome") or "", shutil.which("chromium") or ""]
               if p and Path(p).exists()), None)

# Runs before the page's own scripts: records what the call websocket sends and receives.
SPY = """
window.__spy = {sent: 0, events: [], audio: 0, played: 0};
const NativeWS = window.WebSocket;
window.WebSocket = function (url, protocols) {
  const ws = new NativeWS(url, protocols);
  const send = ws.send.bind(ws);
  ws.send = (data) => { if (typeof data !== "string") __spy.sent++; return send(data); };
  ws.addEventListener("message", (e) => {
    if (typeof e.data === "string") __spy.events.push(JSON.parse(e.data));
    else __spy.audio += e.data.byteLength;
  });
  return ws;
};
window.WebSocket.prototype = NativeWS.prototype;
Object.assign(window.WebSocket, {CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3});
const start = AudioBufferSourceNode.prototype.start;
AudioBufferSourceNode.prototype.start = function (...a) {
  if (this.buffer && this.buffer.sampleRate === 16000) __spy.played += this.buffer.duration;
  return start.apply(this, a);
};
"""


class Page:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, method, **params):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    async def js(self, expr):
        r = await self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    async def wait_for(self, expr, timeout=20.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if await self.js(expr):
                return True
            await asyncio.sleep(0.25)
        raise TimeoutError(expr)


async def main(customer: str) -> int:
    if not CHROME:
        print("no Chrome or Edge found; set CHROME=path")
        return 2
    profile = tempfile.mkdtemp(prefix="ugharani-chrome-")
    chrome = subprocess.Popen([
        CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",  # mic: a test tone
        "--autoplay-policy=no-user-gesture-required", "--no-first-run", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    problems = []
    try:
        async with httpx.AsyncClient() as http:
            for _ in range(50):
                try:
                    tabs = (await http.get(f"http://127.0.0.1:{PORT}/json")).json()
                    break
                except httpx.HTTPError:
                    await asyncio.sleep(0.2)
            target = next(t for t in tabs if t["type"] == "page")
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=2**24) as ws:
            page = Page(ws)
            await page.call("Page.enable")
            await page.call("Page.addScriptToEvaluateOnNewDocument", source=SPY)
            await page.call("Page.navigate", url=f"{SERVER}/phone.html?c={quote(customer)}")
            await page.wait_for("document.readyState === 'complete' && !!document.getElementById('arm')")

            await page.js("document.getElementById('arm').click()")
            await page.wait_for("!document.getElementById('call-now').hidden")
            print("phone armed; tapping 'call this phone'")
            await page.js("document.getElementById('call-now').click()")
            await page.wait_for("!document.getElementById('ringing').hidden", timeout=10)
            print("ringing; answering")
            await page.js("document.getElementById('accept').click()")
            t0 = time.monotonic()
            await page.wait_for("!document.getElementById('ended').hidden || "
                                "!document.getElementById('lock').hidden", timeout=150)
            spy = await page.js("window.__spy")
            print(f"call ended after {time.monotonic() - t0:.0f}s")
    finally:
        chrome.terminate()
        shutil.rmtree(profile, ignore_errors=True)

    kinds = [e["type"] for e in spy["events"]]
    for e in spy["events"]:
        if e["type"] == "line":
            print(f"  {e['who']:8s} {e['text']}")
        elif e["type"] != "line":
            print(f"  [{e['type']}]")
    print(f"mic frames sent: {spy['sent']}, agent audio received: {spy['audio'] / 32000:.1f}s, "
          f"played: {spy['played']:.1f}s")
    if spy["sent"] < 100:
        problems.append("the microphone barely sent anything")
    if spy["audio"] == 0 or spy["played"] == 0:
        problems.append("no agent audio was played")
    if "end" not in kinds:
        problems.append("the agent never hung up")
    async with httpx.AsyncClient(base_url=SERVER) as http:
        calls = (await http.get("/calls")).json()
    saved = calls[0]
    print(f"saved call {saved['id']}: {saved['status']}, {len(saved['transcript'])} turns")
    if saved["status"] != "completed" or not saved["transcript"]:
        problems.append("the call was not saved as completed")
    if os.getenv("EXPECT"):
        for kind in os.getenv("EXPECT").split(","):
            if kind not in kinds:
                problems.append(f"expected a {kind} event")
    print("OK" if not problems else "PROBLEMS: " + "; ".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "રમેશભાઈ")))
