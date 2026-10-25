"""Screenshots of the site at a few moments in the story, for checking the design.

    python3 tools/shoot.py OUTDIR

Serves site/ on a local port, opens it in headless Chromium, plays the story at
high speed, and saves screenshots on desktop and phone sizes.
"""

import functools
import http.server
import os
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parent.parent / "site"


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    httpd = serve()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    exe = os.environ.get("CHROME", "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome")
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe if Path(exe).exists() else None)
        for name, viewport in (("desktop", {"width": 1440, "height": 1000}), ("phone", {"width": 390, "height": 844})):
            page = browser.new_page(viewport=viewport, device_scale_factor=2 if name == "phone" else 1)
            page.on("console", lambda m: m.type == "error" and errors.append(m.text))
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.wait_for_timeout(1200)
            page.screenshot(path=str(out / f"{name}-0-load.png"))
            page.screenshot(path=str(out / f"{name}-0-full.png"), full_page=True)
            # play fast: speed button, then play
            page.evaluate("document.querySelector('#speed').click()")
            page.evaluate("document.querySelector('#play').click()")
            page.wait_for_timeout(2600)
            page.screenshot(path=str(out / f"{name}-1-asks.png"))
            # wait for Theo's decision, then choose yes
            page.wait_for_selector(".choices.live button", timeout=60000)
            page.screenshot(path=str(out / f"{name}-2-theo.png"))
            page.click(".choices.live button >> nth=0")
            for k in range(3, 8):
                try:
                    page.wait_for_selector(".choices.live button", timeout=90000)
                except Exception:
                    break
                page.wait_for_timeout(300)
                page.screenshot(path=str(out / f"{name}-{k}-decision.png"))
                page.click(".choices.live button >> nth=0")
            page.wait_for_function("document.querySelector('#play').textContent === 'Play again'", timeout=180000)
            page.screenshot(path=str(out / f"{name}-9-end.png"))
            page.screenshot(path=str(out / f"{name}-9-end-full.png"), full_page=True)
            page.close()
        browser.close()
    httpd.shutdown()
    print("errors:", errors or "none")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "shots")
