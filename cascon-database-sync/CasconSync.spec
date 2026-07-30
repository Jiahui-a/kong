# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 规格文件：生成无控制台窗口的 CasconSync.exe。

路径一律相对本 spec 所在目录，避免写死某台机器的绝对路径。
入口使用 run_gui.py（绝对导入），不要直接打包 cascon_sync/gui.py。
"""

import os

from PyInstaller.utils.hooks import collect_submodules

# SPECPATH 由 PyInstaller 注入，指向本 .spec 所在目录
spec_dir = SPECPATH  # noqa: F821
entry_script = os.path.join(spec_dir, "run_gui.py")

hiddenimports = collect_submodules("cascon_sync") + collect_submodules("openpyxl")

a = Analysis(  # noqa: F821
    [entry_script],
    pathex=[spec_dir],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CasconSync",
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
