// bridge.js - phone/web version: connects the UI to the Python worker (worker.js).
"use strict";
(function () {
  // Android app (Capacitor): engine bundled inside the app, files opened/shared natively
  const NATIVE = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
  const worker = new Worker(NATIVE ? "worker.js?pyodide=local" : "worker.js");
  const pending = new Map();
  let seq = 0;

  // ---- startup screen (Pyodide takes a few seconds the first time, then it is cached)
  const boot = document.createElement("div");
  boot.id = "web-boot";
  boot.innerHTML = '<div class="wb-card"><div class="wb-mark">₹</div><div class="wb-title">Rental Billing</div>' +
    '<div class="wb-msg">Starting…</div><div class="wb-bar"><span></span></div>' +
    '<div class="wb-note">The first start can take up to a minute. After that it opens quickly.</div></div>';
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(boot));

  async function nativeFile(f) {
    // write to the app's cache, then offer Open (PDF viewer) and Share (WhatsApp, print, ...)
    const P = window.Capacitor.Plugins;
    const saved = await P.Filesystem.writeFile({ path: f.name, data: f.b64, directory: "CACHE" });
    const card = document.createElement("div");
    card.className = "pdf-ready";
    card.innerHTML = '<div><b></b><small></small></div><button class="btn primary sm">Open</button>' +
      '<button class="btn sm">Share</button><button class="btn ghost sm" aria-label="Close">✕</button>';
    card.querySelector("b").textContent = f.mime === "text/csv" ? "File ready" : "PDF ready";
    card.querySelector("small").textContent = f.name;
    const [open, share, close] = card.querySelectorAll("button");
    const fail = (e) => { if (typeof toast === "function") toast("error", "Could not open", String(e && e.message || e)); };
    open.onclick = () => P.FileOpener.open({ filePath: saved.uri, contentType: f.mime, openWithDefault: true }).catch(fail);
    share.onclick = () => P.Share.share({ title: f.name, url: saved.uri, dialogTitle: "Share " + f.name }).catch(() => {});
    close.onclick = () => card.remove();
    document.body.appendChild(card);
  }

  function showFile(f) {
    if (NATIVE) { nativeFile(f).catch((e) => typeof toast === "function" && toast("error", "File error", String(e))); return; }
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
