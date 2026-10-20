"use strict";
/* ---------------- storage (IndexedDB) ---------------- */
function idb(){ return new Promise((res,rej)=>{ try{ const q=indexedDB.open("run-progress-lab",1);
  q.onupgradeneeded=()=>q.result.createObjectStore("kv"); q.onsuccess=()=>res(q.result); q.onerror=()=>rej(q.error);}catch(e){rej(e);} }); }
async function idbSet(v){ try{ const db=await idb(); await new Promise((res,rej)=>{const tx=db.transaction("kv","readwrite"); v===undefined?tx.objectStore("kv").delete("data"):tx.objectStore("kv").put(v,"data"); tx.oncomplete=res; tx.onerror=()=>rej(tx.error);}); }catch(e){} }
async function idbGet(){ try{ const db=await idb(); return await new Promise((res)=>{const q=db.transaction("kv").objectStore("kv").get("data"); q.onsuccess=()=>res(q.result); q.onerror=()=>res(null);}); }catch(e){ return null; } }
