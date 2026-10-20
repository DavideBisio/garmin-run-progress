"use strict";
/* ---------------- geometry & metrics ---------------- */
const SAMPLE = 10;
function hav(a1,o1,a2,o2){ const r=6371008.8, p1=a1*Math.PI/180, p2=a2*Math.PI/180, dp=p2-p1, dl=(o2-o1)*Math.PI/180;
  const a=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2; return 2*r*Math.asin(Math.sqrt(a)); }
function minetti(i){ i=Math.max(-0.3,Math.min(0.3,i)); return 155.4*i**5-30.4*i**4-43.3*i**3+46.3*i**2+19.5*i+3.6; }
const gapFactor = g => minetti(g)/3.6;
function vdot(m, s){ const t=s/60, v=m/t;
  const vo2=-4.6+0.182258*v+0.000104*v*v;
  const pct=0.8+0.1894393*Math.exp(-0.012778*t)+0.2989558*Math.exp(-0.1932605*t);
  return vo2/pct; }
function decYear(dateStr){ const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr||""); if(!m) return null;
  const y=+m[1], start=Date.UTC(y,0,1), end=Date.UTC(y+1,0,1), d=Date.UTC(y,+m[2]-1,+m[3]);
  return {y, month:+m[2], x: y+(d-start)/(end-start), day: Math.round(d/864e5)}; }
const weekOf = day => Math.floor((day+3)/7);            // Monday-based week index (day 0 = Thu 1970-01-01)
const weekStart = w => w*7-3;
const DISTS = [{k:"1k",m:1000},{k:"5k",m:5000},{k:"10k",m:10000},{k:"hm",m:21097.5}];

function bestEffort(t, d, D){
  if (!t || d[d.length-1] < D) return null;
  let best = Infinity, i = 0;
  for (let j=1;j<d.length;j++){
    if (d[j]-d[0] < D) continue;
    while (i+1 < j && d[j]-d[i+1] >= D) i++;
    const target = d[j]-D, span = d[i+1]-d[i];
    const ts = span>0 ? t[i]+(t[i+1]-t[i])*(target-d[i])/span : t[i];
    const dur = t[j]-ts;
    if (dur > 0 && dur < best) best = dur;
  }
  if (!isFinite(best) || D/best > 6.4) return null;
  return best;
}
function prepare(r){
  const p = decYear(r.date); if (!p) return null;
  r._x = p.x; r._y = p.y; r._m = p.month; r._day = p.day;
  r._trail = /trail/.test(r.type||"");
  r._dec = null;
  if (r.t && r.t.length > 5){
    r._km = (r.dist || r.d[r.d.length-1]) / 1000;
    const n=r.t.length, g=new Float32Array(n); let k=0;
    for (let i=0;i<n;i++){
      while (k<i && r.d[i]-r.d[k+1] >= 100) k++;
      const dd=r.d[i]-r.d[k]; g[i] = dd>=60 && r.e[i] && r.e[k] ? (r.e[i]-r.e[k])/10/dd : 0;
    }
    r._g = g;
    const hs = r.hr.filter(h=>h>0);
    r._hrOk = hs.length > n*0.6;
    if (r._hrOk){ hs.sort((a,b)=>a-b); r._hrPeak = hs[Math.floor(hs.length*0.99)]; }   // 99th percentile ignores optical spikes
    r._best = {}; for (const D of DISTS) r._best[D.k] = bestEffort(r.t, r.d, D.m);
    const dc = decoupling(r); if (dc){ r._dec = dc.pct; r._decMin = dc.min; }
  } else { r._km = (r.dist||0)/1000; r._best = {}; }
  return r;
}
function bandPace(r, lo, hi){
  if (!r._g || !r._hrOk) return null;
  let tt=0, adj=0; const t=r.t, d=r.d, h=r.hr;
  for (let i=1;i<t.length;i++){
    if (t[i] < 600) continue;
    const dt=t[i]-t[i-1], dd=d[i]-d[i-1]; if (dt<=0 || dt>30) continue;
    const v=dd/dt; if (v<1.6 || v>6.5) continue;
    const hr=h[i]; if (hr<lo || hr>hi) continue;
    tt+=dt; adj+=dd*gapFactor(r._g[i]);
  }
  return tt>=600 && adj>0 ? tt/adj*1000 : null;
}
function decoupling(r){
  if (!r._g || !r._hrOk) return null;
  const t=r.t, d=r.d, h=r.hr, seg=[];
  for (let i=1;i<t.length;i++){
    if (t[i] < 600) continue;
    const dt=t[i]-t[i-1], dd=d[i]-d[i-1]; if (dt<=0 || dt>30 || !h[i]) continue;
    const v=dd/dt; if (v<1.6 || v>6.5) continue;
    seg.push([dt, dd*gapFactor(r._g[i]), h[i]*dt]);
  }
  const total = seg.reduce((s,x)=>s+x[0],0);
  if (total < 2400) return null;
  // steady runs only: 5-minute blocks of grade-adjusted speed within 10% of their mean
  const blocks=[]; let bt=0, bd=0;
  for (const [dt,ad] of seg){ bt+=dt; bd+=ad; if (bt>=300){ blocks.push(bd/bt); bt=bd=0; } }
  const mean = blocks.reduce((s,v)=>s+v,0)/blocks.length;
  const sd = Math.sqrt(blocks.reduce((s,v)=>s+(v-mean)**2,0)/blocks.length);
  if (sd/mean > 0.10) return null;
  const half=[[0,0],[0,0]]; let acc=0;
  for (const [dt,ad,hb] of seg){ const k = acc < total/2 ? 0 : 1; half[k][0]+=ad; half[k][1]+=hb; acc+=dt; }
  const ef1=half[0][0]/half[0][1], ef2=half[1][0]/half[1][1];
  return {pct:(ef1-ef2)/ef1*100, min:total/60};
}
function zoneTime(r, max){       // seconds in zones 1–5 (share of max HR)
  if (r._hrOk){
    const z=[0,0,0,0,0], t=r.t, h=r.hr;
    for (let i=1;i<t.length;i++){ const dt=t[i]-t[i-1]; if (dt<=0 || dt>30 || !h[i]) continue;
      const f=h[i]/max; z[f<.6?0:f<.7?1:f<.8?2:f<.9?3:4]+=dt; }
    return z;
  }
  return Array.isArray(r.hrz) ? r.hrz.slice(0,5) : null;
}
function trimp(r, max, rest){    // Banister TRIMP: minutes × HRr × 0.64·e^(1.92·HRr)
  const f = hr => { const x=Math.max(0,Math.min(1,(hr-rest)/(max-rest))); return x*0.64*Math.exp(1.92*x)/60; };
  if (r._hrOk){ let s=0; const t=r.t, h=r.hr;
    for (let i=1;i<t.length;i++){ const dt=t[i]-t[i-1]; if (dt>0 && dt<=30 && h[i]) s+=dt*f(h[i]); }
    return s; }
  return r.avgHr ? (r.moving||r.dur||0)*f(r.avgHr) : 0;
}
