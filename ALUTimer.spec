# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ALU Timing Tool v5.

Build with:
    pyinstaller ALUTimer.spec

Produces:
    dist/ALU Timer.exe      (standalone single-file executable)

At runtime the exe creates a "runs/" folder next to itself for
ghost saves and config (ui_config.json).  No other external files needed.
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],                # No external data bundled — runs/ created at runtime
    hiddenimports=[
        'pymem',
        'pymem.process',
        'pymem.pattern',
        'win32api',
        'win32gui',
        'win32con',
        'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unnecessary large packages to keep the build smaller
        'matplotlib',
        'scipy',
        'pandas',
        'PIL',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ALU Timer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,           # No console window — GUI only
    disable_windowed_traceback=False,
    icon='assets\\icon.ico',
    uac_admin=True,          # Request admin privileges (needed for process memory access)
)

