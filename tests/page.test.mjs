// Page smoke tests: run the built dist/index.html script in a Node vm with a minimal DOM stub.
// python tools/build.py && node --test tests/page.test.mjs   (or: make test)
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const ROOT = path.resolve(import.meta.dirname, "..");
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8").replace(/\r\n/g, "\n");
assert.ok(fs.existsSync(path.join(ROOT, "dist/index.html")), "dist/index.html missing: run python tools/build.py");
const html = read("dist/index.html");
const grabberSrc = /<script type="text\/plain" id="grabber-src">([\s\S]*?)<\/script>/.exec(html)[1];
const pageScript = [...html.matchAll(/<script>\n([\s\S]*?)<\/script>/g)].at(-1)[1];
const BOOT = "setData(exampleData(), true);\nidbGet()";

// scripts: the built page script, or the unbuilt src/page/js files run one after another
function runPage(data, scripts = [pageScript]) {
  const defaults = { "hr-lo": "140", "hr-hi": "150", season: "all", "hr-max": "190", "hr-rest": "50" };
  const els = {}, charts = {};
  const el = id => els[id] ??= {
    id, textContent: id === "grabber-src" ? grabberSrc : "", innerHTML: "", hidden: false,
    value: defaults[id] || "", checked: id === "no-trail" || id === "remember", className: "", style: {},
    classList: { toggle() {}, add() {}, remove() {} }, addEventListener() {}, click() {},
    firstElementChild: { style: {} }, files: [],
  };
  const ctx = {
    console, Intl, Math, Date, JSON, Map, Set, Float32Array, Uint32Array, Uint8Array, DataView, ArrayBuffer,
    Promise, setTimeout, TextEncoder, Blob: class {}, navigator: {}, indexedDB: undefined,
    document: { getElementById: el, querySelectorAll: () => [], documentElement: {}, body: {}, createElement: () => ({}) },
    getComputedStyle: () => ({ getPropertyValue: () => "#2347C5" }),
    matchMedia: () => ({ addEventListener() {} }), MutationObserver: class { observe() {} },
    Chart: class { constructor(canvas, cfg) { charts[canvas.id] = cfg; } destroy() {} },
    __DATA: data,
  };
  ctx.window = ctx;
  const last = scripts.at(-1);
  assert.ok(last.includes(BOOT), "boot line not found");
  if (data) scripts = [...scripts.slice(0, -1), last.replace(BOOT, "setData(window.__DATA, false);\nidbGet()")];
  vm.createContext(ctx);
  for (const code of scripts) vm.runInContext(code, ctx);
  const kpis = id => el(id).innerHTML.split('<div class="kpi">').length - 1;
  return { el, charts, kpis };
}

// steady 60-minute runs at 3 m/s and ~145 bpm, two a week, in the old runs.json format
function oldFormatData() {
  const runs = [];
  for (let i = 0; i < 120; i++) {
    const day = new Date(Date.UTC(2022, 0, 3) + i * 3.5 * 864e5).toISOString().slice(0, 10);
    const t = [], d = [], hr = [], e = [];
    for (let s = 0; s <= 3600; s += 10) { t.push(s); d.push(s * 3); hr.push(140 + (s % 100) / 10); e.push(2000); }
    runs.push({ id: i, date: `${day} 07:00:00`, type: "running", dist: 10800, dur: 3600, avgHr: 145, maxHr: 160, t, d, hr, e });
  }
  return { format: "garmin-runs/1", runs };
}

test("example data renders every section", () => {
  const { el, charts, kpis } = runPage();
  assert.ok(kpis("kpis") >= 4);
  assert.equal(kpis("kpis2"), 5);
  for (const id of ["c-load", "c-acwr", "c-zones", "c-week", "c-rhr", "c-dec", "c-cad", "c-stride", "c-te"])
    assert.ok(charts[id], `chart ${id} missing`);
  for (const id of ["rhr-panel", "dec-panel", "te-panel", "stride-panel"])
    assert.equal(el(id).hidden, false, `${id} hidden`);
  assert.ok(el("tbl2").innerHTML.includes("<tr>"));
});

test("old runs.json without the newer fields still renders and hides empty panels", () => {
  const { el, charts, kpis } = runPage(oldFormatData());
  assert.equal(kpis("kpis2"), 5);
  assert.ok(charts["c-load"] && charts["c-zones"]);
  for (const id of ["rhr-panel", "te-panel", "stride-panel"]) assert.equal(el(id).hidden, true, `${id} shown`);
  assert.equal(el("dec-panel").hidden, false);
});

test("the page embeds the built garmin_grab.py", () => {
  assert.equal(grabberSrc, read("dist/garmin_grab.py"));
});

const devScripts = [...read("src/page/index.html").matchAll(/<script src="js\/([\w-]+\.js)"><\/script>/g)].map(m => m[1]);

test("src/page/index.html loads every js file exactly once", () => {
  assert.deepEqual([...devScripts].sort(), fs.readdirSync(path.join(ROOT, "src/page/js")).sort());
});

test("the unbuilt src/page/js files also run as separate scripts (make dev)", () => {
  const { kpis } = runPage(oldFormatData(), devScripts.map(f => read(`src/page/js/${f}`)));
  assert.equal(kpis("kpis2"), 5);
});
