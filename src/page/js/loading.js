"use strict";
/* ---------------- loading ---------------- */
const drop = $("drop"), fileIn = $("file");
drop.addEventListener("click", ()=>fileIn.click());
drop.addEventListener("keydown", e=>{ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); fileIn.click(); } });
["dragenter","dragover"].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add("over");}));
["dragleave","drop"].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove("over");}));
drop.addEventListener("drop", e=>handleFiles([...e.dataTransfer.files]));
fileIn.addEventListener("change", ()=>{ handleFiles([...fileIn.files]); fileIn.value=""; });
function say(t, cls){ const m=$("load-msg"); m.textContent=t; m.className="msg "+(cls||""); }
async function handleFiles(files){
  if (!files.length) return;
  const json = files.find(f=>/\.json$/i.test(f.name));
  const gpx = files.filter(f=>/\.gpx$/i.test(f.name));
  try {
    let payload;
    if (json){
      say("Reading "+json.name+"…");
      payload = JSON.parse(await json.text());
      if (!payload || !Array.isArray(payload.runs)) throw new Error("This JSON isn't a runs.json from the grabber (no \"runs\" list).");
    } else if (gpx.length){
      const bar=$("prog"); bar.hidden=false; const runs=[];
      for (let i=0;i<gpx.length;i++){
        const r = parseGpxText(await gpx[i].text(), gpx[i].name); if (r) runs.push(r);
        if (i%20===0){ bar.firstElementChild.style.width=(100*i/gpx.length)+"%"; say(`Parsing GPX ${i+1}/${gpx.length}…`); await new Promise(r=>setTimeout(r)); }
      }
      bar.hidden=true;
      if (!runs.length) throw new Error("None of the GPX files had a usable track.");
      payload = {format:"garmin-runs/1", runs};
    } else throw new Error("Choose runs.json or .gpx files.");
    setData(payload, false);
    const withStream = RUNS.filter(r=>r._g).length;
    say(`Loaded ${nf.format(RUNS.length)} runs (${nf.format(withStream)} with GPS track).`, "ok");
    if ($("remember").checked) idbSet(payload);
  } catch(err){ $("prog").hidden=true; say(err.message || "Couldn't read that file.", "err"); }
}
$("clear").addEventListener("click", async ()=>{ await idbSet(undefined); setData(exampleData(), true); say("Your data was removed from this browser."); });
$("remember").addEventListener("change", e=>{ if (!e.target.checked) idbSet(undefined); else if (DATA && !DATA.example) idbSet(DATA); });
