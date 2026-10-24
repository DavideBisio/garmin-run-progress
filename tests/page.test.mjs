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
  const focused = [], resized = [], destroyed = [], hashes = [], winListeners = {};
  const defined = [];
  const ctx = {
    console, Intl, Math, Date, JSON, Map, Set, Float32Array, Uint32Array, Uint8Array, DataView, ArrayBuffer,
    Promise, setTimeout, TextEncoder, Blob: class {}, navigator: {}, indexedDB: undefined,
    document: { getElementById: el, querySelectorAll: () => [], documentElement: { dataset: {} }, body: {}, createElement: () => ({}) },
    getComputedStyle: () => ({ getPropertyValue: () => "#2347C5" }),
    matchMedia: () => ({ matches: false, addEventListener() {} }), MutationObserver: class { observe() {} },
    Chart: class { constructor(canvas, cfg) { charts[canvas.id] = cfg; this.id = canvas.id; } destroy() { destroyed.push(this.id); } resize() { resized.push(this.id); } },
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
  return { el, charts, kpis, defined, focused, resized, destroyed, hashes, winListeners, ctx };
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

test("the app's bar links the same pages as the site header, in the same order", () => {
  const bar = html.match(/<site-bar[^>]*>([\s\S]*?)<\/site-bar>/)[1];
  const links = [...bar.matchAll(/<a slot="links" href="([^"]+)"[^>]*>([^<]+)<\/a>/g)].map(m => [m[2], m[1]]);
  assert.deepEqual(links, [["Overview", "../"], ["Docs", "../docs/"], ["App", "./"]]);
  const nav = read("site/astro.config.mjs").match(/nav: \[([\s\S]*?)\]/)[1];
  assert.deepEqual([...nav.matchAll(/label: '([^']+)'/g)].map(m => m[1]), links.map(l => l[0]));
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

// ---------------------------------------------------------------- Planning tab (roadmap 10)
const planStep = (label, role, zone, pace, hrZone, hr, end, value, meters, seconds, note = "") =>
  ({ type: "step", role, label, end, value, zone, pace_s_per_km: pace, hr_zone: hrZone, hr, est_pace_s_per_km: null,
     est_dist: null, est_time: null, effort: null, note, hard: role === "rep", meters, seconds });
const easyRun = km => ({ id: "easy", variant: 1, title: "Easy Run", kind: "E", km, seconds: km * 380, hard_km: 0, climb_m_per_km: null,
  steps: [planStep("Run", "rep", "E", [369, 391], "Z2", [134, 148], "dist", km * 1000, km * 1000, km * 380)] });
const tempoRun = () => ({ id: "cruise_tempo", variant: 2, title: "Cruise Tempo", kind: "T", km: 7.03, seconds: 2427, hard_km: 3.6, climb_m_per_km: null,
  steps: [planStep("Warmup", "warmup", "E", [369, 391], "Z2", [134, 148], "dist", 2000, 2000, 760),
    { type: "repeat", n: 3, skip_last_rest: false, note: "", meters: 4027.6, seconds: 1287.2, steps: [
      planStep("Tempo", "rep", "T", [300, 310], "Z4", [162, 176], "dist", 1200, 1200, 366),
      planStep("Recovery", "recovery", "jog", null, "Z2", [134, 148], "time", 60, 142.5, 60)] },
    planStep("Cooldown", "cooldown", "E", [369, 391], "Z2", [134, 148], "lap", null, 1000, 380)] });
const planDayOf = (date, slot, workout, extra = {}) => ({ date, slot, status: null, activity_id: null, changed_by: null, workout, ...extra });
const planRun = (date, km, min = km * 6.3) => ({ id: date, date: `${date} 07:00:00`, type: "running", dist: km * 1000, dur: min * 60, avgHr: 140, maxHr: 170 });

// example: true pins the runner's today to the day after the last run: Sat 2024-06-15. No day has a
// status field (a plan from before 09), so the page matches the runs by date.
function planData() {
  const runs = [planRun("2024-05-20", 8), planRun("2024-06-04", 7), planRun("2024-06-07", 6), planRun("2024-06-09", 5, 30),
    planRun("2024-06-11", 7), planRun("2024-06-12", 2, 12), planRun("2024-06-14", 5)];
  const plan = { version: 1, generated: "2024-06-10T08:00:00",
    profile: { vdot: 40.0, hr_max: 185, hr_rest: 50, race: { date: "2024-09-29", distance_m: 21097.5, goal_s: 6210 } },
    levels: { volume: "novice", quality: "intermediate", reasons: {} },
    progress: { plan_start: "2024-06-10", block_start: "2024-05-13", vdot: null },
    warnings: [{ rule: "feasibility", detail: "the goal needs <b>VDOT 43.4</b>", action: "kept the paces" }],
    weeks: [
      { start: "2024-05-20", target_km: 15, unit: "km", phase: "base", deload: true, warnings: [], days: [planDayOf("2024-05-20", "E", easyRun(8))] },
      { start: "2024-05-27", target_km: 20, unit: "km", phase: "base", deload: false, warnings: [], days: [planDayOf("2024-05-28", "E", easyRun(6))] },
      { start: "2024-06-03", target_km: 30, unit: "km", phase: "base", deload: false, warnings: [], days: [
        planDayOf("2024-06-04", "Q", tempoRun()),
        planDayOf("2024-06-06", "E", easyRun(6)),
        planDayOf("2024-06-08", "E", easyRun(5)),
        planDayOf("2024-06-09", "L", easyRun(12)),
      ] },
      { start: "2024-06-10", target_km: 40, unit: "km", phase: "rt", deload: false, warnings: [], days: [
        planDayOf("2024-06-10", "E", easyRun(6)),      // no run Sun-Tue but on days with their own session: missed
        planDayOf("2024-06-11", "Q", tempoRun()),      // 7 km that day: done
        planDayOf("2024-06-12", "E", easyRun(5)),      // 2 km in 12 min: partial
        planDayOf("2024-06-13", "E", easyRun(5)),      // the run is on Fri, a rest day: moved
        planDayOf("2024-06-15", "E", easyRun(5)),      // today: next
        planDayOf("2024-06-16", "L", easyRun(12)),
      ] },
      { start: "2024-06-17", target_km: 32, unit: "km", phase: "rt", deload: true, warnings: [], days: [planDayOf("2024-06-18", "Q", tempoRun())] },
    ] };
  return { format: "garmin-runs/1", example: true, runs, plan };
}
const cards = el => [...el("plan-days").innerHTML.matchAll(/<button[^>]*data-i="(\d)"[^>]*>([\s\S]*?)<\/button>/g)];
const cardStatus = el => cards(el).map(m => (/class="pst (\w+)"/.exec(m[2]) || [])[1] || "");
const clickCard = (el, i) => el("plan-days").listeners.click[0]({ target: { closest: () => ({ getAttribute: () => String(i) }) } });

test("plan.js loads exactly once, after training.js and before tabs.js and boot.js", () => {
  assert.equal(devScripts.filter(f => f === "plan.js").length, 1);
  const at = f => devScripts.indexOf(f);
  assert.ok(at("training.js") >= 0 && at("training.js") < at("plan.js") && at("plan.js") < at("tabs.js") && at("tabs.js") < at("boot.js"), devScripts.join(" "));
});

test("a runs.json without a plan shows the empty Planning state and still renders the other tabs", () => {
  for (const data of [oldFormatData(), { ...oldFormatData(), plan: { version: 1 } }, { ...oldFormatData(), plan: [1] }]) {
    const { el, kpis, charts } = runPage(data);
    assert.equal(el("plan-empty").hidden, false);
    assert.equal(el("plan-view").hidden, true);
    assert.equal(kpis("kpis2"), 5);
    assert.ok(charts["c-load"] && charts["c-eff"]);
  }
});

test("a plan shows this week as 7 day cards, a header line and the HR note", () => {
  const data = planData();
  data.plan.weeks[3].days[1].workout.steps[1].n = '3x<img src=x onerror="alert(1)">';
  const { el } = runPage(data);
  assert.equal(el("plan-empty").hidden, true);
  assert.equal(el("plan-view").hidden, false);
  const c = cards(el);
  assert.equal(c.length, 7);
  assert.deepEqual(c.map(m => +m[1]), [0, 1, 2, 3, 4, 5, 6]);
  assert.match(c[1][2], /Cruise Tempo/);
  assert.match(c[1][2], /7\.0 km/);
  assert.match(c[1][2], /5:00–5:10/);                          // the main step: the tempo reps
  assert.match(c[1][2], /Z4 162–176/);
  assert.match(c[1][2], /--z4/);
  assert.match(c[4][2], /Rest/);
  assert.match(el("plan-week-h").textContent, /^This week \(block 2, week 3 · R \+ T\)/);
  const head = el("plan-head").innerHTML;
  for (const s of ["Novice volume", "intermediate quality", "VDOT 40", "Half marathon", "in 15 wk"]) assert.ok(head.includes(s), `header lacks ${s}: ${head}`);
  assert.ok(el("plan-warn").innerHTML.includes("&lt;b&gt;VDOT 43.4&lt;/b&gt;"), "warnings not escaped");
  clickCard(el, 1);
  assert.match(el("plan-detail").innerHTML, /Cruise Tempo/);
  assert.doesNotMatch(el("plan-detail").innerHTML, /<img|onerror/, "repeat count not escaped");
  assert.equal(el("plan-note").hidden, false);                 // plan 185/50, page 170/50
  assert.match(el("plan-note").textContent, /185/);
  el("hr-max").value = "185";
  for (const fn of el("hr-max").listeners.change ?? []) fn({});
  assert.equal(el("plan-note").hidden, true);
});

test("a plan without status fields falls back to matching the runs by date; stored statuses win", () => {
  assert.deepEqual(cardStatus(runPage(planData()).el), ["missed", "done", "partial", "moved", "rest", "next", ""]);
  const d = planData(), wk = d.plan.weeks[3].days;
  wk[0] = { ...wk[0], workout: null, changed_by: "override_skip" };
  wk[2] = { ...wk[2], status: "swapped" };
  assert.deepEqual(cardStatus(runPage(d).el), ["skipped", "done", "swapped", "moved", "rest", "next", ""]);
  const early = planData();
  early.runs = early.runs.slice(0, 4);                         // today Mon 2024-06-10
  const { el } = runPage(early);
  assert.match(el("plan-week-h").textContent, /^This week/);
  assert.deepEqual(cardStatus(el), ["next", "", "", "", "rest", "", ""]);
});

test("clicking a day card opens its step table, as plan.md shows it", () => {
  const { el } = runPage(planData());
  assert.equal(el("plan-detail").hidden, true);
  clickCard(el, 1);
  const t = el("plan-detail").innerHTML;
  assert.equal(el("plan-detail").hidden, false);
  assert.match(t, /<table/);
  for (const s of ["Lap", "Pace range", "HR", "Duration", "Comment", "Warmup", "Repeat 3x", "↳ <b>Tempo</b>", "Threshold 5:00–5:10 /km",
    "Zone 4 162–176 bpm", "1.2 km (~6:06)", "1:00 (~143 m)", "Jog", "Lap button (~6:20, ~1.0 km)", "4.0 km (~21 min)", "2.0 km (~13 min)"])
    assert.ok(t.includes(s), `detail lacks ${s}`);
  clickCard(el, 4);
  assert.match(el("plan-detail").innerHTML, /Rest day/);
});

test("the unbuilt src/page/js files render a plan too (make dev)", () => {
  const { el } = runPage(planData(), devScripts.map(f => read(`src/page/js/${f}`)));
  assert.equal(cards(el).length, 7);
});

test("plan compliance KPIs cover the 4 complete weeks before this one", () => {
  const { el, kpis } = runPage(planData());
  assert.equal(kpis("plan-kpis"), 3);
  const k = el("plan-kpis").innerHTML;
  // weeks of 05-20, 05-27, 06-03: 6 sessions, done 05-20, Q 06-04 and moved 06-06; missed 05-28 and 06-08, partial 06-09
  assert.match(k, /50%[\s\S]*3 of 6 sessions/);
  assert.match(k, /40%[\s\S]*26 of 65 km/);                   // 8 + 7 + 6 + 5 km run against 15 + 20 + 30 planned
  assert.match(k, /1\/1/);
});

test("the block chart: planned against actual km per plan week, phase bands and deloads", () => {
  const { charts } = runPage(planData());
  const cfg = charts["c-plan"];
  assert.ok(cfg, "no c-plan chart");
  const [planned, actual] = cfg.data.datasets;
  assert.equal(cfg.data.datasets.length, 2);
  assert.deepEqual([...planned.data], [15, 20, 30, 40, 32]);
  assert.deepEqual([...actual.data], [8, 0, 18, 14, null]);       // nothing yet for the week to come
  assert.notEqual(planned.backgroundColor[0], planned.backgroundColor[1], "deload weeks not marked");
  const bands = cfg.plugins.find(p => p.beforeDatasetsDraw);
  const rects = [], texts = [];
  bands.beforeDatasetsDraw({ ctx: { save() {}, restore() {}, fillRect(...a) { rects.push(a); }, fillText(t) { texts.push(t); } },
    chartArea: { top: 0, bottom: 100, left: 0, right: 500 }, scales: { x: { getPixelForValue: i => i * 100 + 50 } } });
  assert.equal(rects.length, 2);                               // base (3 weeks), then R + T (2)
  assert.deepEqual(texts, ["Base", "R + T"]);
});

test("opening Planning after a user load resizes its chart", async () => {
  const { el, resized } = runPage(undefined, [pageScript], { hash: "" });
  await tick();
  el("file").files = [{ name: "runs.json", text: async () => JSON.stringify(planData()) }];
  el("file").listeners.change[0]();
  await tick(); await tick();
  assert.deepEqual(visible(el), ["analysis"]);
  resized.length = 0;
  el("tab-btn-planning").listeners.click[0]({});
  assert.deepEqual(visible(el), ["planning"]);
  assert.ok(resized.includes("c-plan"), `c-plan not resized: ${resized}`);
});

test("example data renders the Planning tab: 7 day cards, header, KPIs and the chart", () => {
  const { el, charts, kpis } = runPage();
  assert.equal(el("plan-empty").hidden, true);
  assert.equal(el("plan-view").hidden, false);
  assert.equal(cards(el).length, 7);
  assert.ok(cardStatus(el).includes("next"), cardStatus(el).join(","));
  assert.match(el("plan-week-h").textContent, /^This week \(block \d+, week \d+ · /);
  assert.match(el("plan-head").innerHTML, /Half marathon in \d+ wk/);
  assert.ok(el("plan-warn").innerHTML.includes("feasibility"));
  assert.equal(kpis("plan-kpis"), 3);
  const cfg = charts["c-plan"];
  assert.ok(cfg && cfg.data.datasets.length === 2 && cfg.data.labels.length >= 8);
  assert.ok(cfg.data.labels.some(l => l.endsWith("↓")), "no deload week");
  const q = cards(el).findIndex(m => /Cruise Tempo/.test(m[2]));
  assert.ok(q >= 0, "no Q session this week");
  clickCard(el, q);
  assert.match(el("plan-detail").innerHTML, /Repeat \dx/);
});

test("the example plan has no status fields: its past days are matched to the example runs by date", () => {
  const p = runPage(undefined, devScripts.map(f => read(`src/page/js/${f}`)));
  const ex = p.ctx.exampleData(), plan = ex.plan;
  const days = plan.weeks.flatMap(w => w.days);
  assert.ok(days.every(d => d.status === null), "the example plan sets statuses");
  const last = p.ctx.decYear(ex.runs.at(-1).date).day;
  const ctx = p.ctx.planContext(plan, last + 1);
  const past = [...ctx.status].filter(([d]) => d <= last).map(([, s]) => s);
  assert.ok(past.filter(s => s === "done").length >= 5, past.join(","));
  assert.equal(past.filter(s => s === "missed").length, 1, past.join(","));
  assert.ok(plan.weeks.some(w => w.phase === "base") && plan.weeks.some(w => w.phase === "rt"));
  assert.deepEqual(Object.keys(plan.profile).sort(), ["hr_max", "hr_rest", "race", "vdot"]);
});

test("the empty Planning state says how to get a plan into runs.json", () => {
  const empty = /<div class="panel empty" id="plan-empty">([\s\S]*?)<\/div>/.exec(html)[1];
  for (const s of ["make plan", "make replan", "runs.json"]) assert.ok(empty.includes(s), `empty state lacks ${s}`);
  assert.doesNotMatch(empty, /will be made/);
});

test("a week in minutes shows the whole minutes first on the card and in the detail", () => {
  const d = planData();
  d.plan.weeks[3].unit = "min";
  const { el } = runPage(d);
  assert.match(cards(el)[1][2], /40 min · ~7\.0 km/);          // 2427 s
  assert.doesNotMatch(cards(el)[1][2], /7\.0 km · ~/);
  clickCard(el, 1);
  assert.ok(el("plan-detail").innerHTML.includes("40 min · ~7.0 km"), el("plan-detail").innerHTML);
});

test("a repeat of 1 is its steps, its note first; a skipped last rest drops or notes the last recovery", () => {
  const d = planData(), w = d.plan.weeks[3].days[1].workout, rep = w.steps[1];
  w.steps[1] = { ...rep, n: 1, skip_last_rest: true, note: "steady", steps: [{ ...rep.steps[0], note: "relax" }, rep.steps[1]] };
  let p = runPage(d);
  clickCard(p.el, 1);
  let t = p.el("plan-detail").innerHTML;
  assert.doesNotMatch(t, /Repeat/);
  assert.doesNotMatch(t, /↳/);
  assert.ok(t.includes("<td><b>Tempo</b></td>"), t);
  assert.ok(t.includes("<td>steady; relax</td>"), t);
  assert.doesNotMatch(t, /Recovery/);                          // the skipped last rest is left out
  const d3 = planData();
  d3.plan.weeks[3].days[1].workout.steps[1].skip_last_rest = true;
  p = runPage(d3);
  clickCard(p.el, 1);
  t = p.el("plan-detail").innerHTML;
  assert.match(t, /Repeat 3x[\s\S]*no recovery after the last rep/);
  assert.ok(t.includes("↳ <b>Recovery</b>"), "the nested recovery stays listed");
});

test("stored statuses done, partial, missed and moved win over the date fallback", () => {
  const d = planData(), wk = d.plan.weeks[3].days;
  // the fallback would say missed, done, partial, moved
  wk[0].status = "done"; wk[1].status = "missed"; wk[2].status = "moved"; wk[3].status = "partial";
  assert.deepEqual(cardStatus(runPage(d).el), ["done", "missed", "moved", "partial", "rest", "next", ""]);
});

test("a run today on a free day explains yesterday's session as moved, like match.py", () => {
  const d = planData(), p = runPage(d, devScripts.map(f => read(`src/page/js/${f}`)));
  const day = s => p.ctx.decYear(s).day;
  const ctx = p.ctx.planContext(d.plan, day("2024-06-14"));   // today Fri, run that day
  assert.equal(ctx.status.get(day("2024-06-13")), "moved");
  assert.equal(ctx.status.get(day("2024-06-15")), "next");
});

test("a day without a session and no override reads Rest day in the detail; an override's reads Skipped", () => {
  const d = planData(), wk = d.plan.weeks[3].days;
  wk[3] = { ...wk[3], workout: null };
  wk[0] = { ...wk[0], workout: null, changed_by: "override_skip" };
  const { el } = runPage(d);
  assert.deepEqual(cardStatus(el).slice(0, 4), ["skipped", "done", "partial", "rest"]);
  clickCard(el, 3);
  assert.match(el("plan-detail").innerHTML, /<h3>Rest day<\/h3>/);
  clickCard(el, 0);
  assert.match(el("plan-detail").innerHTML, /<h3>Skipped<\/h3>[\s\S]*skipped/);
});

test("a plan whose weeks are all to come shows '–' KPIs", () => {
  const d = planData();
  d.runs = [planRun("2024-05-01", 5)];                         // today Thu 2024-05-02
  const { el, kpis } = runPage(d);
  assert.equal(kpis("plan-kpis"), 3);
  assert.equal(el("plan-kpis").innerHTML.split('<span class="val">–</span>').length - 1, 3, el("plan-kpis").innerHTML);
  assert.doesNotMatch(el("plan-kpis").innerHTML, /NaN|Infinity/);
  assert.match(el("plan-week-h").textContent, /^Week of /);
});

test("loading data without a plan drops the old plan chart", () => {
  const { ctx, destroyed } = runPage(planData(), devScripts.map(f => read(`src/page/js/${f}`)));
  assert.ok(vm.runInContext('charts["c-plan"]', ctx), "no c-plan chart to start with");
  ctx.setData(oldFormatData(), false);
  assert.equal(vm.runInContext('"c-plan" in charts', ctx), false, "c-plan left in charts");
  assert.ok(destroyed.includes("c-plan"), "c-plan not destroyed");
});
