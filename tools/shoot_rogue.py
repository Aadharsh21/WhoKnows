"""Screenshots of the rogue agent story, for checking the design.

    python3 tools/shoot_rogue.py OUTDIR
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from shoot import serve

EXE = "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome"


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    httpd = serve()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=EXE if Path(EXE).exists() else None)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_timeout(1000)
        page.click("#go-rogue")
        for k in range(14):
            page.wait_for_timeout(2200)
            page.screenshot(path=str(out / f"rogue-{k:02d}.png"))
            if page.evaluate("document.querySelector('#play').textContent") == "Play again":
                break
        page.close()
        browser.close()
    httpd.shutdown()
    print("errors:", errors or "none")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "shots")
