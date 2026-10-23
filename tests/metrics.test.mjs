// Parity vectors: the page's metrics.js must still give the numbers in tests/fixtures/metric_vectors.json,
// which tests/test_plan.py checks garmin_plan.metrics against. node --test tests/metrics.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const ROOT = path.resolve(import.meta.dirname, "..");
// the build inlines src/page/js/metrics.js verbatim; in dist/ its functions sit inside the page IIFE
const src = fs.readFileSync(path.join(ROOT, "src/page/js/metrics.js"), "utf8");
const V = JSON.parse(fs.readFileSync(path.join(ROOT, "tests/fixtures/metric_vectors.json"), "utf8"));

const ctx = { Math, Float32Array };
vm.createContext(ctx);
// const bindings (gapFactor, weekOf, DISTS) are not context properties: return them from the script
const M = vm.runInContext(src + "\n;({vdot, gapFactor, trimp, hrrZones, weekOf, bestEffort, prepare, decYear})", ctx);

test("vdot", () => { for (const [m, s, want] of V.vdot) assert.equal(M.vdot(m, s), want, `${m} m in ${s} s`); });

test("gapFactor, clamped at ±0.3", () => { for (const [g, want] of V.gapFactor) assert.equal(M.gapFactor(g), want, `grade ${g}`); });

test("hrrZones", () => {
  for (const [max, rest, want] of V.hrrZones) assert.deepEqual(Array.from(M.hrrZones(max, rest)), want, `${max}/${rest}`);
});

test("weekOf and day index", () => {
  for (const [day, want] of V.weekOf) assert.equal(M.weekOf(day), want, `day ${day}`);
  for (const [s, want] of V.day) assert.equal(M.decYear(s).day, want, s);
});

test("bestEffort", () => {
  for (const { t, d, D, expected } of V.bestEffort) assert.equal(M.bestEffort(t, d, D), expected, `D=${D}`);
});

test("trimp, stream and average-HR paths", () => {
  for (const { run, max, rest, expected } of V.trimp) {
    const r = M.prepare(structuredClone(run));
    assert.equal(M.trimp(r, max, rest), expected, `${run.date} ${max}/${rest}`);
  }
});
