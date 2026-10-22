// Project site checks on the built site/dist (run `make site-build` first): make site-test
// CI runs them after the site build; they are not part of `make test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const DIST = path.join(ROOT, "site/dist");
assert.ok(fs.existsSync(DIST), "site/dist missing: run make site-build");

const htmlFiles = dir => fs.readdirSync(dir, { withFileTypes: true }).flatMap(e =>
  e.isDirectory() ? htmlFiles(path.join(dir, e.name)) : e.name.endsWith(".html") ? [path.join(dir, e.name)] : []);

test("the app is published at /app/", () => {
  assert.ok(fs.existsSync(path.join(DIST, "app/index.html")));
});

test("the repo docs are published as pages", () => {
  for (const page of ["docs/features/resting-heart-rate/index.html", "docs/roadmap/index.html",
                      "docs/roadmap/readme/index.html"])
    assert.ok(fs.existsSync(path.join(DIST, page)), `${page} missing`);
});

test("no link points to a .md file or climbs out of the site", () => {
  const bad = [];
  for (const file of htmlFiles(DIST)) {
    const html = fs.readFileSync(file, "utf8");
    for (const [, href] of html.matchAll(/\shref="([^"]*)"/g))
      // absolute URLs are fine: the docs' "Edit on GitHub" links do point at the .md source
      if ((!/^[a-z][a-z0-9+.-]*:/i.test(href) && /\.mdx?(?:#.*)?$/i.test(href)) || href.includes("/garmin-run-progress/../"))
        bad.push(`${path.relative(DIST, file)}: ${href}`);
  }
  assert.deepEqual(bad, []);
});
