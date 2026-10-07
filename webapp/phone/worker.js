// worker.js - runs the app's Python (Pyodide) off the main thread for the phone/web version.
/* global importScripts, loadPyodide */
"use strict";
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
importScripts(PYODIDE + "pyodide.js");

// Synchronous HTTP for Python (cloud/client.py -> _send_browser). Allowed inside workers.
self.pyHttp = (method, url, headersJson, body) => {
  try {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url, false);
    const headers = JSON.parse(headersJson);
    for (const k of Object.keys(headers)) xhr.setRequestHeader(k, headers[k]);
    xhr.send(body ? body : null);
    if (xhr.status === 0) return { error: "network error" };
    return { status: xhr.status, text: xhr.responseText, ctype: xhr.getResponseHeader("Content-Type") || "" };
  } catch (e) {
    return { error: String(e && e.message || e) };
  }
};

let py = null, rt = null, imagesReady = false;
const PRINTS = new Set(["print_bill", "return_print"]);

async function persist() {
  await new Promise((res) => py.FS.syncfs(false, () => res()));
}

async function boot() {
  const step = (msg) => self.postMessage({ type: "progress", msg });
  step("Loading the app engine…");
  py = await loadPyodide({ indexURL: PYODIDE });
  step("Loading database & PDF tools…");
  await py.loadPackage(["sqlite3", "Pillow", "micropip"]);
  const v = (await (await fetch("py/version.txt", { cache: "no-store" })).text()).trim();
  const zip = await (await fetch("py/app.zip?v=" + v)).arrayBuffer();
  py.unpackArchive(zip, "zip", { extractDir: "/app" });
  const wheels = (await (await fetch("py/wheels.txt?v=" + v)).text()).trim().split("\n");
  const micropip = py.pyimport("micropip");
  await micropip.install(wheels.map((w) => new URL("py/" + w, self.location).href), { deps: false });
  step("Opening saved data…");
  py.FS.mkdirTree("/data");
  py.FS.mount(py.FS.filesystems.IDBFS, {}, "/data");
  await new Promise((res) => py.FS.syncfs(true, () => res()));
  py.runPython("import sys; sys.path.insert(0, '/app')");
  rt = py.pyimport("webapp.web_runtime");
  self.postMessage({ type: "ready" });
}

async function loadBillImages() {
  if (imagesReady) return;
  for (const name of ["bill-layout.jpg", "Estimate-Bill.png", "Tax-Invoice.png"]) {
    const buf = new Uint8Array(await (await fetch("img/" + name)).arrayBuffer());
    py.FS.writeFile("/app/" + name, buf);
  }
  imagesReady = true;
}

const booting = boot().catch((e) => self.postMessage({ type: "fatal", msg: String(e && e.message || e) }));

// Requests are handled strictly one after another (like the desktop's single DB thread)
let queue = Promise.resolve();
self.onmessage = (ev) => {
  queue = queue.then(() => handle(ev.data));
};
async function handle({ id, method, params }) {
  await booting;
  let out;
  try {
    if (PRINTS.has(method)) await loadBillImages();
    out = JSON.parse(rt.call(method, JSON.stringify(params || {})));
    await persist();                   // keep this phone's copy saved in the browser
  } catch (e) {
    out = { ok: false, error: { title: "Error", message: String(e && e.message || e), kind: "error" } };
  }
  self.postMessage({ type: "result", id, out });
}
