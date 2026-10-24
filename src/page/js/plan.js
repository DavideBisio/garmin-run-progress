"use strict";
/* ---------------- plan (Planning tab: runs.json's plan, read-only; docs/features/plan-view.md) ---------------- */
// The page files share one scope: every top-level name here starts with plan/PLAN_.
const PLAN_ZONES = {E:"Easy", M:"Marathon", T:"Threshold", I:"Interval", R:"Repetition"};   // render_md.py
const PLAN_PHASES = {base:"Base", rt:"R + T", it:"I + T", tm:"T + M", taper:"Taper"};
const PLAN_WDAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const PLAN_STATUS = {done:"done", partial:"partial", missed:"missed", moved:"moved a day", swapped:"swapped terrain",
  skipped:"skipped", next:"next", rest:"rest"};
const PLAN_PARTIAL = 0.70;          // rules.toml [adapt] partial: under 70 % of both distance and time
const PLAN_RACES = {5000:"5 km", 10000:"10 km", 21097.5:"Half marathon", 42195:"Marathon"};
let planCells = [], planSel = null;  // this week's 7 days ({day, entry, status}); the date opened in the detail

const planEsc = s => String(s ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[ch]);
const planDayIdx = ds => decYear(ds)?.day ?? null;          // a local YYYY-MM-DD as the page's day index
const planDate = (day, o) => new Date(day*864e5).toLocaleDateString(undefined, {...o, timeZone:"UTC"});
// the runner's today as a day index: the local calendar day (never UTC parsing); for the example data
// the day after its last run, so its plan stays current
function planToday(){
  if (DATA?.example && RUNS.length) return RUNS[RUNS.length-1]._day + 1;
  const n = new Date();
  return Math.round(Date.UTC(n.getFullYear(), n.getMonth(), n.getDate())/864e5);
}
// render_md.py's fmt_pace, fmt_dur, fmt_dist
const planPace = s => { s = Math.floor(s+0.5); return `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`; };
function planDur(s){
  s = Math.floor(s+0.5);
  if (s < 60) return `${s} s`;
  if (s < 600) return planPace(s);
  const m = Math.floor(s/60+0.5);
  return m < 60 ? `${m} min` : `${Math.floor(m/60)} h ${String(m%60).padStart(2,"0")}`;
}
const planDist = m => { m = Math.floor(m+0.5); return m < 1000 ? `${m} m` : `${(m/1000).toFixed(1)} km`; };
const planMin = s => Math.floor(s/60+0.5);                   // plan_io.shown_min
const planSize = (w, unit) => unit==="min" ? `${planMin(w.seconds)} min · ~${(+w.km).toFixed(1)} km` : `${(+w.km).toFixed(1)} km · ~${planDur(w.seconds)}`;
const planZoneNo = s => +(/^Z(\d)/.exec(s?.hr_zone || "")||[])[1] || 0;

// every step of a workout in order, repeats opened
const planSteps = w => (w?.steps||[]).flatMap(p => p.type==="repeat" ? (p.steps||[]) : [p]);
// the step a card shows: the first rep, else the longest step that isn't warmup or cooldown
function planMain(w){
  const st = planSteps(w);
  return st.find(s => s.role==="rep") || [...st].sort((a,b)=>(b.seconds||0)-(a.seconds||0)).find(s=>!/warmup|cooldown/.test(s.role)) || st[0] || null;
}
function planHrChip(s, long){
  if (!s?.hr) return "";
  const z = planZoneNo(s), txt = long ? `Zone ${String(s.hr_zone).slice(1)} ${s.hr[0]}–${s.hr[1]} bpm` : `${s.hr_zone} ${s.hr[0]}–${s.hr[1]}`;
  return `<span class="pz"${z ? ` style="--c:var(--z${z})"` : ""}>${planEsc(txt)}</span>`;
}
function planPaceCell(s){                                    // render_md._pace_cell
  if (s.pace_s_per_km) return `${PLAN_ZONES[s.zone] || s.zone} ${planPace(s.pace_s_per_km[0])}–${planPace(s.pace_s_per_km[1])} /km`;
  return s.zone==="jog" ? "Jog" : s.effort || "Open";
}
function planDurCell(s){                                     // render_md._duration_cell
  if (s.end==="dist") return `${planDist(s.meters)} (~${planDur(s.seconds)})`;
  if (s.end==="time") return `${planDur(s.value)} (~${planDist(s.meters)})`;
  return `Lap button (~${planDur(s.seconds)}, ~${planDist(s.meters)})`;
}
const planRow = (s, nested, note) => `<tr><td>${nested ? "↳ " : ""}<b>${planEsc(s.label)}</b></td><td>${planEsc(planPaceCell(s))}</td>`
  + `<td>${planHrChip(s, true)}</td><td>${planEsc(planDurCell(s))}</td><td>${planEsc(note ?? s.note)}</td></tr>`;
// the step table of plan.md (render_md.render_workout): a repeat of 1 is just its steps
function planTable(w){
  let h = "";
  for (const p of w.steps||[]){
    if (p.type!=="repeat"){ h += planRow(p); continue; }
    const st = p.steps||[], last = st[st.length-1];
    if (p.n===1){
      const steps = p.skip_last_rest && last?.role==="recovery" ? st.slice(0,-1) : st;
      const first = [p.note, steps[0]?.note].filter(Boolean).join("; ");
      steps.forEach((s,i) => { h += planRow(s, false, i===0 ? first : undefined); });
      continue;
    }
    const note = [p.note, p.skip_last_rest && last?.role==="recovery" ? "no recovery after the last rep" : ""].filter(Boolean).join("; ");
    h += `<tr><td><b>Repeat ${+p.n || 0}x</b></td><td></td><td></td><td>${planEsc(`${planDist(p.meters)} (~${planDur(p.seconds)})`)}</td><td>${planEsc(note)}</td></tr>`;
    h += st.map(s => planRow(s, true)).join("");
  }
  return `<div class="tbl-wrap"><table class="plan-steps"><thead><tr><th>Lap</th><th>Pace range</th><th>HR</th><th>Duration</th><th>Comment</th></tr></thead><tbody>${h}</tbody></table></div>`;
}

// What the page knows of each plan day: runs by day, plan days by day, and each day's status: the
// stored one (09's match), else matched by date like match.py (same day: done or partial; none,
// but a run on a free day before or after, today's included: moved; else missed). Future days: "next" for the first.
function planContext(plan, today){
  const runs = new Map();
  for (const r of RUNS){ const x = runs.get(r._day) || {km:0, s:0}; x.km += r._km||0; x.s += r.moving || r.dur || 0; runs.set(r._day, x); }
  const days = new Map(), weeks = [];
  for (const wk of plan.weeks){
    const ws = planDayIdx(wk?.start);
    if (ws==null || !Array.isArray(wk.days)) continue;
    weeks.push({wk, w:weekOf(ws), start:ws});
    for (const e of wk.days){ const d = planDayIdx(e?.date); if (d!=null && !days.has(d)) days.set(d, e); }
  }
  weeks.sort((a,b)=>a.start-b.start);
  const status = new Map(), claimed = new Set();
  let next = null;
  for (const d of [...days.keys()].sort((a,b)=>a-b)){
    const e = days.get(d), w = e.workout, run = runs.get(d);
    let st = null;
    if (!w) st = e.changed_by ? "skipped" : "rest";
    else if (PLAN_STATUS[e.status] && e.status!=="next" && e.status!=="rest") st = e.status;
    else if (run && d <= today)
      st = run.km < PLAN_PARTIAL*(w.km||0) && run.s < PLAN_PARTIAL*(w.seconds||0) ? "partial" : "done";
    else if (d < today){
      const free = [d-1, d+1].find(x => x <= today && runs.has(x) && !days.get(x)?.workout && !claimed.has(x));
      if (free!=null){ claimed.add(free); st = "moved"; } else st = "missed";
    } else if (next==null){ next = d; st = "next"; }
    status.set(d, st);
  }
  return {runs, days, weeks, status, today};
}
// block N, week M: blocks start at progress.block_start and after each deload week
function planBlock(plan, weeks, i){
  const {wk, w} = weeks[i];
  if (!wk.phase) return "";
  const phase = PLAN_PHASES[wk.phase] || wk.phase, dl = wk.deload ? ", deload" : "";
  if (wk.phase==="taper"){
    let n = 1; for (let j=i-1; j>=0 && weeks[j].wk.phase==="taper"; j--) n++;
    return ` (taper, week ${n}${dl})`;
  }
  const bs = planDayIdx(plan.progress?.block_start), anchor = bs!=null && weekOf(bs) <= w ? weekOf(bs) : weeks[0].w;
  let block = 1, from = anchor;
  for (const x of weeks) if (x.w >= anchor && x.w < w && x.wk.deload){ block++; from = x.w+1; }
  return ` (block ${block}, week ${w-from+1} · ${phase}${dl})`;
}

function planHeader(plan, ctx){
  const lv = plan.levels, prof = plan.profile, out = [];
  const cap = s => s ? s[0].toUpperCase()+s.slice(1) : "";
  if (lv?.volume && lv?.quality) out.push(`${cap(planEsc(lv.volume))} volume · ${planEsc(lv.quality)} quality`);
  const v = typeof prof?.vdot==="number" ? prof.vdot : plan.progress?.vdot?.value;
  if (typeof v==="number") out.push(`VDOT ${Math.round(v*10)/10}`);
  const race = prof?.race, rd = planDayIdx(race?.date);
  if (race && rd!=null){
    const m = +race.distance_m, name = PLAN_RACES[m] || `${nf.format(m/1000)} km race`;
    const wks = weekOf(rd) - weekOf(ctx.today);
    const goal = race.goal_s ? `, goal ${fmtTime(race.goal_s)}` : "";
    out.push(rd < ctx.today ? `${name} on ${planDate(rd, {day:"numeric", month:"short", year:"numeric"})} (past)`
      : `${name} in ${wks} wk${goal}`);
  }
  return out.join(" · ") || "Training plan";
}

function renderPlan(c){
  const plan = PLAN;
  $("plan-empty").hidden = !!plan; $("plan-view").hidden = !plan;
  planCells = [];
  if (!plan){ if (charts["c-plan"]){ charts["c-plan"].destroy(); delete charts["c-plan"]; } return; }
  const ctx = planContext(plan, planToday());
  $("plan-head").innerHTML = planHeader(plan, ctx);
  const hm = +$("hr-max").value || 190, hr = Math.min(+$("hr-rest").value || 50, hm-20), pp = plan.profile;
  const differs = pp && typeof pp.hr_max==="number" && typeof pp.hr_rest==="number" && (pp.hr_max!==hm || pp.hr_rest!==hr);
  $("plan-note").hidden = !differs;
  $("plan-note").textContent = differs ? `The plan's heart-rate targets come from max ${pp.hr_max} / resting ${pp.hr_rest} bpm (profile.toml); the Data tab uses ${hm} / ${hr} bpm. The targets below are the plan's, as pushed to your watch.` : "";

  // this week: the one holding today, else the first to come, else the last
  const tw = weekOf(ctx.today), W = ctx.weeks;
  planKpis(ctx, tw);
  planChart(c, ctx, tw);
  let i = W.findIndex(x => x.w===tw);
  if (i < 0) i = W.findIndex(x => x.w > tw);
  if (i < 0) i = W.length-1;
  const warns = [...(Array.isArray(plan.warnings) ? plan.warnings : []), ...(i>=0 && Array.isArray(W[i].wk.warnings) ? W[i].wk.warnings : [])];
  $("plan-warn").innerHTML = warns.filter(x=>x && typeof x==="object").map(x => `<li><b>${planEsc(x.rule)}</b>: ${planEsc(x.detail)}${x.action ? `. Planner: ${planEsc(x.action)}.` : ""}</li>`).join("");
  $("plan-warn").hidden = !warns.length;
  if (i < 0){ $("plan-week-h").textContent = "No weeks in this plan"; $("plan-days").innerHTML = ""; $("plan-detail").hidden = true; return; }
  const {wk, w, start} = W[i];
  $("plan-week-h").textContent = (w===tw ? "This week" : `Week of ${planDate(start, {day:"numeric", month:"short"})}`) + planBlock(plan, W, i);
  const unit = wk.unit;
  let h = "";
  for (let k=0; k<7; k++){
    const day = start+k, e = ctx.days.get(day), wo = e?.workout, st = e ? ctx.status.get(day) : "rest";
    planCells.push({day, entry:e || null, status:st, unit});
    const main = planMain(wo);
    const pace = main ? (main.pace_s_per_km ? `${main.zone} ${planPace(main.pace_s_per_km[0])}–${planPace(main.pace_s_per_km[1])} /km` : main.zone==="jog" ? "Jog" : main.effort || "") : "";
    const title = wo ? wo.title : st==="skipped" ? "Skipped" : "Rest";
    h += `<button type="button" class="pday${wo ? "" : " rest"}${day===ctx.today ? " today" : ""}" data-i="${k}" aria-controls="plan-detail">`
      + `<span class="pd-h"><span>${PLAN_WDAYS[k]} ${planDate(day, {day:"numeric"})}</span>${st && st!=="rest" || !wo ? `<span class="pst ${st}">${PLAN_STATUS[st]}</span>` : ""}</span>`
      + `<span class="pd-t">${planEsc(title)}</span>`
      + (wo ? `<span class="pd-s">${planSize(wo, unit)}</span>` : "")
      + (pace ? `<span class="pd-s">${planEsc(pace)}</span>` : "")
      + (main?.hr ? `<span class="pd-s">${planHrChip(main)}</span>` : "")
      + `</button>`;
  }
  $("plan-days").innerHTML = h;
  const sel = planCells.findIndex(x => x.day===planSel);
  if (sel >= 0) planShow(sel); else { planSel = null; $("plan-detail").hidden = true; $("plan-detail").innerHTML = ""; }
}

// km run in each week, by week index
function planWeekKm(ctx){
  const km = new Map();
  for (const [d, x] of ctx.runs) km.set(weekOf(d), (km.get(weekOf(d))||0) + x.km);
  return km;
}
const planR1 = x => Math.round(x*10)/10;
// compliance over the last 4 complete weeks before this one: sessions done (moved and swapped
// count), km run against the weeks' targets, Q sessions done
function planKpis(ctx, tw){
  const weeks = ctx.weeks.filter(x => x.w >= tw-4 && x.w < tw), km = planWeekKm(ctx);
  let n = 0, ok = 0, q = 0, qOk = 0, kmRun = 0, kmPlan = 0;
  for (const {wk, w, start} of weeks){
    kmPlan += +wk.target_km || 0; kmRun += km.get(w) || 0;
    for (const [d, e] of ctx.days){
      if (d < start || d > start+6 || !e.workout) continue;
      const good = ["done","moved","swapped"].includes(ctx.status.get(d));
      n++; ok += good;
      if (e.slot==="Q"){ q++; qOk += good; }
    }
  }
  const pct = (a, b) => b ? Math.round(a/b*100)+"%" : "–";
  const none = "No plan weeks in the last 4 weeks yet";
  const kpi = (lab, val, sub) => `<div class="kpi"><span class="lab">${lab}</span><span class="val">${val}</span><span class="sub">${sub}</span></div>`;
  $("plan-kpis").innerHTML = [
    kpi("Sessions done, 4 weeks", pct(ok, n), weeks.length ? `${ok} of ${n} sessions (moved and swapped count, partial doesn't)` : none),
    kpi("Km done, 4 weeks", pct(kmRun, kmPlan), weeks.length ? `${nf.format(kmRun)} of ${nf.format(kmPlan)} km planned` : none),
    kpi("Quality done, 4 weeks", q ? `${qOk}/${q}` : "–", weeks.length ? (q ? "Q sessions done" : "no Q sessions planned") : none),
  ].join("");
}
// planned against actual km per plan week, over shaded phase bands; deload weeks lighter and marked ↓
function planChart(c, ctx, tw){
  const W = ctx.weeks, km = planWeekKm(ctx);
  const labels = W.map(x => planDate(x.start, {day:"numeric", month:"short"}) + (x.wk.deload ? " ↓" : ""));
  const runs = [];                                             // [first, last, phase] of each phase band
  W.forEach((x, i) => { const ph = x.wk.phase || ""; const r = runs[runs.length-1];
    if (r && r[2]===ph) r[1] = i; else runs.push([i, i, ph]); });
  const bands = {id:"planPhases", beforeDatasetsDraw(ch){
    const {ctx:g, chartArea:a, scales:{x}} = ch;
    if (!a || !x || W.length < 1) return;
    const step = W.length > 1 ? x.getPixelForValue(1) - x.getPixelForValue(0) : a.right - a.left;
    g.save();
    runs.forEach(([i, j, ph], k) => {
      if (!ph) return;
      const l = Math.max(a.left, x.getPixelForValue(i) - step/2), r = Math.min(a.right, x.getPixelForValue(j) + step/2);
      g.globalAlpha = k%2 ? .05 : .11; g.fillStyle = c.muted; g.fillRect(l, a.top, r-l, a.bottom-a.top);
      g.globalAlpha = 1; g.fillStyle = c.muted; g.font = `12px ${c.mono}`; g.textAlign = "left"; g.textBaseline = "top";
      g.fillText(PLAN_PHASES[ph] || ph, l+4, a.top+4);
    });
    g.restore();
  }};
  const o = baseOpts(c);
  o.scales.x = {...o.scales.x, ticks:{...o.scales.x.ticks, maxRotation:0, autoSkip:true, maxTicksLimit:9}};
  o.scales.y = {...o.scales.y, beginAtZero:true, title:{display:true, text:"km", color:c.muted}};
  o.layout = {padding:{top:18}};
  o.interaction = {mode:"index", intersect:false};
  o.plugins.tooltip.callbacks = {
    title: items => { const x = items.length && W[items[0].dataIndex]; return x ? `Week of ${planDate(x.start, {day:"numeric", month:"short", year:"numeric"})}`
      + (x.wk.phase ? ` · ${PLAN_PHASES[x.wk.phase] || x.wk.phase}` : "") + (x.wk.deload ? ", deload" : "") : ""; },
    label: ctx2 => `${ctx2.dataset.label}: ${nf.format(ctx2.parsed.y)} km`};
  chart("c-plan", {type:"bar", data:{labels, datasets:[
    {label:"Planned", data:W.map(x => planR1(+x.wk.target_km || 0)), backgroundColor:W.map(x => alpha(c.a2, x.wk.deload ? .22 : .5)), borderRadius:3},
    {label:"Actual", data:W.map(x => x.w <= tw ? planR1(km.get(x.w) || 0) : null), backgroundColor:alpha(c.a1, .85), borderRadius:3},
  ]}, options:o, plugins:[bands]});
}

// a day card's session detail: the step table of plan.md
function planShow(k){
  const cell = planCells[k];
  if (!cell) return;
  planSel = cell.day;
  const e = cell.entry, w = e?.workout, when = `${PLAN_WDAYS[k]} ${planDate(cell.day, {day:"numeric", month:"short", year:"numeric"})}`;
  const st = cell.status && cell.status!=="rest" ? ` · ${PLAN_STATUS[cell.status]}` : "";
  const ch = e?.change && typeof e.change==="object" ? `<p class="muted small-t">Changed: ${planEsc(e.change.from)} → ${planEsc(e.change.to)}${e.change.reason ? `: ${planEsc(e.change.reason)}` : ""}</p>` : "";
  $("plan-detail").innerHTML = w
    ? `<h3>${planEsc(w.title)}</h3><p class="muted small-t">${when} · ${planSize(w, cell.unit)}${st}</p>${ch}${planTable(w)}`
    : `<h3>${cell.status==="skipped" ? "Skipped" : "Rest day"}</h3><p class="muted small-t">${when}${e ? st : ""}</p>${ch}`;
  $("plan-detail").hidden = false;
}
$("plan-days").addEventListener("click", ev => {
  const b = ev.target?.closest?.("[data-i]");
  if (b) planShow(+b.getAttribute("data-i"));
});
