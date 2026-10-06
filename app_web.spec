# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build for the web-UI version:  pyinstaller app_web.spec
# Like main.exe, RentalBilling.exe reads rentals.db, materials.csv, the bill
# images, credentials.json/token.json and ID_Proofs from the folder it sits in.

a = Analysis(
    ['app_web.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('webapp/static', 'webapp/static'),
        ('webapp/app.ico', 'webapp'),
        ('bill-layout.jpg', '.'), ('Estimate-Bill.png', '.'), ('Tax-Invoice.png', '.'), ('materials.csv', '.'),
    ],
    hiddenimports=[
        'form_tab', 'partial_returns_tab', 'pending_tab', 'daily_report_tab', 'customer_report_tab',
        'materials_report_tab', 'analytics_dashboard', 'customers_tab', 'scanner_helper',
        'googleapiclient', 'google.oauth2', 'google_auth_oauthlib', 'win32com', 'win32com.client', 'pythoncom',
        'clr', 'webview.platforms.winforms', 'webview.platforms.edgechromium',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RentalBilling',
    icon='webapp/app.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
