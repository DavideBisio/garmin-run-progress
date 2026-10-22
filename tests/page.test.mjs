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
// opts.hash installs window.location (hash writes and replace() recorded) and window.addEventListener
function runPage(data, scripts = [pageScript], opts = {}) {
  const defaults = { "hr-lo": "140", "hr-hi": "150", season: "all", "hr-max": "190", "hr-rest": "50" };
  const els = {}, charts = {};
  const el = id => els[id] ??= {
    id, textContent: id === "grabber-src" ? grabberSrc : "", innerHTML: "", hidden: false,
    value: defaults[id] || "", checked: id === "no-trail" || id === "remember", className: "", style: {},
    classList: { toggle() {}, add() {}, remove() {} }, click() {},
    listeners: {}, addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); },
    firstElementChild: { style: {} }, files: [],
    attrs: {}, setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] ?? null; },
    tabIndex: 0, focus() { focused.push(id); },
  };
  const focused = [], resized = [], hashes = [], winListeners = {};
  const defined = [];
  const ctx = {
    console, Intl, Math, Date, JSON, Map, Set, Float32Array, Uint32Array, Uint8Array, DataView, ArrayBuffer,
    Promise, setTimeout, TextEncoder, Blob: class {}, navigator: {}, indexedDB: undefined,
    document: { getElementById: el, querySelectorAll: () => [], documentElement: { dataset: {} }, body: {}, createElement: () => ({}) },
    getComputedStyle: () => ({ getPropertyValue: () => "#2347C5" }),
    matchMedia: () => ({ matches: false, addEventListener() {} }), MutationObserver: class { observe() {} },
    Chart: class { constructor(canvas, cfg) { charts[canvas.id] = cfg; this.id = canvas.id; } destroy() {} resize() { resized.push(this.id); } },
    // just enough for site-bar.js to register itself
    HTMLElement: class {},
    customElements: { define(name) { defined.push(name); }, get: name => defined.includes(name) ? class {} : undefined },
    localStorage: { getItem: () => null, setItem() {} },
    __DATA: data,
  };
  ctx.window = ctx;
  if (opts.hash !== undefined) {
    let hash = opts.hash;
    ctx.location = { get hash() { return hash; }, set hash(h) { hashes.push(["push", h]); hash = h; },
      replace(u) { hashes.push(["replace", u]); hash = u.slice(u.indexOf("#")); } };
    ctx.addEventListener = (type, fn) => { (winListeners[type] ??= []).push(fn); };
  }
  const last = scripts.at(-1);
  assert.ok(last.includes(BOOT), "boot line not found");
  if (data) scripts = [...scripts.slice(0, -1), last.replace(BOOT, "setData(window.__DATA, false);\nidbGet()")];
  vm.createContext(ctx);
  for (const code of scripts) vm.runInContext(code, ctx);
  const kpis = id => el(id).innerHTML.split('<div class="kpi">').length - 1;
  return { el, charts, kpis, defined, focused, resized, hashes, winListeners, ctx };
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

// runs with Garmin's zone times only (no t/d/hr/e streams), two a week
function hrzOnlyData() {
  const runs = [];
  for (let i = 0; i < 40; i++) {
    const day = new Date(Date.UTC(2023, 0, 2) + i * 3.5 * 864e5).toISOString().slice(0, 10);
    runs.push({ id: i, date: `${day} 07:00:00`, type: "treadmill_running", dist: 8000, dur: 3600, moving: 3600, avgHr: 140, maxHr: 165, hrz: [600, 1800, 900, 200, 100] });
  }
  return { format: "garmin-runs/1", runs };
}

// metrics.js alone in its own context
function metrics() {
  const ctx = vm.createContext({ Math, Float32Array });
  vm.runInContext(read("src/page/js/metrics.js"), ctx);
  return ctx;
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
  assert.match(el("lim-hint").textContent, /50 bpm is a placeholder/);
});

test("the page defines <site-bar> exactly once", () => {
  assert.deepEqual(runPage().defined, ["site-bar"]);
});

test("the built page loads no third-party scripts or stylesheets", () => {
  assert.doesNotMatch(html, /<script\b[^>]*\bsrc\s*=\s*["']?(?:https?:)?\/\//i);
  assert.doesNotMatch(html, /<link\b[^>]*\bhref\s*=\s*["']?(?:https?:)?\/\//i);
});

test("the inlined Chart.js bundle defines Chart", () => {
  const blocks = [...html.matchAll(/<script>\n([\s\S]*?)<\/script>/g)].map(m => m[1]);
  const bundle = blocks.find(b => b.includes("Chart.js v"));
  assert.ok(bundle, "no inlined Chart.js <script> block");
  assert.ok(blocks.indexOf(bundle) < blocks.length - 1, "Chart.js must come before the page script");
  assert.match(bundle, /Released under the MIT License/);
  const ctx = vm.createContext({});
  vm.runInContext(bundle, ctx);
  assert.equal(typeof ctx.Chart, "function");
});

test("the page embeds the built garmin_grab.py", () => {
  assert.equal(grabberSrc, read("dist/garmin_grab.py"));
});

const devScripts = [...read("src/page/index.html").matchAll(/<script src="js\/([\w-]+\.js)"><\/script>/g)].map(m => m[1]);

test("src/page/index.html loads every js file exactly once, site-bar.js first", () => {
  assert.deepEqual([...devScripts].sort(), fs.readdirSync(path.join(ROOT, "src/page/js")).sort());
  assert.equal(devScripts[0], "site-bar.js");
});

test("the unbuilt src/page/js files also run as separate scripts (make dev)", () => {
  const { kpis } = runPage(oldFormatData(), devScripts.map(f => read(`src/page/js/${f}`)));
  assert.equal(kpis("kpis2"), 5);
});

test("TC-4 hrrZones: Karvonen bounds rounded half up, rest clamped to max - 20", () => {
  const { hrrZones } = metrics();
  assert.equal(typeof hrrZones, "function");
  assert.deepEqual([...hrrZones(190, 50)], [134, 148, 162, 176]);
  assert.deepEqual([...hrrZones(185, 52)], [132, 145, 158, 172]);
  assert.deepEqual([...hrrZones(185, 50)], [131, 145, 158, 172]);   // 144.5 and 171.5 round up
  assert.deepEqual([...hrrZones(150, 140)], [142, 144, 146, 148]);  // rest clamped to 130
});

test("TC-5 zoneTime buckets bpm against the rounded HRR bounds; a bound belongs to the upper zone", () => {
  const { zoneTime } = metrics();
  const bpm = [40, 133, 134, 147, 148, 175, 176, 200];
  const r = { _hrOk: true, t: [0, ...bpm.map((_, i) => (i + 1) * 10)], hr: [120, ...bpm] };
  assert.deepEqual([...zoneTime(r, 190, 50)], [20, 20, 10, 10, 20]);
  assert.deepEqual([...zoneTime({ _hrOk: false, hrz: [1, 2, 3, 4, 5, 6] }, 190, 50)], [1, 2, 3, 4, 5]);
  assert.equal(zoneTime({ _hrOk: false }, 190, 50), null);
});

test("TC-6 the zones legend shows live bpm ranges and follows the max/resting inputs", () => {
  const { el } = runPage();
  const range = (max, rest) => { const b = metrics().hrrZones(max, rest);
    return [`Z1 &lt;${b[0]}`, `Z2 ${b[0]}–${b[1]}`, `Z3 ${b[1]}–${b[2]}`, `Z4 ${b[2]}–${b[3]}`, `Z5 ${b[3]}+`]; };
  for (const s of range(+el("hr-max").value, +el("hr-rest").value)) assert.ok(el("zones-legend").innerHTML.includes(s), `legend lacks ${s}`);
  el("hr-max").value = "200"; el("hr-rest").value = "60";
  for (const fn of el("hr-max").listeners.change ?? []) fn({});
  for (const s of range(200, 60)) assert.ok(el("zones-legend").innerHTML.includes(s), `legend lacks ${s} after change`);
  assert.ok(el("zones-legend").innerHTML.includes("Z2 144–158"));
});

test("TC-7 runs without a usable HR stream are counted; easy share is below 70% of HRR", () => {
  const { el } = runPage(hrzOnlyData());
  assert.equal(el("zones-fallback").hidden, false);
  assert.match(el("zones-fallback").textContent, /\b40 runs without a usable heart-rate stream use Garmin's zones/);
  assert.match(el("zones-fallback").textContent, /%HRR|HRR zones/);
  const ex = runPage();
  const kpi = ex.el("kpis2").innerHTML.split('<div class="kpi">').find(k => k.includes("Easy share"));
  assert.ok(kpi.includes("70% of heart-rate reserve"), "easy-share text not HRR-based");
  const v = +/<span class="val">(\d+)%<\/span>/.exec(kpi)[1];
  assert.ok(v > 0 && v < 100, `easy share ${v}`);
});

const TABS = ["data", "analysis", "planning"];
const visible = el => TABS.filter(t => !el(`tab-${t}`).hidden);
const tick = () => new Promise(r => setTimeout(r, 0));

test("TC-8 tabs.js loads once before boot.js; three tabpanels, only Data shown after boot", () => {
  assert.equal(devScripts.filter(f => f === "tabs.js").length, 1);
  assert.ok(devScripts.indexOf("tabs.js") < devScripts.indexOf("boot.js"), "tabs.js must load before boot.js");
  assert.equal(html.match(/role="tabpanel"/g)?.length, 3);
  for (const t of TABS) assert.ok(new RegExp(`<section[^>]*\\bid="tab-${t}"`).test(html), `no tab-${t} section`);
  const { el } = runPage();
  assert.deepEqual(visible(el), ["data"]);
});

test("TC-9 the URL hash picks the tab, old #s1/#s2/#s3 anchors too", () => {
  for (const [hash, tab] of [["#planning", "planning"], ["#analysis", "analysis"], ["#data", "data"], ["#s3", "analysis"], ["#s1", "data"], ["#s2", "data"], ["", "data"], ["#nope", "data"]]) {
    const { el } = runPage(undefined, [pageScript], { hash });
    assert.deepEqual(visible(el), [tab], `hash ${hash}`);
  }
  for (const id of TABS) assert.ok(!new RegExp(`\\bid="${id}"`).test(html), `no element may have id ${id}`);
});

test("TC-10 a user file load opens Analysis and resizes its charts; example boot and Forget stay put", async () => {
  const d = oldFormatData();
  const { el, resized, hashes } = runPage(undefined, [pageScript], { hash: "" });
  await tick();
  assert.deepEqual(visible(el), ["data"], "example boot left Data");
  resized.length = 0;
  el("file").files = [{ name: "runs.json", text: async () => JSON.stringify(d) }];
  el("file").listeners.change[0]();
  await tick(); await tick();
  assert.match(el("status-t").textContent, /Your data · 120 runs/);
  assert.deepEqual(visible(el), ["analysis"], "user load did not open Analysis");
  assert.ok(resized.includes("c-eff") && resized.includes("c-zones"), `charts not resized: ${resized}`);
  assert.deepEqual(hashes.at(-1), ["push", "#analysis"]);
  el("clear").listeners.click[0]();
  await tick(); await tick();
  assert.match(el("status-t").textContent, /Example data/);
  assert.deepEqual(visible(el), ["analysis"], "Forget my data switched tabs");
});

test("TC-11 WAI-ARIA tabs: roles, one aria-selected, arrow keys wrap, Home/End; no location is fine", () => {
  const attrs = tag => Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1], m[2]]));
  const tabs = [...html.matchAll(/<button[^>]*role="tab"[^>]*>/g)].map(m => attrs(m[0]));
  assert.deepEqual(tabs.map(a => [a.id, a["aria-controls"]]), TABS.map(t => [`tab-btn-${t}`, `tab-${t}`]));
  const panels = [...html.matchAll(/<section[^>]*role="tabpanel"[^>]*>/g)].map(m => attrs(m[0]));
  assert.deepEqual(panels.map(a => [a.id, a["aria-labelledby"]]), TABS.map(t => [`tab-${t}`, `tab-btn-${t}`]));
  assert.ok(/role="tablist"/.test(html), "no tablist");
  let page;
  assert.doesNotThrow(() => { page = runPage(); });
  const { el, focused } = page;
  const selected = () => TABS.filter(t => el(`tab-btn-${t}`).getAttribute("aria-selected") === "true");
  const key = (t, k) => el(`tab-btn-${t}`).listeners.keydown[0]({ key: k, preventDefault() {} });
  const check = t => {
    assert.deepEqual(visible(el), [t]); assert.deepEqual(selected(), [t]);
    for (const u of TABS) assert.equal(el(`tab-btn-${u}`).tabIndex, u === t ? 0 : -1);
  };
  check("data");
  key("data", "ArrowLeft"); check("planning"); assert.equal(focused.at(-1), "tab-btn-planning");
  key("planning", "ArrowRight"); check("data"); assert.equal(focused.at(-1), "tab-btn-data");
  key("data", "ArrowRight"); check("analysis");
  key("analysis", "End"); check("planning");
  key("planning", "Home"); check("data");
  el("tab-btn-analysis").listeners.click[0]({}); check("analysis");
});

test("arrow keys replace the hash, clicks add a history entry", () => {
  const { el, hashes } = runPage(undefined, undefined, { hash: "" });
  el("tab-btn-data").listeners.keydown[0]({ key: "ArrowRight", preventDefault() {} });
  el("tab-btn-analysis").listeners.keydown[0]({ key: "End", preventDefault() {} });
  assert.deepEqual(hashes, [["replace", "#analysis"], ["replace", "#planning"]]);
  el("tab-btn-data").listeners.click[0]({});
  assert.deepEqual(hashes.at(-1), ["push", "#data"]);
});
