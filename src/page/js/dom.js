"use strict";
/* ---------------- dom & grabber source ---------------- */
const $ = id => document.getElementById(id);
const SRC = $("grabber-src").textContent.replace(/^\n/, "");
$("script-view").textContent = SRC;
