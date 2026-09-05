# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


datas = collect_data_files("bap_desktop", includes=["resources/**", "VERSION"])
datas += collect_data_files("PySide6", includes=["translations/**"])
binaries = collect_dynamic_libs("PySide6", search_patterns=["plugins/platforms/*"])
binaries += collect_dynamic_libs(
    "PySide6",
    search_patterns=[
        "concrt140.dll",
        "msvcp140_codecvt_ids.dll",
        "vccorlib140.dll",
        "vcomp140.dll",
    ],
)

a = Analysis(
    ["../../bap_desktop/app.py"],
    pathex=["../.."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
# Windows ships the ICU compatibility DLLs used by Qt. Do not accidentally
# bundle an unrelated, versioned ICU found on the build runner PATH (for
# example a Poppler runtime), because Qt imports the unversioned Windows API.
a.binaries = [
    entry
    for entry in a.binaries
    if entry[0].lower() not in {"icuuc.dll", "icudt78.dll"}
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BAP",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BAP",
)
