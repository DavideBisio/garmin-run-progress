#!/usr/bin/env python3
"""Build the two shipped files from src/ into dist/ (not committed):

    dist/garmin_grab.py  the src/garmin_grab/ package bundled into one script
    dist/index.html      src/page/ with styles.css and js/*.js inlined and the
                         bundled grabber embedded (for "Copy script" and the zip)

CI deploys dist/ to GitHub Pages and attaches both files to each release.

Usage (from the repo root):
    python tools/build.py
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "garmin_grab"
PAGE = ROOT / "src" / "page"
DIST = ROOT / "dist"

# dependency order: each module may only import from the ones before it
MODULES = ["config", "storage", "activities", "garmin", "rhr", "gpx", "export", "cli"]

CSS_LINK = '<link rel="stylesheet" href="styles.css">\n'
JS_TAGS = re.compile(r'(?:<script src="js/[\w-]+\.js"></script>\n)+')
JS_NAME = re.compile(r'<script src="js/([\w-]+)\.js"></script>')
GRABBER = re.compile(r'(<script type="text/plain" id="grabber-src">)(.*?)(</script>)', re.S)


def fail(msg):
    sys.exit(f"build: {msg}")


# ---------------------------------------------------------------- grabber
def top_level_names(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def bundle_grabber():
    init = (PKG / "__init__.py").read_text(encoding="utf-8")
    doc = ast.parse(init).body[0]
    header = ast.get_source_segment(init, doc)

    plain, froms, sections, defined = set(), {}, [], {}
    for name in MODULES:
        src = (PKG / f"{name}.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        drop = set()
        for node in tree.body:
            is_doc = (node is tree.body[0] and isinstance(node, ast.Expr)
                      and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))
            if isinstance(node, ast.Import):
                plain.add(ast.get_source_segment(src, node))
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                froms.setdefault(node.module, set()).update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level != 1 or node.module not in defined:
                    fail(f"{name}.py: 'from .{node.module or ''} import' must name a module listed before it")
                for a in node.names:
                    if a.asname or a.name not in defined[node.module]:
                        fail(f"{name}.py: cannot import {a.name} from .{node.module}")
            elif not is_doc:
                continue
            drop.update(range(node.lineno, node.end_lineno + 1))
        names = top_level_names(tree)
        for other, theirs in defined.items():
            if names & theirs:
                fail(f"{name}.py and {other}.py both define {', '.join(sorted(names & theirs))}")
        defined[name] = names
        lines = [l for i, l in enumerate(src.splitlines(), 1) if i not in drop]
        body = "\n".join(lines).strip("\n")
        sections.append(f"# ---------------------------------------------------------------- {name}\n{body}\n")

    imports = sorted(plain, key=lambda s: s.split()[1])
    imports += [f"from {m} import {', '.join(sorted(n))}" for m, n in sorted(froms.items())]
    return ("#!/usr/bin/env python3\n" + header + "\n"
            "# Built from src/garmin_grab/ by tools/build.py. Edit those files, not this one.\n\n"
            + "\n".join(imports) + "\n\n\n"
            + "\n\n".join(sections)
            + '\n\nif __name__ == "__main__":\n    main()\n')


# ---------------------------------------------------------------- page
def build_page(grabber):
    if "</script" in grabber.lower():
        fail("the grabber contains '</script', which would break the page")
    html = (PAGE / "index.html").read_text(encoding="utf-8")
    if html.count(CSS_LINK) != 1:
        fail("src/page/index.html must link styles.css exactly once")
    css = (PAGE / "styles.css").read_text(encoding="utf-8")
    html = html.replace(CSS_LINK, f"<style>\n{css}</style>\n")

    tags = JS_TAGS.findall(html)
    if len(tags) != 1:
        fail("src/page/index.html must load its js/*.js files in one block of <script src> tags")
    parts = []
    for name in JS_NAME.findall(tags[0]):
        js = (PAGE / "js" / f"{name}.js").read_text(encoding="utf-8")
        parts.append(js.removeprefix('"use strict";\n'))
    script = '<script>\n(() => {\n"use strict";\n' + "\n".join(parts) + "})();\n</script>\n"
    html = html.replace(tags[0], script)

    m = GRABBER.search(html)
    if not m:
        fail("could not find the grabber-src block in src/page/index.html")
    return html[:m.start(2)] + grabber + html[m.end(2):]


def main():
    grabber = bundle_grabber()
    page = build_page(grabber)
    DIST.mkdir(exist_ok=True)
    (DIST / "garmin_grab.py").write_text(grabber, encoding="utf-8", newline="\n")
    (DIST / "index.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"built {DIST.name}/garmin_grab.py and {DIST.name}/index.html")


if __name__ == "__main__":
    main()
