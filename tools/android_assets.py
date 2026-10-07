# tools/android_assets.py - app icon + splash screen for the Android app (from webapp/app.ico)
#   python tools/android_assets.py
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "mobile", "android", "app", "src", "main", "res")
BG = (11, 11, 11)          # #0B0B0B, the app's sidebar colour

with Image.open(os.path.join(ROOT, "webapp", "app.ico")) as im:
    icon = im.convert("RGBA").resize((512, 512), Image.LANCZOS)

# Legacy + round launcher icons
for folder, size in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
    out = os.path.join(RES, f"mipmap-{folder}")
    icon.resize((size, size), Image.LANCZOS).save(os.path.join(out, "ic_launcher.png"))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    rnd = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rnd.paste(icon.resize((size, size), Image.LANCZOS), (0, 0), mask)
    rnd.save(os.path.join(out, "ic_launcher_round.png"))
    # Adaptive icon foreground: 108dp canvas, artwork in the central ~66%
    fg_size = int(size * 108 / 48)
    fg = Image.new("RGBA", (fg_size, fg_size), (0, 0, 0, 0))
    art = int(fg_size * 0.66)
    fg.paste(icon.resize((art, art), Image.LANCZOS), ((fg_size - art) // 2, (fg_size - art) // 2))
    fg.save(os.path.join(out, "ic_launcher_foreground.png"))

with open(os.path.join(RES, "values", "ic_launcher_background.xml"), "w", encoding="utf-8") as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
            '    <color name="ic_launcher_background">#0B0B0B</color>\n</resources>\n')

# Splash screens: dark background with the icon in the middle
for dirpath, _, files in os.walk(RES):
    if "splash.png" in files:
        path = os.path.join(dirpath, "splash.png")
        with Image.open(path) as old:
            w, h = old.size
        splash = Image.new("RGB", (w, h), BG)
        s = max(48, min(w, h) // 4)
        splash.paste(icon.resize((s, s), Image.LANCZOS), ((w - s) // 2, (h - s) // 2), icon.resize((s, s), Image.LANCZOS))
        splash.save(path)
print("Android icons and splash screens written")
