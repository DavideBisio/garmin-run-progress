"use strict";
/* ---------------- copy helpers ---------------- */
async function copyText(text, btn){
  const old = btn.textContent;
  try { await navigator.clipboard.writeText(text); btn.textContent = "Copied"; }
  catch(e){
    const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand("copy"); } catch(_){}
    ta.remove(); btn.textContent = ok ? "Copied" : "Select and copy manually";
  }
  setTimeout(() => btn.textContent = old, 1800);
}
document.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", () => {
  const el = $(b.dataset.copy); copyText(el.textContent.replace(b.textContent, "").trim(), b);
}));
$("copy-script").addEventListener("click", e => copyText(SRC, e.currentTarget));
