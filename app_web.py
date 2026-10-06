# app_web.py - Entry point for the web-UI version of the Rental Billing Software.
# (main.py still starts the original Tkinter version.)
import os
import sys

# Run from the folder that holds rentals.db, materials.csv and the bill images,
# exactly like the Tkinter app expected.
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Same DPI fix main.py applied, so the window is crisp on scaled displays
if os.name == 'nt':
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

from webapp.server import main

if __name__ == "__main__":
    main()
