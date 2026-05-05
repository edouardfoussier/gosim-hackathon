# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_submodules

datas = []
binaries = []
hiddenimports = ['overlay', 'overlay.__main__', 'overlay.glyph', 'overlay.ws_client', 'overlay.ns_panel']
datas += collect_data_files('overlay')
binaries += collect_dynamic_libs('PyQt6')
hiddenimports += collect_submodules('overlay')
hiddenimports += collect_submodules('PyQt6')


a = Analysis(
    ['/Users/edouardfoussier/code/gosim-hack/desktop/scripts/_pyinstaller_overlay_entry.py'],
    pathex=['/Users/edouardfoussier/code/gosim-hack'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='xiexie-overlay',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='xiexie-overlay',
)
app = BUNDLE(
    coll,
    name='xiexie-overlay.app',
    icon=None,
    bundle_identifier=None,
)
