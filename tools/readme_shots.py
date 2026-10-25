"""The README's pictures, taken from the real site so the two always look the same.

    python3 tools/readme_shots.py                 # all of them, into docs/readme/
    python3 tools/readme_shots.py hero buttons    # just these

Serves site/ on a local port, opens it in headless Chromium, and saves:

  hero.png      the night-sky header and the headline
  night.gif     the first part of the night playing (needs ffmpeg)
  rogue.png     the rogue agent story once every attempt has been stopped
  btn-*.png     the site's buttons on their own, plus one for the demo video, so the README can link each one

Needs Playwright for Python (pip install playwright, then playwright install chromium).
"""

import functools
import http.server
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
WIDTH = 1280
GIF_SECONDS = 22      # of the night at 2x speed: who knows, then answers quoted from notes
GIF_WIDTH = 880       # about the width GitHub shows a README at
GIF_FPS = 5           # enough to see messages fly, small enough for a README


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve():
    handler = functools.partial(Quiet, directory=str(SITE))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


ERRORS = []  # anything the site logged as an error while it was being captured


def watch(page):
    page.on("pageerror", lambda e: ERRORS.append(str(e)))
    page.on("console", lambda m: m.type == "error" and ERRORS.append(m.text))
    return page


def click(page, selector):
    page.evaluate(f"document.querySelector({selector!r}).click()")


def hero(browser, url, out):
    page = watch(browser.new_page(viewport={"width": WIDTH, "height": 900}, device_scale_factor=2))
    page.goto(url)
    page.wait_for_timeout(2400)  # the headline types itself in
    # Just the header and the headline: the README sets the rest as text, with buttons that work.
    page.add_style_tag(content=".hook-row { visibility: hidden; }")
    bottom = page.evaluate("document.querySelector('.hook h1').getBoundingClientRect().bottom")
    page.screenshot(path=str(out / "hero.png"), clip={"x": 0, "y": 0, "width": WIDTH, "height": bottom + 44})
    page.close()


def rogue(browser, url, out):
    page = watch(browser.new_page(viewport={"width": WIDTH, "height": 900}, device_scale_factor=2))
    page.goto(url)
    page.wait_for_timeout(800)
    click(page, "[data-story=rogue]")
    click(page, "#speed")
    click(page, "#play")
    page.wait_for_function("document.querySelector('#play').textContent === 'Play again'", timeout=180000)
    page.wait_for_timeout(600)
    page.locator("#player .player-grid").screenshot(path=str(out / "rogue.png"))
    page.close()


BUTTONS = (  # file, label, the lamp-colored main button?
    ("btn-play.png", "Play the night", True),
    ("btn-video.png", "Watch the demo video", False),
    ("btn-rogue.png", "Watch an agent go rogue", False),
    ("btn-discord.png", "Try it live in Discord", False),
)


def buttons(browser, url, out):
    """The site's buttons in its own font and colors. The quiet ones get a solid night fill (on the site they
    sit on the night sky), so they still read on GitHub's light theme."""
    page = watch(browser.new_page(device_scale_factor=2))
    # A plain file from the same server, so the page below can load the site's font without running its script.
    page.goto(url.rsplit("/", 1)[0] + "/fonts/OFL-bricolage-grotesque.txt")
    links = "".join(f'<a class="btn{" lamp" if lamp else ""}" id="b{i}">{label}</a>'
                    for i, (_, label, lamp) in enumerate(BUTTONS))
    page.set_content(f"""<!doctype html><style>
      @font-face {{ font-family: "Bricolage Grotesque Variable"; font-weight: 200 800; font-stretch: 75% 100%;
                    src: url(/fonts/bricolage-grotesque.woff2) format("woff2"); }}
      body {{ margin: 0; padding: 8px; background: transparent; font-family: "Bricolage Grotesque Variable", sans-serif; }}
      .btn {{ display: inline-block; margin: 4px; font-size: 17px; font-weight: 650; line-height: 1.25;
              border-radius: 999px; padding: 12px 22px; border: 1px solid #3A4386; background: #0E1330; color: #EEF0FF; }}
      .btn.lamp {{ background: #FFC46B; border-color: #FFC46B; color: #2B1C04; }}
    </style>{links}""")
    page.evaluate("document.fonts.ready.then(() => document.fonts.size)")
    page.wait_for_timeout(300)
    for i, (name, _, _) in enumerate(BUTTONS):
        page.locator(f"#b{i}").screenshot(path=str(out / name), omit_background=True)
    page.close()


def night(browser, url, out):
    if not shutil.which("ffmpeg"):
        print("ffmpeg isn't installed, so night.gif was skipped.", file=sys.stderr)
        return
    with tempfile.TemporaryDirectory() as tmp:
        height = 800  # room for the player to grow when a caption wraps
        context = browser.new_context(viewport={"width": WIDTH, "height": height},
                                      record_video_dir=tmp, record_video_size={"width": WIDTH, "height": height})
        page = watch(context.new_page())
        page.goto(url)
        page.add_style_tag(content="#board { visibility: hidden; }")  # keep the next section out of the frame
        page.wait_for_timeout(800)
        box = page.locator("#player .player-grid").bounding_box()
        page.evaluate(f"window.scrollTo(0, {box['y'] - 16})")
        page.wait_for_timeout(400)
        click(page, "#speed")
        click(page, "#play")
        start = page.evaluate("performance.now()")
        while page.evaluate("performance.now()") - start < GIF_SECONDS * 1000:
            if page.locator(".choices.live button").count():
                page.wait_for_timeout(900)  # long enough to read the question
                page.click(".choices.live button >> nth=0")
            page.wait_for_timeout(200)
        video = page.video.path()
        context.close()
        crop = f"crop={int(box['width'])}:{min(int(box['height']) + 60, height - 16)}:{int(box['x'])}:16"
        graph = (f"[0:v]trim=start=1.2,setpts=PTS-STARTPTS,{crop},fps={GIF_FPS},scale={GIF_WIDTH}:-1:flags=lanczos,split[a][b];"
                 "[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-filter_complex", graph,
                        "-loop", "0", str(out / "night.gif")], check=True)


SHOTS = {"hero": hero, "buttons": buttons, "night": night, "rogue": rogue}


def main(names, out=ROOT / "docs" / "readme"):
    unknown = [n for n in names if n not in SHOTS]
    if unknown:
        raise SystemExit(f"Unknown: {', '.join(unknown)}. Pick from: {', '.join(SHOTS)}.")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    httpd = serve()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in names or SHOTS:
            SHOTS[name](browser, url, out)
        browser.close()
    httpd.shutdown()
    for f in sorted(out.iterdir()):
        print(f"{f}  {f.stat().st_size // 1024} KB")
    print("errors:", ERRORS or "none")


if __name__ == "__main__":
    main(sys.argv[1:])
