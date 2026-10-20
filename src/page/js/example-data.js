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
  return {format:"garmin-runs/1", example:true, runs, rhr};
}
