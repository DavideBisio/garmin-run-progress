"use strict";
/* ---------------- stats helpers ---------------- */
const median = a => { if(!a.length) return null; const s=[...a].sort((x,y)=>x-y), m=s.length>>1; return s.length%2?s[m]:(s[m-1]+s[m])/2; };
function theilSen(pts){ const sl=[]; for(let i=0;i<pts.length;i++)for(let j=i+1;j<pts.length;j++){const dx=pts[j][0]-pts[i][0]; if(dx) sl.push((pts[j][1]-pts[i][1])/dx);} return median(sl); }
const fmtPace = s => { if (s==null||!isFinite(s)) return "–"; s=Math.round(s); return `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`; };
const fmtTime = s => { if (s==null) return "–"; s=Math.round(s); const h=Math.floor(s/3600), m=Math.floor(s%3600/60), x=s%60; return h?`${h}:${String(m).padStart(2,"0")}:${String(x).padStart(2,"0")}`:`${m}:${String(x).padStart(2,"0")}`; };
const nf = new Intl.NumberFormat(undefined,{maximumFractionDigits:0});
