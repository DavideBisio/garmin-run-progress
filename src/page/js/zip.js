"use strict";
/* ---------------- zip (stored) ---------------- */
const CRC = (() => { const t = new Uint32Array(256); for (let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0;} return t; })();
function crc32(b){ let c=0xFFFFFFFF; for (let i=0;i<b.length;i++) c=CRC[(c^b[i])&255]^(c>>>8); return (c^0xFFFFFFFF)>>>0; }
function makeZip(files){
  const enc = new TextEncoder(), parts = [], central = []; let off = 0;
  const now = new Date();
  const dt = ((now.getHours()<<11)|(now.getMinutes()<<5)|(now.getSeconds()>>1)) & 0xFFFF;
  const dd = (((now.getFullYear()-1980)<<9)|((now.getMonth()+1)<<5)|now.getDate()) & 0xFFFF;
  for (const f of files){
    const name = enc.encode(f.name), data = enc.encode(f.text), crc = crc32(data);
    const h = new DataView(new ArrayBuffer(30));
    h.setUint32(0,0x04034b50,true); h.setUint16(4,20,true); h.setUint16(6,0x0800,true); h.setUint16(8,0,true);
    h.setUint16(10,dt,true); h.setUint16(12,dd,true); h.setUint32(14,crc,true);
    h.setUint32(18,data.length,true); h.setUint32(22,data.length,true); h.setUint16(26,name.length,true); h.setUint16(28,0,true);
    parts.push(new Uint8Array(h.buffer), name, data);
    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0,0x02014b50,true); c.setUint16(4,20,true); c.setUint16(6,20,true); c.setUint16(8,0x0800,true); c.setUint16(10,0,true);
    c.setUint16(12,dt,true); c.setUint16(14,dd,true); c.setUint32(16,crc,true); c.setUint32(20,data.length,true); c.setUint32(24,data.length,true);
    c.setUint16(28,name.length,true); c.setUint32(42,off,true);
    central.push(new Uint8Array(c.buffer), name);
    off += 30 + name.length + data.length;
  }
  const csize = central.reduce((s,p)=>s+p.length,0);
  const e = new DataView(new ArrayBuffer(22));
  e.setUint32(0,0x06054b50,true); e.setUint16(8,files.length,true); e.setUint16(10,files.length,true);
  e.setUint32(12,csize,true); e.setUint32(16,off,true);
  return new Blob([...parts, ...central, new Uint8Array(e.buffer)], {type:"application/zip"});
}
const README = `Garmin grabber for Run Progress Lab
====================================

1. Install Python 3.12+ and, in this folder:
     python3 -m venv .venv
     source .venv/bin/activate        (Windows: .venv\\Scripts\\activate)
     pip install --upgrade garminconnect curl_cffi ua-generator

2. Run:
     python garmin_grab.py

   First run: asks for Garmin email, password, MFA code. Tokens are saved
   in ~/.garminconnect so later runs need nothing.

3. Upload garmin_export/runs.json to the Run Progress Lab page.

Run it again any time; it only downloads runs it has not seen yet.
Original GPX files stay in garmin_export/gpx/.
`;
(async () => {
  let dl = null;
  try { dl = window.claude && await window.claude.use("downloads"); } catch(e){ dl = null; }
  if (!dl) return;
  const btn = $("dl-zip"); btn.hidden = false;
  btn.addEventListener("click", async () => {
    $("dl-msg").textContent = ""; $("dl-msg").className = "msg";
    try {
      await dl.save({filename:"garmin_grabber.zip", data: makeZip([{name:"garmin_grab.py",text:SRC},{name:"README.txt",text:README}])});
      $("dl-msg").textContent = "Saved. Unzip it and follow the setup below."; $("dl-msg").className = "msg ok";
    } catch(err){
      if (err && err.code === "declined") return;
      if (err && err.code === "rate_limited"){ $("dl-msg").textContent = "A save prompt is already open."; return; }
      btn.hidden = true; $("dl-msg").textContent = "Downloads aren't available here. Use Copy script and save it as garmin_grab.py.";
    }
  });
})();
