# -*- mode: python ; coding: utf-8 -*-
# KGSaveManager PyInstaller 配置（模块：i18n/config_store/web_server/web_bridge/savecodec/utils）
# - console=False：GUI 程序不弹出控制台
# - hiddenimports：显式声明拆分的模块，避免“仅运行时局部导入”导致漏包
#   （web_server.open_in_browser 在函数内 import config_store）
# - upx=False：不依赖外部 UPX 压缩工具，避免构建告警（体积差异可忽略）

a = Analysis(
    ['KGSaveManager.py'],
    pathex=[],
    binaries=[],
    datas=[('docs', 'docs')],
    hiddenimports=['i18n', 'config_store', 'web_server', 'utils',
                   'web_bridge', 'savecodec', 'downloader', 'kgsm_logging',
                   'pages_download', 'pages_editor', 'save_flows'],
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
    name='KGSaveManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name='KGSaveManager',
)
