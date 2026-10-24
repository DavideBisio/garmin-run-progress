"use strict";
/* ---------------- state ---------------- */
let DATA = null, RUNS = [], RHR = [], PLAN = null;
// fromUser: a file the user just loaded, which opens Analysis (not the example data or a restore)
function setData(payload, isExample, fromUser){
  DATA = payload;
  RUNS = (payload.runs||[]).map(r=>prepare({...r})).filter(Boolean).sort((a,b)=>a._x-b._x);
  RHR = (Array.isArray(payload.rhr) ? payload.rhr : []).map(([ds,v])=>{ const p=decYear(ds); return p && v>0 ? {x:p.x, y:p.y, day:p.day, v} : null; })
    .filter(Boolean).sort((a,b)=>a.day-b.day);
  // runs.json's copy of plan.json (docs/plan-json-format.md), shown in Planning; anything else: no plan
  const pl = payload.plan;
  PLAN = pl && typeof pl==="object" && !Array.isArray(pl) && Array.isArray(pl.weeks) ? pl : null;
  const yrs = RUNS.length ? `${RUNS[0]._y}–${RUNS[RUNS.length-1]._y}` : "";
  $("status").classList.toggle("real", !isExample);
  $("status-t").textContent = isExample ? "Example data ·" : `Your data · ${nf.format(RUNS.length)} runs · ${yrs}`;
  $("status-load").hidden = !isExample;
  $("clear").hidden = isExample;
  suggestBand();
  suggestLimits();
  render();
  if (fromUser) showTab("analysis", true);
}
function suggestLimits(){
  const peaks = RUNS.map(r=>r._hrPeak || r.maxHr || 0).filter(v=>v>120 && v<230).sort((a,b)=>b-a);
  const max = peaks.length ? Math.round(peaks[Math.min(1, peaks.length-1)]) : 190;
  const lastR = RHR.length ? RHR[RHR.length-1].day : 0;
  const restMed = median(RHR.filter(p=>p.day>lastR-365).map(p=>p.v));
  const rest = restMed ? Math.round(restMed) : 50;
  $("hr-max").value = max; $("hr-rest").value = rest;
  $("lim-hint").textContent = `Filled in from your data: ${peaks.length ? `${max} bpm is the second-highest sustained heart rate in any run` : "no heart rate found, so 190 bpm is a placeholder"}; ${restMed ? `${rest} bpm is your median resting heart rate over the last year` : "no resting heart rate in this file, so 50 bpm is a placeholder"}. Both move the zone boundaries; change them if you know better values.`;
}
function suggestBand(){
  const hrs = RUNS.filter(r=>r._hrOk).map(r=>{ const h=r.hr.filter(x=>x>0).sort((a,b)=>a-b); return h[h.length>>1]; });
  if (!hrs.length){ $("band-hint").textContent = "No heart-rate data found, so the efficiency chart stays empty."; return; }
  const sorted=[...hrs].sort((a,b)=>a-b), q=p=>sorted[Math.floor(p*(sorted.length-1))];
  const easy = q(0.35);
  $("band-hint").textContent = `Your easy runs typically sit around ${easy} bpm (median of all runs ${q(0.5)} bpm). A 10 bpm band around your easy heart rate works well.`;
}
