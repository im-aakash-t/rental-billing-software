# tools/build_phone.py - builds the phone/web version into dist_phone/
#
#   python tools/build_phone.py
#
# The output is a plain static website (no server code): upload the dist_phone
# folder to any static host (Netlify, Cloudflare Pages, GitHub Pages, ...).
# It needs internet to run (it talks to Supabase and loads Pyodide from a CDN).
import hashlib
import io
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dist_phone")
# Android app (Capacitor): the Python engine is bundled so the app needs no CDN
NATIVE_OUT = os.path.join(ROOT, "mobile", "www")
PYODIDE_NPM = os.path.join(ROOT, "mobile", "node_modules", "pyodide")
PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/"
PYODIDE_CORE = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]
PYODIDE_PACKAGES = ["sqlite3", "pillow", "micropip", "packaging"]
# Same versions as the desktop app, so PDFs come out the same
WHEELS = ["reportlab==4.3.1", "chardet==5.2.0"]
PY_DIRS = ["", "webapp", "cloud"]
SKIP_PY = {"main.spec"}


def bundle_pyodide(out):
    """Copy the Pyodide engine + the packages the app loads into out/pyodide/."""
    import json
    import urllib.request
    dest = os.path.join(out, "pyodide")
    os.makedirs(dest)
    for f in PYODIDE_CORE:
        shutil.copy(os.path.join(PYODIDE_NPM, f), os.path.join(dest, f))
    with open(os.path.join(PYODIDE_NPM, "pyodide-lock.json"), encoding="utf-8") as fh:
        lock = json.load(fh)["packages"]
    cache = os.path.join(ROOT, "build_web", "pyodide_pkgs")
    os.makedirs(cache, exist_ok=True)
    for name in PYODIDE_PACKAGES:
        fname = lock[name]["file_name"]
        cached = os.path.join(cache, fname)
        if not os.path.exists(cached):
            urllib.request.urlretrieve(PYODIDE_CDN + fname, cached)
        shutil.copy(cached, os.path.join(dest, fname))


def build(native=False):
    global OUT
    if native:
        OUT = NATIVE_OUT
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "py"))
    os.makedirs(os.path.join(OUT, "img"))

    # 1. user interface (same files as the desktop app) + phone bridge/worker
    shutil.copytree(os.path.join(ROOT, "webapp", "static"), os.path.join(OUT, "static"),
                    ignore=shutil.ignore_patterns("index.html"))
    for f in ("bridge.js", "worker.js"):
        shutil.copy(os.path.join(ROOT, "webapp", "phone", f), os.path.join(OUT, f))

    with open(os.path.join(ROOT, "webapp", "static", "index.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace('    window.APP_TOKEN = "__APP_TOKEN__";\n', "")
    html = html.replace('href="/static/', 'href="static/').replace('src="/static/', 'src="static/')
    html = html.replace('<script src="static/logic.js"></script>',
                        '<script src="static/logic.js"></script>\n  <script src="bridge.js"></script>')
    html = html.replace('<meta name="viewport" content="width=device-width, initial-scale=1">',
                        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                        '  <meta name="theme-color" content="#0E1420">\n'
                        '  <meta name="apple-mobile-web-app-capable" content="yes">\n'
                        '  <meta name="mobile-web-app-capable" content="yes">\n'
                        '  <link rel="manifest" href="manifest.webmanifest">\n'
                        '  <link rel="icon" href="icon-192.png">\n'
                        '  <link rel="apple-touch-icon" href="icon-192.png">')
    assert "bridge.js" in html and "manifest.webmanifest" in html
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # 2. the app's Python code (same files the desktop runs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in PY_DIRS:
            folder = os.path.join(ROOT, d)
            for name in sorted(os.listdir(folder)):
                if name.endswith(".py") and name not in SKIP_PY:
                    z.write(os.path.join(folder, name), (d + "/" if d else "") + name)
        z.write(os.path.join(ROOT, "materials.csv"), "materials.csv")
    data = buf.getvalue()
    with open(os.path.join(OUT, "py", "app.zip"), "wb") as f:
        f.write(data)

    # 3. pure-Python wheels for PDFs
    subprocess.check_call([sys.executable, "-m", "pip", "download", "--no-deps", "-q", "-d",
                           os.path.join(OUT, "py")] + WHEELS)
    wheels = sorted(w for w in os.listdir(os.path.join(OUT, "py")) if w.endswith(".whl"))
    assert all(w.endswith("py3-none-any.whl") for w in wheels), wheels
    with open(os.path.join(OUT, "py", "wheels.txt"), "w") as f:
        f.write("\n".join(wheels))
    version = hashlib.sha1(data + "".join(wheels).encode()).hexdigest()[:12]
    with open(os.path.join(OUT, "py", "version.txt"), "w") as f:
        f.write(version)

    # 4. bill backgrounds used by the PDF printer
    for name in ("bill-layout.jpg", "Estimate-Bill.png", "Tax-Invoice.png"):
        shutil.copy(os.path.join(ROOT, name), os.path.join(OUT, "img", name))

    # 5. home-screen icon + manifest
    from PIL import Image
    with Image.open(os.path.join(ROOT, "webapp", "app.ico")) as im:
        im = im.convert("RGBA")
        for size in (192, 512):
            im.resize((size, size), Image.LANCZOS).save(os.path.join(OUT, f"icon-{size}.png"))
    with open(os.path.join(OUT, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        f.write('{"name": "Rental Billing", "short_name": "Rental Billing", "start_url": "./", "display": "standalone",'
                ' "background_color": "#0B1020", "theme_color": "#0E1420",'
                ' "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},'
                ' {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}]}')

    if native:
        bundle_pyodide(OUT)

    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT) for f in fs)
    print(f"Built {OUT}  (version {version}, {total / 1024 / 1024:.1f} MB, wheels: {', '.join(wheels)})")


if __name__ == "__main__":
    build(native="--android" in sys.argv)
