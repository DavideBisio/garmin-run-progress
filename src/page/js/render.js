"use strict";
/* ---------------- render ---------------- */
["hr-lo","hr-hi","season","no-trail","hr-max","hr-rest"].forEach(id=>$(id).addEventListener("change", render));
const charts = {};
function tok(n){ return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function chart(id, cfg){ if (charts[id]) charts[id].destroy(); if (!window.Chart) return; charts[id] = new Chart($(id), cfg); }
function baseOpts(c){
  return { responsive:true, maintainAspectRatio:false, animation:false, interaction:{mode:"nearest",intersect:false},
    plugins:{legend:{display:false}, tooltip:{backgroundColor:c.surface, titleColor:c.ink, bodyColor:c.ink, borderColor:c.line, borderWidth:1}},
    scales:{ x:{grid:{color:c.grid}, ticks:{color:c.muted, font:{family:c.mono}}, border:{color:c.line}},
             y:{grid:{color:c.grid}, ticks:{color:c.muted, font:{family:c.mono}}, border:{color:c.line}} } };
}
function alpha(hex, a){ const m=/^#([0-9a-f]{6})$/i.exec(hex); if(!m) return hex; const n=parseInt(m[1],16); return `rgba(${n>>16},${(n>>8)&255},${n&255},${a})`; }

function render(){
  let lo=+$("hr-lo").value, hi=+$("hr-hi").value; if (hi<lo) [lo,hi]=[hi,lo];
  const season=$("season").value, months = season==="all"?null:new Set(season.split(",").map(Number));
  const noTrail=$("no-trail").checked;
  const runs = RUNS.filter(r => (!months || months.has(r._m)) && !(noTrail && r._trail));
  const c = {a1:tok("--accent-1"),a2:tok("--accent-2"),a3:tok("--accent-3"),ink:tok("--ink"),muted:tok("--muted"),line:tok("--line"),surface:tok("--surface"),mono:tok("--f-mono"),grid:alpha(tok("--line"),.6)};

  // per-year aggregates
  const years = {};
  const effPts = [];
  for (const r of runs){
    const Y = years[r._y] ||= {y:r._y, n:0, km:0, eff:[], best:{}, vo2:[], dec:[], cad:[], stride:[]};
    Y.n++; Y.km += r._km||0;
    if (r.vo2) Y.vo2.push(r.vo2);
    if (r._dec != null) Y.dec.push(r._dec);
    if (r.cad > 100) Y.cad.push(r.cad);
    if (r.stride > 0) Y.stride.push(r.stride/100);
    const p = bandPace(r, lo, hi);
    if (p){ Y.eff.push(p); effPts.push({x:r._x, y:p}); }
    for (const D of DISTS){ const b=r._best[D.k]; if (b && (!Y.best[D.k] || b<Y.best[D.k])) Y.best[D.k]=b; }
  }
  const ys = Object.values(years).sort((a,b)=>a.y-b.y);
  const rhrYear = {}; for (const p of RHR) (rhrYear[p.y] ||= []).push(p.v);
  ys.forEach(Y=>{ Y.effMed = Y.eff.length>=5 ? median(Y.eff) : null; Y.vo2Med = median(Y.vo2);
    Y.decMed = Y.dec.length>=3 ? median(Y.dec) : null; Y.cadMed = median(Y.cad); Y.strideMed = median(Y.stride);
    Y.rhrMed = median(rhrYear[Y.y] || []);
    Y.vdot = {}; for (const D of DISTS) if (Y.best[D.k]) Y.vdot[D.k] = vdot(D.m, Y.best[D.k]);
    const v = Object.entries(Y.vdot).filter(([k])=>k!=="1k").map(([,v])=>v); Y.vdotMax = v.length?Math.max(...v):null; });

  // KPIs
  const effYears = ys.filter(Y=>Y.effMed!=null);
  const slope = effYears.length>=2 ? theilSen(effYears.map(Y=>[Y.y, Y.effMed])) : null;
  const first = effYears[0], last = effYears[effYears.length-1];
  const vYears = ys.filter(Y=>Y.vdotMax);
  const vFirst = vYears[0], vPeak = vYears.reduce((a,b)=>!a||b.vdotMax>a.vdotMax?b:a, null), vLast = vYears[vYears.length-1];
  const totKm = ys.reduce((s,Y)=>s+Y.km,0);
  const chip = (v, goodWhenNeg, txt) => v==null?"":`<span class="chip ${ (goodWhenNeg? v<0 : v>0) ? "good":"bad"}">${txt}</span>`;
  const k = [];
  k.push(`<div class="kpi"><span class="lab">Trend at ${lo}–${hi} bpm</span><span class="val">${slope==null?"–":(slope<0?"−":"+")+Math.abs(slope).toFixed(1)+" s/km"}</span><span class="sub">${slope==null?"Not enough heart-rate runs":"per year · "+(slope<0?"getting faster":"getting slower")+" at the same effort"}</span></div>`);
  k.push(`<div class="kpi"><span class="lab">Pace at same HR</span><span class="val">${first?fmtPace(first.effMed):"–"} → ${last?fmtPace(last.effMed):"–"}</span><span class="sub">${first&&last?`/km, ${first.y} → ${last.y} `+chip(last.effMed-first.effMed,true,((last.effMed-first.effMed)<0?"−":"+")+Math.abs(Math.round(last.effMed-first.effMed))+" s"):"min/km, grade-adjusted"}</span></div>`);
  k.push(`<div class="kpi"><span class="lab">Best-effort VDOT</span><span class="val">${vFirst?vFirst.vdotMax.toFixed(1):"–"} → ${vLast?vLast.vdotMax.toFixed(1):"–"}</span><span class="sub">${vFirst&&vLast?`${vFirst.y} → ${vLast.y} · peak ${vPeak.vdotMax.toFixed(1)} in ${vPeak.y}`:"needs GPS tracks"}</span></div>`);
  k.push(`<div class="kpi"><span class="lab">Volume</span><span class="val">${nf.format(totKm)} km</span><span class="sub">${nf.format(runs.length)} runs over ${ys.length} years</span></div>`);
  const lastDay = RUNS.length ? RUNS[RUNS.length-1]._day : 0;
  const decIn = (a,b) => runs.filter(r=>r._dec!=null && r._day>a && r._day<=b).map(r=>r._dec);
  const decNow = decIn(lastDay-365, lastDay), decPrev = decIn(lastDay-730, lastDay-365);
  const dNow = median(decNow), dPrev = median(decPrev);
  k.push(`<div class="kpi"><span class="lab">Aerobic decoupling</span><span class="val">${dNow==null?"–":dNow.toFixed(1)+"%"}</span><span class="sub">${dNow==null?"No steady 50-minute runs with heart rate in the last 12 months":`median of ${decNow.length} steady runs, last 12 months `+(dPrev==null?"":chip(dNow-dPrev,true,`${dPrev.toFixed(1)}% the year before`))}</span></div>`);
  const rLast = RHR.length ? RHR[RHR.length-1].day : 0;
  const rhrIn = (a,b) => median(RHR.filter(p=>p.day>a && p.day<=b).map(p=>p.v));
  const rNow = rhrIn(rLast-30, rLast), rPrev = rhrIn(rLast-395, rLast-365);
  if (RHR.length) k.push(`<div class="kpi"><span class="lab">Resting heart rate</span><span class="val">${rNow==null?"–":Math.round(rNow)+" bpm"}</span><span class="sub">median of the last 30 days ${rPrev==null?"":chip(rNow-rPrev,true,`${rNow-rPrev<0?"−":"+"}${Math.abs(Math.round(rNow-rPrev))} bpm vs a year ago`)}</span></div>`);
  $("kpis").innerHTML = k.join("");

  // efficiency chart
  const xTicks = {stepSize:1, callback:v=>Number.isInteger(v)?v:""};
  const xMin = ys.length?ys[0].y:2016, xMax = ys.length?ys[ys.length-1].y+1:2026;
  let o = baseOpts(c);
  o.scales.x = {...o.scales.x, type:"linear", min:xMin, max:xMax, ticks:{...o.scales.x.ticks, ...xTicks}};
  o.scales.y = {...o.scales.y, reverse:true, ticks:{...o.scales.y.ticks, callback:v=>fmtPace(v)}, title:{display:true,text:"min/km",color:c.muted}};
  o.plugins.tooltip.callbacks = {label:ctx=>`${ctx.dataset.label}: ${fmtPace(ctx.parsed.y)} /km`, title:items=>items.length?String(Math.floor(items[0].parsed.x)):""};
  chart("c-eff", {type:"scatter", data:{datasets:[
    {label:"Run", data:effPts, pointRadius:2.2, pointHoverRadius:4, backgroundColor:alpha(c.a1,.28), borderColor:"transparent"},
    {label:"Yearly median", type:"line", data:effYears.map(Y=>({x:Y.y+.5,y:Y.effMed})), borderColor:c.ink, backgroundColor:c.ink, borderWidth:2.5, pointRadius:4, tension:.25}
  ]}, options:o});

  // VDOT chart
  o = baseOpts(c);
  o.scales.y.title = {display:true,text:"VDOT",color:c.muted};
  o.plugins.tooltip.callbacks = {label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} (${fmtTime(ctx.dataset.times[ctx.dataIndex])})`};
  const lab = ys.map(Y=>String(Y.y));
  const ds = [["5k","5 km",c.a1],["10k","10 km",c.a2],["hm","Half",c.a3]].map(([kk,l,col])=>({label:l, data:ys.map(Y=>Y.vdot[kk]??null), times:ys.map(Y=>Y.best[kk]), borderColor:col, backgroundColor:col, spanGaps:true, pointRadius:3.5, borderWidth:2, tension:.2}));
  chart("c-vdot", {type:"line", data:{labels:lab, datasets:ds}, options:o});

  // volume
  o = baseOpts(c);
  o.scales.y.title = {display:true,text:"km",color:c.muted};
  o.plugins.tooltip.callbacks = {label:ctx=>`${nf.format(ctx.parsed.y)} km`};
  chart("c-vol", {type:"bar", data:{labels:lab, datasets:[{data:ys.map(Y=>Math.round(Y.km)), backgroundColor:alpha(c.a1,.75), borderRadius:3}]}, options:o});

  // VO2max
  const vo2Pts = runs.filter(r=>r.vo2).map(r=>({x:r._x,y:r.vo2}));
  $("vo2-panel").hidden = !vo2Pts.length;
  if (vo2Pts.length){
    o = baseOpts(c);
    o.scales.x = {...o.scales.x, type:"linear", min:xMin, max:xMax, ticks:{...o.scales.x.ticks, ...xTicks}};
    o.scales.y.title = {display:true,text:"ml/kg/min",color:c.muted};
    o.plugins.tooltip.callbacks = {label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y.toFixed(0)}`, title:items=>items.length?String(Math.floor(items[0].parsed.x)):""};
    chart("c-vo2", {type:"scatter", data:{datasets:[
      {label:"Run", data:vo2Pts, pointRadius:2, backgroundColor:alpha(c.a2,.35), borderColor:"transparent"},
      {label:"Yearly median", type:"line", data:ys.filter(Y=>Y.vo2Med).map(Y=>({x:Y.y+.5,y:Y.vo2Med})), borderColor:c.ink, backgroundColor:c.ink, borderWidth:2.5, pointRadius:4, tension:.25}
    ]}, options:o});
  }

  // resting HR: daily dots + 30-day rolling median
  $("rhr-panel").hidden = !RHR.length;
  if (RHR.length){
    const roll = []; let j = 0;
    for (let i=0;i<RHR.length;i++){ while (RHR[j].day <= RHR[i].day-30) j++; if (i-j >= 9) roll.push({x:RHR[i].x, y:median(RHR.slice(j,i+1).map(p=>p.v))}); }
    o = baseOpts(c);
    o.scales.x = {...o.scales.x, type:"linear", min:RHR[0].y, max:RHR[RHR.length-1].y+1, ticks:{...o.scales.x.ticks, ...xTicks}};
    o.scales.y.title = {display:true,text:"bpm",color:c.muted};
    o.plugins.tooltip.callbacks = {label:ctx=>`${ctx.dataset.label}: ${Math.round(ctx.parsed.y)} bpm`, title:items=>items.length?String(Math.floor(items[0].parsed.x)):""};
    chart("c-rhr", {type:"scatter", data:{datasets:[
      {label:"Day", data:RHR.map(p=>({x:p.x,y:p.v})), pointRadius:1.6, pointHoverRadius:4, backgroundColor:alpha(c.a3,.35), borderColor:"transparent"},
      {label:"30-day median", type:"line", data:roll, borderColor:c.ink, borderWidth:2, pointRadius:0, tension:.2}
    ]}, options:o});
  }

  // per-run trend charts: dots + yearly median
  const trend = (id, pts, med, col, yTitle, fmt, yOpts, extra) => {
    const o = baseOpts(c);
    o.scales.x = {...o.scales.x, type:"linear", min:xMin, max:xMax, ticks:{...o.scales.x.ticks, ...xTicks}};
    o.scales.y = {...o.scales.y, ...(yOpts||{}), ticks:{...o.scales.y.ticks, callback:v=>fmt(v)}, title:{display:true,text:yTitle,color:c.muted}};
    o.plugins.tooltip.callbacks = {label:ctx=>`${ctx.dataset.label}: ${fmt(ctx.parsed.y)}`, title:items=>items.length?String(Math.floor(items[0].parsed.x)):""};
    chart(id, {type:"scatter", data:{datasets:[
      {label:"Run", data:pts, pointRadius:2.2, pointHoverRadius:4, backgroundColor:alpha(col,.3), borderColor:"transparent"},
      {label:"Yearly median", type:"line", data:med, borderColor:c.ink, backgroundColor:c.ink, borderWidth:2.5, pointRadius:4, tension:.25},
      ...(extra||[])
    ]}, options:o});
  };
  const decPts = runs.filter(r=>r._dec!=null).map(r=>({x:r._x, y:Math.max(-10, Math.min(25, r._dec))}));
  $("dec-panel").hidden = !decPts.length;
  if (decPts.length) trend("c-dec", decPts, ys.filter(Y=>Y.decMed!=null).map(Y=>({x:Y.y+.5,y:Y.decMed})), c.a1, "% drift", v=>v.toFixed(0)+"%", {min:-10, max:25},
    [{label:"5% line", type:"line", data:[{x:xMin,y:5},{x:xMax,y:5}], borderColor:c.muted, borderDash:[5,4], borderWidth:1.5, pointRadius:0, pointHitRadius:0}]);
  const cadPts = runs.filter(r=>r.cad>100).map(r=>({x:r._x, y:r.cad}));
  $("cad-panel").hidden = !cadPts.length;
  if (cadPts.length) trend("c-cad", cadPts, ys.filter(Y=>Y.cadMed).map(Y=>({x:Y.y+.5,y:Y.cadMed})), c.a1, "steps/min", v=>v.toFixed(0));
  const stPts = runs.filter(r=>r.stride>0).map(r=>({x:r._x, y:r.stride/100}));
  $("stride-panel").hidden = !stPts.length;
  if (stPts.length) trend("c-stride", stPts, ys.filter(Y=>Y.strideMed).map(Y=>({x:Y.y+.5,y:Y.strideMed})), c.a3, "m per step", v=>v.toFixed(2));

  // Training Effect
  const teRuns = runs.filter(r=>r.te!=null);
  $("te-panel").hidden = !teRuns.length;
  if (teRuns.length){
    o = baseOpts(c);
    o.scales.x = {...o.scales.x, type:"linear", min:xMin, max:xMax, ticks:{...o.scales.x.ticks, ...xTicks}};
    o.scales.y = {...o.scales.y, min:0, max:5, title:{display:true,text:"Training Effect",color:c.muted}};
    o.plugins.tooltip.callbacks = {label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}`, title:items=>items.length?String(Math.floor(items[0].parsed.x)):""};
    const teMed = key => ys.map(Y=>{ const v=median(teRuns.filter(r=>r._y===Y.y && r[key]!=null).map(r=>r[key])); return v==null?null:{x:Y.y+.5,y:v}; }).filter(Boolean);
    chart("c-te", {type:"scatter", data:{datasets:[
      {label:"Aerobic", data:teRuns.map(r=>({x:r._x,y:r.te})), pointRadius:2.2, pointHoverRadius:4, backgroundColor:alpha(c.a1,.3), borderColor:"transparent"},
      {label:"Anaerobic", data:teRuns.filter(r=>r.teAn!=null).map(r=>({x:r._x,y:r.teAn})), pointRadius:2.2, pointHoverRadius:4, backgroundColor:alpha(c.a2,.35), borderColor:"transparent"},
      {label:"Aerobic, yearly median", type:"line", data:teMed("te"), borderColor:c.a1, backgroundColor:c.a1, borderWidth:2.5, pointRadius:4, tension:.25},
      {label:"Anaerobic, yearly median", type:"line", data:teMed("teAn"), borderColor:c.a2, backgroundColor:c.a2, borderWidth:2.5, pointRadius:4, tension:.25}
    ]}, options:o});
  }

  // table
  const bestOf = key => { let b=null; ys.forEach(Y=>{ const v=Y[key]; if (v!=null && (b==null || v<b)) b=v; }); return b; };
  const bestEff = bestOf("effMed");
  const best5 = Math.min(...ys.map(Y=>Y.best["5k"]||Infinity)), best10 = Math.min(...ys.map(Y=>Y.best["10k"]||Infinity));
  const bestV = Math.max(...ys.map(Y=>Y.vdotMax||0));
  let h = `<thead><tr><th>Year</th><th>Runs</th><th>km</th><th>Pace @ ${lo}–${hi}</th><th>Best 1 km</th><th>Best 5 km</th><th>Best 10 km</th><th>Best half</th><th>VDOT</th><th>Garmin VO2max</th><th>Decoupling</th><th>Cadence</th><th>Stride</th><th>Resting HR</th></tr></thead><tbody>`;
  for (const Y of [...ys].reverse()){
    h += `<tr><td>${Y.y}</td><td>${Y.n}</td><td>${nf.format(Y.km)}</td>
      <td class="${Y.effMed!=null&&Y.effMed===bestEff?"best":""}">${fmtPace(Y.effMed)}</td>
      <td>${fmtTime(Y.best["1k"])}</td>
      <td class="${Y.best["5k"]===best5?"best":""}">${fmtTime(Y.best["5k"])}</td>
      <td class="${Y.best["10k"]===best10?"best":""}">${fmtTime(Y.best["10k"])}</td>
      <td>${fmtTime(Y.best["hm"])}</td>
      <td class="${Y.vdotMax&&Y.vdotMax===bestV?"best":""}">${Y.vdotMax?Y.vdotMax.toFixed(1):"–"}</td>
      <td>${Y.vo2Med?Y.vo2Med.toFixed(0):"–"}</td>
      <td>${Y.decMed!=null?Y.decMed.toFixed(1)+"%":"–"}</td>
      <td>${Y.cadMed?Y.cadMed.toFixed(0):"–"}</td>
      <td>${Y.strideMed?Y.strideMed.toFixed(2)+" m":"–"}</td>
      <td>${Y.rhrMed?Math.round(Y.rhrMed):"–"}</td></tr>`;
  }
  $("tbl").innerHTML = h + "</tbody>";

  renderTraining(c);
  renderPlan(c);
}
