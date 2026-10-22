"use strict";
/* ---------------- training (all runs, last 52 weeks) ---------------- */
function renderTraining(c){
  const max = +$("hr-max").value || 190, rest = Math.min(+$("hr-rest").value || 50, max-20), zb = hrrZones(max, rest);
  const zr = [`Z1 &lt;${zb[0]}`, `Z2 ${zb[0]}–${zb[1]}`, `Z3 ${zb[1]}–${zb[2]}`, `Z4 ${zb[2]}–${zb[3]}`, `Z5 ${zb[3]}+`];
  $("zones-legend").innerHTML = zr.map((s,i)=>`<span style="--c:var(--z${i+1})">${s}</span>`).join("") + " bpm";
  $("zones-fallback").hidden = true;
  if (!RUNS.length){ $("kpis2").innerHTML = ""; return; }
  const lastDay = RUNS[RUNS.length-1]._day, lastWeek = weekOf(lastDay), W = 52, firstWeek = lastWeek-W+1;
  const fmtDay = day => new Date(day*864e5).toLocaleDateString(undefined, {day:"numeric", month:"short", year:"numeric", timeZone:"UTC"});
  $("tr-end").textContent = ` (${fmtDay(lastDay)})`;

  // daily load and per-week buckets for every run
  const daily = new Map(), allWeeks = new Map(); let nFb = 0;
  const weeks = Array.from({length:W}, (_,i)=>({w:firstWeek+i, km:0, long:0, n:0, load:0, z:[0,0,0,0,0]}));
  for (const r of RUNS){
    const load = trimp(r, max, rest);
    daily.set(r._day, (daily.get(r._day)||0) + load);
    const aw = allWeeks.get(weekOf(r._day)) || {n:0, km:0, long:0};
    aw.n++; aw.km += r._km||0; aw.long = Math.max(aw.long, r._km||0); allWeeks.set(weekOf(r._day), aw);
    const i = weekOf(r._day) - firstWeek; if (i < 0) continue;
    const B = weeks[i]; B.n++; B.km += r._km||0; B.long = Math.max(B.long, r._km||0); B.load += load;
    const z = zoneTime(r, max, rest); if (z) z.forEach((v,k)=>B.z[k]+=v);
    if (!r._hrOk && Array.isArray(r.hrz)) nFb++;
  }
  const sumDays = (a,b) => { let s=0; for (let d=a; d<=b; d++) s += daily.get(d)||0; return s; };
  const firstDay = RUNS[0]._day;
  const acwr = day => { if (day-27 < firstDay) return null; const ch = sumDays(day-27, day)/4; return ch>0 ? sumDays(day-6, day)/ch : null; };
  weeks.forEach(B => { B.acwr = acwr(Math.min(weekStart(B.w)+6, lastDay)); });

  // KPIs over the last 12 weeks
  const last12 = weeks.slice(-12);
  const now = acwr(lastDay);
  const ratioTxt = now==null ? "" : now<0.8 ? "below 0.8: easing off" : now<=1.3 ? "in the 0.8–1.3 range" : now<=1.5 ? "1.3–1.5: ramping up fast" : "above 1.5: high injury risk";
  const zt = last12.reduce((a,B)=>a.map((v,k)=>v+B.z[k]), [0,0,0,0,0]), zSum = zt.reduce((a,b)=>a+b,0);
  const easy = zSum ? (zt[0]+zt[1])/zSum*100 : null;
  const n12 = last12.reduce((s,B)=>s+B.n,0), km12 = last12.reduce((s,B)=>s+B.km,0);
  let streak = 0; for (let w=lastWeek; allWeeks.has(w); w--) streak++;
  let best = 0, cur = 0, prevW = null;
  for (const w of [...allWeeks.keys()].sort((a,b)=>a-b)){ cur = prevW!=null && w===prevW+1 ? cur+1 : 1; best = Math.max(best, cur); prevW = w; }
  const longShare = median(last12.filter(B=>B.km>0).map(B=>B.long/B.km*100));
  const k = [];
  k.push(`<div class="kpi"><span class="lab">Load ratio (7 d : 28 d)</span><span class="val">${now==null?"–":now.toFixed(2)}</span><span class="sub">${now==null?"Needs 4 weeks of runs with heart rate":`at your last run · <span class="chip ${now>=0.8&&now<=1.3?"good":"bad"}">${ratioTxt}</span>`}</span></div>`);
  k.push(`<div class="kpi"><span class="lab">Easy share, 12 weeks</span><span class="val">${easy==null?"–":Math.round(easy)+"%"}</span><span class="sub">${easy==null?"No heart-rate data":`of running time below 70% of heart-rate reserve (&lt; ${zb[1]} bpm) · <span class="chip ${easy>=75?"good":"bad"}">${easy>=75?"close to 80/20":"aim for about 80%"}</span>`}</span></div>`);
  k.push(`<div class="kpi"><span class="lab">Runs per week, 12 weeks</span><span class="val">${(n12/12).toFixed(1)}</span><span class="sub">${nf.format(km12/12)} km a week on average</span></div>`);
  k.push(`<div class="kpi"><span class="lab">Weekly streak</span><span class="val">${streak} wk</span><span class="sub">weeks in a row with at least one run · longest ${best} wk</span></div>`);
  k.push(`<div class="kpi"><span class="lab">Long-run share, 12 weeks</span><span class="val">${longShare==null?"–":Math.round(longShare)+"%"}</span><span class="sub">of a week's distance in its longest run (median)</span></div>`);
  $("kpis2").innerHTML = k.join("");
  $("zones-fallback").textContent = `${nFb} run${nFb===1?"":"s"} without a usable heart-rate stream use${nFb===1?"s":""} Garmin's zones: set Garmin Connect to HRR zones to match.`;
  $("zones-fallback").hidden = !nFb;

  const labels = weeks.map(B => new Date(weekStart(B.w)*864e5).toLocaleDateString(undefined, {day:"numeric", month:"short", timeZone:"UTC"}));
  const title = items => items.length ? `Week of ${fmtDay(weekStart(weeks[items[0].dataIndex].w))}` : "";
  const xCat = o => { o.scales.x = {...o.scales.x, ticks:{...o.scales.x.ticks, maxRotation:0, autoSkip:true, maxTicksLimit:7}}; return o; };

  let o = xCat(baseOpts(c));
  o.scales.y.title = {display:true,text:"TRIMP",color:c.muted};
  o.plugins.tooltip.callbacks = {title, label:ctx=>`Load ${nf.format(ctx.parsed.y)} · ${weeks[ctx.dataIndex].n} runs`};
  chart("c-load", {type:"bar", data:{labels, datasets:[{data:weeks.map(B=>Math.round(B.load)), backgroundColor:alpha(c.a1,.75), borderRadius:3}]}, options:o});

  o = xCat(baseOpts(c));
  o.scales.y = {...o.scales.y, min:0, suggestedMax:2, title:{display:true,text:"ratio",color:c.muted}};
  o.plugins.tooltip.callbacks = {title, label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}`};
  o.plugins.tooltip.filter = item => item.datasetIndex === 0;
  const ref = v => ({label:String(v), data:weeks.map(()=>v), borderColor:c.muted, borderDash:[5,4], borderWidth:1.5, pointRadius:0, pointHitRadius:0});
  chart("c-acwr", {type:"line", data:{labels, datasets:[
    {label:"Load ratio", data:weeks.map(B=>B.acwr), borderColor:c.a1, backgroundColor:c.a1, borderWidth:2, pointRadius:2.5, pointHoverRadius:5, tension:.25, spanGaps:false},
    ref(0.8), ref(1.3)
  ]}, options:o});

  o = xCat(baseOpts(c));
  o.scales.x.stacked = true; o.scales.y = {...o.scales.y, stacked:true, title:{display:true,text:"minutes",color:c.muted}};
  o.interaction = {mode:"index", intersect:false};
  o.plugins.tooltip.callbacks = {title, label:ctx=>`${zr[ctx.datasetIndex].replace("&lt;","<")} bpm: ${nf.format(ctx.parsed.y)} min`};
  const zc = [1,2,3,4,5].map(i=>tok("--z"+i));
  chart("c-zones", {type:"bar", data:{labels, datasets:zc.map((col,i)=>({label:"Z"+(i+1), data:weeks.map(B=>Math.round(B.z[i]/60)), backgroundColor:col, borderColor:c.surface, borderWidth:{top:1}, borderSkipped:false}))}, options:o});

  o = xCat(baseOpts(c));
  o.scales.x.stacked = true; o.scales.y = {...o.scales.y, stacked:true, title:{display:true,text:"km",color:c.muted}};
  o.interaction = {mode:"index", intersect:false};
  o.plugins.tooltip.callbacks = {title, label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} km`};
  chart("c-week", {type:"bar", data:{labels, datasets:[
    {label:"Longest run", data:weeks.map(B=>B.long), backgroundColor:c.a2, borderColor:c.surface, borderWidth:{top:1}, borderSkipped:false},
    {label:"Other runs", data:weeks.map(B=>B.km-B.long), backgroundColor:alpha(c.a1,.75), borderColor:c.surface, borderWidth:{top:1}, borderSkipped:false}
  ]}, options:o});

  // consistency per calendar year (all runs)
  const days = [...new Set(RUNS.map(r=>r._day))].sort((a,b)=>a-b);
  const yrs = {};
  for (let i=0;i<days.length;i++){
    const y = new Date(days[i]*864e5).getUTCFullYear(), Y = yrs[y] ||= {y, runDays:0, gaps:0, longest:0};
    if (i>0){ const gap = days[i]-days[i-1]-1; if (gap>=7) Y.gaps++; Y.longest = Math.max(Y.longest, gap); }
  }
  for (const r of RUNS) (yrs[r._y] ||= {y:r._y, gaps:0, longest:0}).n = (yrs[r._y].n||0) + 1;
  let h = `<thead><tr><th>Year</th><th>Runs/week</th><th>Weeks with a run</th><th>Breaks of 7+ days</th><th>Longest break</th><th>Long-run share</th></tr></thead><tbody>`;
  for (const Y of Object.values(yrs).sort((a,b)=>b.y-a.y)){
    const a = Math.max(Math.round(Date.UTC(Y.y,0,1)/864e5), firstDay), b = Math.min(Math.round(Date.UTC(Y.y,11,31)/864e5), lastDay);
    const wks = [...allWeeks.entries()].filter(([w])=>w>=weekOf(a) && w<=weekOf(b));
    const span = weekOf(b)-weekOf(a)+1;
    const share = median(wks.filter(([,v])=>v.km>0).map(([,v])=>v.long/v.km*100));
    h += `<tr><td>${Y.y}</td><td>${(Y.n/((b-a+1)/7)).toFixed(1)}</td><td>${Math.round(wks.length/span*100)}%</td><td>${Y.gaps}</td><td>${Y.longest} d</td><td>${share==null?"–":Math.round(share)+"%"}</td></tr>`;
  }
  $("tbl2").innerHTML = h + "</tbody>";
}
