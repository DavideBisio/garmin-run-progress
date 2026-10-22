#!/usr/bin/env python3
"""Build the two shipped files from src/ into dist/ (not committed):

    dist/garmin_grab.py  the src/garmin_grab/ package bundled into one script
    dist/index.html      src/page/ as one self-contained file: vendor/tokens.css and
                         styles.css, the vendored Chart.js and js/*.js inlined, and the
                         bundled grabber embedded (for "Copy script" and the zip)

The page makes no third-party requests, so the release's index.html works opened
from disk. The build fails if any remote script, stylesheet, font or CSS import, or
any local .js/.css file it does not inline, is left in the page.

The Pages workflow copies dist/index.html into the project site at /app/; the release
workflow attaches both files to each GitHub Release.

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

# Chart.js is vendored in src/page/vendor/; this is the one place its version is recorded
# (the build checks it against the file's license header; docs/deploy.md points here).
CHART_VERSION = "4.4.1"
CHART_JS = "vendor/chart.umd.min.js"

# local stylesheets inlined in place, in this order (the kit's tokens before the app's styles)
CSS_FILES = ["vendor/tokens.css", "styles.css"]
# local classic scripts inlined in place, each as its own <script> block before the page script
VENDOR_JS = [CHART_JS]

JS_TAGS = re.compile(r'(?:<script src="js/[\w-]+\.js"></script>\n)+')
JS_NAME = re.compile(r'<script src="js/([\w-]+)\.js"></script>')
GRABBER = re.compile(r'(<script type="text/plain" id="grabber-src">)(.*?)(</script>)', re.S)

# self-containment check on the finished page
SCRIPT_BODY = re.compile(r"(<script\b[^>]*>).*?(</script\s*>)", re.S | re.I)
LOADING_TAG = re.compile(r"<(?:script|link)\b[^>]*>", re.I)
TAG_URL = re.compile(r"""\b(?:src|href)\s*=\s*["']?([^"'\s>]+)""", re.I)
REMOTE = re.compile(r"^(?:https?:)?//", re.I)
LOCAL_ASSET = re.compile(r"\.(?:js|css)(?:[?#].*)?$", re.I)
CSS_REMOTE = re.compile(r"""@import\b|url\(\s*["']?(?:https?:)?//""", re.I)


def fail(msg):
    sys.exit(f"build: {msg}")


# ---------------------------------------------------------------- grabber
def top_level_names(tree):
    """The names a module defines, and the names its absolute imports bind (name -> what it binds)."""
    defs, imports = set(), {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            defs.update(n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name))
        elif isinstance(node, ast.Import):
            for a in node.names:
                imports[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for a in node.names:
                imports[a.asname or a.name] = f"{node.module}.{a.name}"
    return defs, imports


def clashes(defs, imports, other_defs, other_imports):
    """Names two modules can't both bind once they share the bundle's single namespace."""
    found = defs & other_defs | defs & other_imports.keys() | other_defs & imports.keys()
    return found | {n for n in imports.keys() & other_imports.keys() if imports[n] != other_imports[n]}


def bundle_grabber():
    init = (PKG / "__init__.py").read_text(encoding="utf-8")
    doc = ast.parse(init).body[0]
    header = ast.get_source_segment(init, doc)

    plain, froms, sections, defined = set(), {}, [], {}
    for name in MODULES:
        src = (PKG / f"{name}.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        top = {id(node) for node in tree.body}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level and id(node) not in top:
                fail(f"{name}.py line {node.lineno}: 'from .{node.module or ''} import' must be at the top level")
        drop = set()
        for node in tree.body:
            is_doc = (node is tree.body[0] and isinstance(node, ast.Expr)
                      and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))
            if isinstance(node, ast.Import):
                plain.add(ast.get_source_segment(src, node))
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                froms.setdefault(node.module, set()).update(
                    f"{a.name} as {a.asname}" if a.asname else a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level != 1 or node.module not in defined:
                    fail(f"{name}.py: 'from .{node.module or ''} import' must name a module listed before it")
                for a in node.names:
                    if a.asname or a.name not in defined[node.module][0]:
                        fail(f"{name}.py: cannot import {a.name} from .{node.module}")
            elif not is_doc:
                continue
            drop.update(range(node.lineno, node.end_lineno + 1))
        names = top_level_names(tree)
        for other, theirs in defined.items():
            if both := clashes(*names, *theirs):
                fail(f"{name}.py and {other}.py both bind {', '.join(sorted(both))}")
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
def check_self_contained(html):
    """Fail on anything the page would fetch: remote scripts, stylesheets, fonts and other
    <link>s (any rel), CSS imports and remote url()s, and local .js/.css files that were not
    inlined. Links (<a href>) are fine. Inline script bodies (the vendored Chart.js, the page
    script and the grabber's text/plain source) are text, not markup, so they are skipped."""
    markup = SCRIPT_BODY.sub(r"\1\2", html)
    for tag in LOADING_TAG.findall(markup):
        m = TAG_URL.search(tag)
        if not m:
            continue
        if REMOTE.match(m[1]):
            fail(f"the page must not load anything from another site: {tag}")
        if LOCAL_ASSET.search(m[1]):
            fail(f"src/page/index.html loads a file the build does not inline: {tag}")
    if m := CSS_REMOTE.search(markup):
        fail(f"the page's CSS must not import or load remote files: {markup[m.start():m.start() + 80]!r}")


def inline_vendor_js(html, name):
    tag = f'<script src="{name}"></script>\n'
    if html.count(tag) != 1:
        fail(f"src/page/index.html must load {name} exactly once")
    js = (PAGE / name).read_text(encoding="utf-8")
    if "</script" in js.lower():
        fail(f"{name} contains '</script', which would break the page")
    if name == CHART_JS:
        m = re.search(r"Chart\.js v([\w.-]+)", js[:500])
        if not m or m[1] != CHART_VERSION or "MIT License" not in js[:500]:
            fail(f"{name} must start with the Chart.js v{CHART_VERSION} MIT license header (CHART_VERSION in tools/build.py)")
    return html.replace(tag, f"<script>\n{js.rstrip()}\n</script>\n")


def build_page(grabber):
    if "</script" in grabber.lower():
        fail("the grabber contains '</script', which would break the page")
    html = (PAGE / "index.html").read_text(encoding="utf-8")
    at = []
    for name in CSS_FILES:
        link = f'<link rel="stylesheet" href="{name}">\n'
        if html.count(link) != 1:
            fail(f"src/page/index.html must link {name} exactly once")
        at.append(html.index(link))
        css = (PAGE / name).read_text(encoding="utf-8")
        if "</style" in css.lower():
            fail(f"{name} contains '</style', which would break the page")
        html = html.replace(link, f"<style>\n{css}</style>\n")
    if at != sorted(at):
        fail(f"src/page/index.html must link {', '.join(CSS_FILES)} in that order")

    for name in VENDOR_JS:
        html = inline_vendor_js(html, name)

    tags = JS_TAGS.findall(html)
    if len(tags) != 1:
        fail("src/page/index.html must load its js/*.js files in one block of <script src> tags")
    parts = []
    for name in JS_NAME.findall(tags[0]):
        js = (PAGE / "js" / f"{name}.js").read_text(encoding="utf-8")
        # site-bar.js (a verbatim site-kit copy) shows "<script ...></script>" in its usage
        # comment; "<\/script" means the same in JS comments, strings and regexes
        js = re.sub(r"</(script)", r"<\\/\1", js, flags=re.I)
        parts.append(js.removeprefix('"use strict";\n'))
    script = '<script>\n(() => {\n"use strict";\n' + "\n".join(parts) + "})();\n</script>\n"
    html = html.replace(tags[0], script)

    m = GRABBER.search(html)
    if not m:
        fail("could not find the grabber-src block in src/page/index.html")
    html = html[:m.start(2)] + grabber + html[m.end(2):]
    check_self_contained(html)
    return html


def main():
    grabber = bundle_grabber()
    page = build_page(grabber)
    DIST.mkdir(exist_ok=True)
    (DIST / "garmin_grab.py").write_text(grabber, encoding="utf-8", newline="\n")
    (DIST / "index.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"built {DIST.name}/garmin_grab.py and {DIST.name}/index.html")


if __name__ == "__main__":
    main()
