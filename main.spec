# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('bill-layout.jpg', '.'), ('Estimate-Bill.png', '.'), ('Tax-Invoice.png', '.'), ('materials.csv', '.')],
    hiddenimports=['form_tab', 'partial_returns_tab', 'pending_tab', 'daily_report_tab', 'customer_report_tab', 'materials_report_tab', 'analytics_dashboard', 'customers_tab', 'scanner_helper', 'googleapiclient', 'google.oauth2'],
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
    name='main',
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
