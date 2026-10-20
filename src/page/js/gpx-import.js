"use strict";
/* ---------------- GPX import ---------------- */
function parseGpxText(txt, name){
  const doc = new DOMParser().parseFromString(txt, "application/xml");
  const pts = [];
  for (const el of doc.getElementsByTagNameNS("*","trkpt")){
    const lat=+el.getAttribute("lat"), lon=+el.getAttribute("lon"); let tm=null, ele=null, hr=0;
    for (const c of el.getElementsByTagName("*")){
      const n=c.localName;
      if (n==="time") tm=Date.parse(c.textContent); else if (n==="ele") ele=+c.textContent; else if (n==="hr") hr=Math.round(+c.textContent);
    }
    if (tm && isFinite(lat)) pts.push([tm,lat,lon,ele,hr]);
  }
  if (pts.length < 2) return null;
  pts.sort((a,b)=>a[0]-b[0]);
  const cum=[0]; for (let i=1;i<pts.length;i++) cum.push(cum[i-1]+hav(pts[i-1][1],pts[i-1][2],pts[i][1],pts[i][2]));
  const t0=pts[0][0], t=[],d=[],hr=[],e=[]; let last=-1e9;
  pts.forEach((p,i)=>{ if ((p[0]-last)/1000 < SAMPLE && i!==pts.length-1) return; last=p[0];
    t.push(Math.round((p[0]-t0)/1000)); d.push(Math.round(cum[i])); hr.push(p[4]); e.push(p[3]==null?0:Math.round(p[3]*10)); });
  const local = new Date(t0 - new Date(t0).getTimezoneOffset()*60000).toISOString().replace("T"," ").slice(0,19);
  const type = /trail/i.test(txt.slice(0,3000)) ? "trail_running" : "running";
  return {date:local, name, type, dist:cum[cum.length-1], dur:t[t.length-1], t, d, hr, e};
}
