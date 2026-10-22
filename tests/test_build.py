"""tools/build.py page checks (standard library only): python -m unittest discover -s tests

The built index.html must be self-contained: no third-party scripts, stylesheets, fonts or
CSS imports, and no local file left un-inlined, so the release file works opened from disk.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_build():
    spec = importlib.util.spec_from_file_location("build", ROOT / "tools" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="vendor/tokens.css">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<a href="https://github.com/DavideBisio/garmin-run-progress">Source</a>
<script type="text/plain" id="grabber-src"></script>
<script src="vendor/chart.umd.min.js"></script>
<script src="js/a.js"></script>
</body>
</html>
"""
CHART_TAG = '<script src="vendor/chart.umd.min.js"></script>\n'
# the grabber is text, not markup: URLs and tag-like strings in it must not trip the check
GRABBER = 'URL = "https://connect.garmin.com/"\n# <link rel="stylesheet" href="https://example.com/x.css">\n'


class SelfContainedPage(unittest.TestCase):
    def build(self, html=PAGE, css="body{color:var(--ink)}\n", extra=None):
        build = load_build()
        version = getattr(build, "CHART_VERSION", "4.4.1")
        files = {
            "index.html": html,
            "styles.css": css,
            "vendor/tokens.css": "@layer site-kit{:root{--sk-ink:#1e232a}}\n",
            "vendor/chart.umd.min.js": f"/*!\n * Chart.js v{version}\n * https://www.chartjs.org\n"
                                       " * (c) 2023 Chart.js Contributors\n * Released under the MIT License\n */\n"
                                       "window.Chart=function(){};\n",
            "js/a.js": '"use strict";\nconst A = 1;\n',
            **(extra or {}),
        }
        with tempfile.TemporaryDirectory() as d:
            build.PAGE = Path(d)
            for name, text in files.items():
                (build.PAGE / name).parent.mkdir(parents=True, exist_ok=True)
                (build.PAGE / name).write_text(text, encoding="utf-8")
            return build.build_page(GRABBER)

    def assertFails(self, **kw):
        with self.assertRaises(SystemExit):
            self.build(**kw)

    def test_inlines_tokens_styles_and_chart(self):
        out = self.build()
        self.assertNotIn("vendor/", out)
        self.assertNotIn("styles.css", out)
        self.assertLess(out.index("--sk-ink"), out.index("color:var(--ink)"))
        self.assertLess(out.index("window.Chart="), out.index("const A = 1;"))
        self.assertIn("Released under the MIT License", out)
        self.assertIn('<a href="https://github.com/DavideBisio/garmin-run-progress">', out)
        self.assertIn(GRABBER, out)

    def test_cdn_script(self):
        self.assertFails(html=PAGE.replace(
            CHART_TAG, '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>\n'))

    def test_google_fonts_stylesheet(self):
        self.assertFails(html=PAGE.replace("<head>\n", '<head>\n<link rel="stylesheet" href='
                                           '"https://fonts.googleapis.com/css2?family=IBM+Plex+Sans&display=swap">\n'))

    def test_google_fonts_preconnect(self):
        self.assertFails(html=PAGE.replace("<head>\n", '<head>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n'))

    def test_css_import(self):
        self.assertFails(css='@import url("https://fonts.googleapis.com/css2?family=Inter");\nbody{color:red}\n')

    def test_css_remote_url(self):
        self.assertFails(css="@font-face{font-family:X;src:url(https://fonts.gstatic.com/x.woff2)}\n")

    def test_leftover_local_script(self):
        self.assertFails(html=PAGE.replace("</body>", '<script src="vendor/other.js"></script>\n</body>'),
                         extra={"vendor/other.js": "var other = 1;\n"})

    def test_leftover_local_stylesheet(self):
        self.assertFails(html=PAGE.replace("</body>", '<link rel="stylesheet" href="vendor/extra.css">\n</body>'),
                         extra={"vendor/extra.css": "body{margin:0}\n"})

    def test_chart_version_mismatch(self):
        self.assertFails(extra={"vendor/chart.umd.min.js": "/*!\n * Chart.js v3.0.0\n * Released under the MIT License\n */\n"})


if __name__ == "__main__":
    unittest.main()
