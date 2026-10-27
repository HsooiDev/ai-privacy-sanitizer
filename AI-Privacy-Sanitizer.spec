# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct,
)
from src import APP_NAME, __version__

version_tuple = tuple(int(part) for part in __version__.split('.'))
version_tuple = version_tuple + (0,) * (4 - len(version_tuple))
windows_version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple, mask=0x3f,
                      flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('FileDescription', APP_NAME),
        StringStruct('ProductName', APP_NAME),
        StringStruct('InternalName', APP_NAME),
        StringStruct('OriginalFilename', APP_NAME + '.exe'),
        StringStruct('FileVersion', __version__),
        StringStruct('ProductVersion', __version__),
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
)

datas = []
binaries = []
hiddenimports = ['pystray._win32', 'plyer.platforms.win.notification']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]


a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'unittest', 'pdb', 'pydoc'],
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
    name=APP_NAME,
    version=windows_version,
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
    icon=['assets/icon.ico'],
)
