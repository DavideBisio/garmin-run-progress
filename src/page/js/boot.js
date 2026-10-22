"use strict";
/* ---------------- boot ---------------- */
// re-render charts when the theme changes
try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render); } catch(e){}
new MutationObserver(render).observe(document.documentElement, {attributes:true, attributeFilter:["data-theme"]});

/* ---------------- boot ---------------- */
setData(exampleData(), true);
idbGet().then(saved => { if (saved && Array.isArray(saved.runs)) { setData(saved, false); say(`Loaded ${nf.format(RUNS.length)} runs saved in this browser.`, "ok");
  if (!tabFromHash() && !tabTouched) showTab("analysis", false); } });
