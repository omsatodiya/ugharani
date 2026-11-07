"""Screenshots of the real pages for the launch video (video/public/screens), at 2x.

    uv run python scripts/fake_voice_server.py      # (DEMO_SEED: sample dues and calls)
    uv run python scripts/video_screens.py
"""

import asyncio
import base64
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_check import CHROME, Page  # noqa: E402

SERVER = "http://localhost:8000"
OUT = Path("video/public/screens")
SHOTS = [  # name, path, width, height, js to run first
    ("landing", "/", 1440, 900, None),
    ("desk_today", "/app/#today", 1440, 900, None),
    ("desk_calls", "/app/#calls", 1440, 900,
     "document.getElementById('hours-note').hidden = true; document.querySelectorAll('#call-log details')[1]?.setAttribute('open', '')"),
    ("desk_settings", "/app/#settings", 1440, 900, None),
    ("desk_today_phone", "/app/#today", 400, 860, None),
]


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp()
    chrome = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=9338", f"--user-data-dir={profile}",
                               "--hide-scrollbars", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = httpx.get("http://127.0.0.1:9338/json").json()
                break
            except httpx.HTTPError:
                await asyncio.sleep(0.2)
        target = next(t for t in tabs if t["type"] == "page")
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=2**27) as ws:
            page = Page(ws)
            await page.call("Page.enable")
            for name, path, w, h, js in SHOTS:
                await page.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2, mobile=w < 500)
                await page.call("Page.navigate", url=SERVER + path)
                await asyncio.sleep(4)  # fonts, data, and the entrance animations
                if js:
                    await page.js(js)
                    await asyncio.sleep(0.8)
                shot = await page.call("Page.captureScreenshot", format="png")
                (OUT / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))
                print("saved", name)
    finally:
        chrome.terminate()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
