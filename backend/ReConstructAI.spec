# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller packaging for the ReConstructAI desktop application.

Build from the repository root:

    backend\\venv\\Scripts\\python.exe -m PyInstaller backend\\ReConstructAI.spec

The application entry point is ``main.py`` in the repository root, which puts
``backend`` on ``sys.path`` before importing the PySide6 UI. Data files that the
app reads at runtime (storage folders, the model folder) are created next to the
executable's data directory on first run rather than bundled, because they hold
user evidence and are written to at runtime.
"""

import os

block_cipher = None

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
BACKEND = os.path.join(ROOT, "backend")

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[BACKEND, ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        "app",
        "app.ui.main_window",
        "app.ui.evidence",
        "app.ui.analysis_worker",
        "app.core_engine.engine",
        "app.reconstruction.cross_recovery",
        "app.ai.fragment_relevance",
        "app.storage.database",
        "sklearn.neighbors",
        "sklearn.feature_extraction.text",
        "scipy.sparse.csgraph",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "pytest",
        "IPython",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ReConstructAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=bool(os.environ.get("RECONSTRUCTAI_CONSOLE")),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ReConstructAI",
)
