"use strict";
/* ---------------- example data ---------------- */
function exampleData(){
  let seed = 7; const rnd = () => (seed = (seed*16807)%2147483647)/2147483647;
  const gauss = () => Math.sqrt(-2*Math.log(rnd()+1e-9))*Math.cos(2*Math.PI*rnd());
  const runs = []; const start = Date.UTC(2016,2,1);
  for (let day=0; day<3650; day+= 3 + Math.floor(rnd()*4)){
    const dt = new Date(start + day*864e5), yrs = day/365, month = dt.getUTCMonth()+1;
    const heat = (month>=6 && month<=8) ? 4 : 0;
    const fit = 2.95 + 0.055*yrs - 0.02*Math.max(0,yrs-6.5)**2 + 0.05*Math.sin(yrs*2*Math.PI)*0.3;
    const dur = 1800 + Math.floor(rnd()*3600), hard = rnd() < 0.15;
    const t=[],d=[],hr=[],e=[]; let dist=0, h=118;
    const driftPerH = Math.max(2, 12 - yrs);                 // cardiac drift shrinks as endurance grows
    for (let s=0; s<=dur; s+=SAMPLE){
      const drift = driftPerH*s/3600;
      const target = (hard ? 168 : 143) + heat + drift + gauss()*1.5;
      h += (target-h)*Math.min(1,s/700)*0.25;
      const v = fit*(1+(h-heat-drift-143)/95)*(1+gauss()*0.02);
      dist += v*SAMPLE;
      t.push(s); d.push(Math.round(dist)); hr.push(Math.round(h)); e.push(Math.round((120+25*Math.sin(dist/900))*10));
    }
    const ds = dt.toISOString().slice(0,10)+" 07:00:00";
    const cad = 163 + yrs*0.8 + (hard?8:0) + gauss()*2;
    const r1 = x => Math.round(x*10)/10, clamp5 = x => Math.max(0, Math.min(5, x));
    runs.push({date:ds,type:"running",dist,dur,avgHr:Math.round(hr.reduce((a,b)=>a+b,0)/hr.length),vo2:Math.round(44+yrs*0.55+gauss()*0.6),
      cad:r1(cad), stride:r1(dist/dur/(cad/60)*100),
      te:r1(clamp5(hard ? 3.8+gauss()*0.3 : 2.4+dur/3600*0.6+gauss()*0.2)), teAn:r1(clamp5(hard ? 2.5+gauss()*0.5 : 0.4+gauss()*0.3)),
      t,d,hr,e});
  }
  const rhr = [];
  for (let day=0; day<3650; day++){
    const dt = new Date(start + day*864e5), yrs = day/365;
    rhr.push([dt.toISOString().slice(0,10), Math.round(57 - 0.7*yrs + 0.2*Math.max(0,yrs-6.5)**2 + gauss()*1.5)]);
  }
  return {format:"garmin-runs/1", example:true, runs, rhr, plan:examplePlan(runs)};
}
// A synthetic plan.json (docs/plan-json-format.md) around the example's last run, so the Planning tab
// has content: 4 past weeks whose sessions are the example runs (one more session missed), this
// week, 7 to come; base then R + T, deloads, one Q a week. No status fields: the page matches the
// runs by date, as for a plan from before 09.
function examplePlan(runs){
  const iso = day => new Date(day*864e5).toISOString().slice(0,10), r1 = x => Math.round(x*10)/10;
  const last = decYear(runs[runs.length-1].date).day, today = last+1, mon = weekStart(weekOf(today)), NW = 12;
  const E = [318,348], T = [265,275], zb = hrrZones(186, 48), Z2 = [zb[0],zb[1]], Z4 = [zb[2],zb[3]];
  const step = (label, role, zone, pace, hz, hr, end, value, meters, seconds) => ({type:"step", role, label, end, value, zone,
    pace_s_per_km:pace, hr_zone:hz, hr, est_pace_s_per_km:null, est_dist:null, est_time:null, effort:null, note:"",
    hard:role==="rep" && zone==="T", meters, seconds});
  const easy = (km, kind="E") => { const m = Math.round(km*1000), sec = Math.round(km*333);
    return {id:kind==="L" ? "long_run" : "easy_run", variant:1, title:kind==="L" ? "Long Run" : "Easy Run", kind, km:r1(km), seconds:sec,
      hard_km:0, climb_m_per_km:null, steps:[step("Run", "rep", "E", E, "Z2", Z2, "dist", m, m, sec)]}; };
  const tempo = km => { const cool = Math.max(1, km-7.7), cm = Math.round(cool*1000), cs = Math.round(cool*333);
    return {id:"cruise_tempo", variant:2, title:"Cruise Tempo", kind:"T", km:r1(7.7+cool), seconds:666+1656+cs, hard_km:4.8, climb_m_per_km:null,
      steps:[step("Warmup", "warmup", "E", E, "Z2", Z2, "dist", 2000, 2000, 666),
        {type:"repeat", n:3, skip_last_rest:false, note:"", meters:5700, seconds:1656, steps:[
          step("Tempo", "rep", "T", T, "Z4", Z4, "dist", 1600, 1600, 432),
          step("Recovery", "recovery", "jog", null, "Z2", Z2, "time", 120, 300, 120)]},
        step("Cooldown", "cooldown", "E", E, "Z2", Z2, "dist", cm, cm, cs)]}; };
  const entry = (d, slot, w) => ({date:iso(d), slot, status:null, activity_id:null, changed_by:null, workout:w});
  const ran = new Map();
  for (const r of runs){ const d = decYear(r.date).day; if (d >= mon-29) ran.set(d, (ran.get(d)||0) + r.dist/1000); }
  let missed = null;                 // a day with no run on it or next to it, so it stays missed
  for (let d = mon-28; d < mon-1 && missed==null; d++) if (![d-1, d, d+1].some(x => ran.has(x))) missed = d;
  ran.delete(mon-29);                // (only there for that check: the plan starts at mon-28)
  const weeks = [];
  for (let i = 0; i < NW; i++){
    const ws = mon + 7*(i-4), deload = i===3 || i===7, days = [];
    const past = [...ran.keys()].filter(d => d >= ws && d <= ws+6).sort((a,b)=>a-b);
    const long = past.reduce((a, d) => a==null || ran.get(d) > ran.get(a) ? d : a, null);
    const q = past.find(d => ran.get(d) >= 9 && d!==long);
    for (const d of past) days.push(entry(d, d===q ? "Q" : d===long ? "L" : "E", d===q ? tempo(ran.get(d)) : easy(ran.get(d), d===long ? "L" : "E")));
    if (missed!=null && missed >= ws && missed <= ws+6) days.push(entry(missed, "E", easy(6)));
    const t = (28 + 1.5*i) * (deload ? 0.85 : 1), lkm = r1(t*0.3), ekm = r1((t - 9 - lkm)/2);
    for (const [k, slot] of [[1,"Q"], [3,"E"], [5,"E"], [6,"L"]]){
      const d = ws+k;
      if (d < today) continue;
      const s = slot==="Q" && q!=null ? "E" : slot;
      days.push(entry(d, s, s==="Q" ? tempo(9) : easy(s==="L" ? lkm : ekm, s)));
    }
    days.sort((a, b) => a.date < b.date ? -1 : 1);
    weeks.push({start:iso(ws), target_km:r1(days.reduce((a, x) => a + x.workout.km, 0)), unit:"km", phase:i < 6 ? "base" : "rt",
      deload, warnings:[], days});
  }
  const race = {date:iso(mon + 7*(NW-4) + 6), distance_m:21097.5, goal_s:5700};
  return {version:1, generated:iso(last)+"T20:00:00", profile_hash:"example", profile:{vdot:45, hr_max:186, hr_rest:48, race},
    levels:{volume:"intermediate", quality:"novice", reasons:{volume:"example data", quality:"example data"}},
    progress:{plan_start:iso(mon+7), block_start:iso(mon-28), cycle_start:iso(mon-28), run_walk_stage:null, vdot:null, time_trials:[], time_trial:null},
    changes:[], history:[],
    warnings:[{rule:"feasibility", detail:"the goal needs VDOT 47.6, 2.6 above the current 45.0, in 8 weeks: ambitious",
      action:"kept the paces at the current VDOT (set vdot after a race or time trial to raise them)"}],
    weeks};
}
