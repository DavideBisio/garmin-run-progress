"use strict";
/* ---------------- tabs (Data, Analysis, Planning: WAI-ARIA tabs that follow the URL hash) ---------------- */
// Only location.hash and location.replace: history.pushState throws on file:// and in sandboxed iframes.
const TABS = ["data","analysis","planning"], OLD_TABS = {s1:"data", s2:"data", s3:"analysis"};
let curTab = null, tabTouched = false;
function curHash(){ try{ return location.hash || ""; }catch(e){ return ""; } }
function tabFromHash(){ const h = curHash().slice(1); return TABS.includes(h) ? h : OLD_TABS[h] || ""; }
// push: add a history entry (a click or a file load); otherwise only fix up a hash that is already there
function showTab(name, push){
  const hash = curHash(), want = "#"+name;
  if (name===curTab && (hash===want || !push && !hash)) return;
  const was = curTab; curTab = name;
  for (const t of TABS){ const on = t===name, b = $("tab-btn-"+t);
    $("tab-"+t).hidden = !on; b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1; }
  // charts drawn while their panel was hidden measured 0 x 0
  if (name!==was && name==="analysis") Object.values(charts).forEach(c=>c?.resize?.());
  try{ if (hash!==want && (push || hash)){ if (push) location.hash = want; else location.replace(want); } }catch(e){}
}
TABS.forEach((t,i)=>{ const b = $("tab-btn-"+t);
  b.addEventListener("click", ()=>{ tabTouched = true; showTab(t, true); });
  b.addEventListener("keydown", e=>{
    const j = {ArrowRight:(i+1)%TABS.length, ArrowLeft:(i+TABS.length-1)%TABS.length, Home:0, End:TABS.length-1}[e.key];
    if (j==null) return;
    e.preventDefault(); tabTouched = true; showTab(TABS[j], true); $("tab-btn-"+TABS[j]).focus();
  });
});
try{ window.addEventListener("hashchange", ()=>{ const t = tabFromHash() || "data"; if (t!==curTab) tabTouched = true; showTab(t, false); }); }catch(e){}
showTab(tabFromHash() || "data", false);
