#!/usr/bin/env python3
"""Copy garmin_grab.py into index.html so the page's "Copy script" and
"Download grabber" buttons always ship the current version.

Usage (from the repo root):
    python tools/embed_grabber.py          # update index.html in place
    python tools/embed_grabber.py --check  # exit 1 if index.html is out of date
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "index.html"
SCRIPT = ROOT / "garmin_grab.py"
BLOCK = re.compile(r'(<script type="text/plain" id="grabber-src">)(.*?)(</script>)', re.S)


def main():
    src = SCRIPT.read_text(encoding="utf-8")
    if "</script" in src.lower():
        sys.exit("garmin_grab.py contains '</script', which would break the page.")
    html = PAGE.read_text(encoding="utf-8")
    m = BLOCK.search(html)
    if not m:
        sys.exit("Could not find the grabber-src block in index.html.")
    if m.group(2) == src:
        print("index.html is up to date.")
        return
    if "--check" in sys.argv:
        sys.exit("index.html embeds an outdated garmin_grab.py. Run: python tools/embed_grabber.py")
    PAGE.write_text(html[:m.start(2)] + src + html[m.end(2):], encoding="utf-8")
    print("index.html updated.")


if __name__ == "__main__":
    main()
