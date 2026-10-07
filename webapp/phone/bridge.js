// bridge.js - phone/web version: connects the UI to the Python worker (worker.js).
"use strict";
(function () {
  const worker = new Worker("worker.js");
  const pending = new Map();
  let seq = 0;

  // ---- startup screen (Pyodide takes a few seconds the first time, then it is cached)
  const boot = document.createElement("div");
  boot.id = "web-boot";
  boot.innerHTML = '<div class="wb-card"><div class="wb-mark">₹</div><div class="wb-title">Rental Billing</div>' +
    '<div class="wb-msg">Starting…</div><div class="wb-bar"><span></span></div>' +
    '<div class="wb-note">The first start can take up to a minute. After that it opens quickly.</div></div>';
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(boot));

  function showFile(f) {
    const bytes = Uint8Array.from(atob(f.b64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: f.mime }));
    if (f.mime === "text/csv") {
      const a = document.createElement("a");
      a.href = url; a.download = f.name; document.body.appendChild(a); a.click(); a.remove();
      return;
    }
    // A tap is needed to open a PDF on most phones, so offer a button
    const card = document.createElement("div");
    card.className = "pdf-ready";
    card.innerHTML = '<div><b>PDF ready</b><small></small></div><a class="btn primary sm" target="_blank" rel="noopener">Open</a>' +
      '<a class="btn sm" download>Save</a><button class="btn ghost sm" aria-label="Close">✕</button>';
    card.querySelector("small").textContent = f.name;
    const [open, save] = card.querySelectorAll("a");
    open.href = url; save.href = url; save.download = f.name;
    const close = () => card.remove();
    card.querySelector("button").onclick = close;
    open.addEventListener("click", () => setTimeout(close, 400));
    document.body.appendChild(card);
  }

  worker.onmessage = (ev) => {
    const m = ev.data;
    if (m.type === "progress") { const el = boot.querySelector(".wb-msg"); if (el) el.textContent = m.msg; return; }
    if (m.type === "ready") { boot.classList.add("done"); setTimeout(() => boot.remove(), 400); return; }
    if (m.type === "fatal") {
      boot.querySelector(".wb-msg").textContent = "Could not start: " + m.msg;
      boot.querySelector(".wb-note").textContent = "Check the internet connection and reload the page.";
      boot.classList.add("failed");
      return;
    }
    if (m.type === "result") {
      const resolve = pending.get(m.id);
      pending.delete(m.id);
      for (const f of m.out.files || []) showFile(f);
      if (m.out.warning && typeof toast === "function") toast("warning", "Not uploaded yet", m.out.warning, 12000);
      if (resolve) resolve(m.out);
    }
  };

  window.WebBridge = {
    call(method, params) {
      return new Promise((resolve) => {
        const id = ++seq;
        pending.set(id, resolve);
        worker.postMessage({ id, method, params });
      });
    },
  };
})();
