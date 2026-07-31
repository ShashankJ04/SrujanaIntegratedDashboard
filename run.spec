# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller run.spec
# Place a `.env` file next to the generated executable (same folder as Operations.exe).
#
# Shipped via datas: templates/, static/ only (UI assets).
# Operational JSON (reports, rbac, etc.) is NOT bundled — at runtime the exe reads
# APP_DATA_DIR from .env (e.g. .\data next to the exe).
# NOT bundled (PM date OCR / ML dev — other branch): models/, notebooks/, tests/,
# pm_date_training.zip, backend/pm_date_*.py (not imported by run.py → app).

_PM_DATE_EXCLUDES = [
    'backend.pm_date_crop',
    'backend.pm_date_extractor',
    'backend.pm_date_lite',
    'backend.pm_date_model',
    'backend.pm_date_parse',
    # Heavy ML stacks — only needed for pm_date_* dev, never for Operations.exe
    'torch',
    'torchvision',
    'transformers',
    'onnxruntime',
    'paddleocr',
    'paddle',
]

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=[('templates', 'templates'), ('static', 'static'), ('data/overview_reports_seed.json', 'data')],
    hiddenimports=['dotenv', 'waitress', 'pymysql'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_PM_DATE_EXCLUDES,
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
    name='Operations',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
