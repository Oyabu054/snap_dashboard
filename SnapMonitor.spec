# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller ビルド設定(単一exe形式)
======================================
ビルド方法:
    pip install pyinstaller
    pyinstaller SnapMonitor.spec

生成物は dist/SnapMonitor.exe。config.txt・box_jwt_config.json は
このexeには含めていない(機密情報のため)。dist フォルダに配布時、
config.txt(config.txt.exampleから作成したもの)・box_jwt_config.json を
SnapMonitor.exe と同じフォルダに配置すること。
"""
from PyInstaller.utils.hooks import collect_submodules

# pymssql/boxsdk/waitressはコンパイル済み拡張・動的インポートを含むため、
# PyInstallerの静的解析だけでは検出しきれないことがある。明示的に収集する
hiddenimports = collect_submodules("pymssql") + collect_submodules("boxsdk") + collect_submodules("waitress")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("templates", "templates"),
        ("static", "static"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SnapMonitor",
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
