# -*- mode: python ; coding: utf-8 -*-
# KGSaveManager Lite（Tkinter 界面）PyInstaller 配置
# - 与主版本共用 core/，界面是 Tkinter（标准库），适合只想用经典窗口的用户
# - console=False：GUI 程序不弹出控制台
# - hiddenimports：显式声明拆分的模块（含 core 逻辑层与 Tkinter 界面端口实现），
#   避免“仅运行时局部导入”导致漏包（web_server.open_in_browser 在函数内
#   import config_store）
# - upx=False：不依赖外部 UPX 压缩工具，避免构建告警（体积差异可忽略）

a = Analysis(
    ['KGSaveManagerLite.py'],
    pathex=[],
    binaries=[],
    datas=[('docs', 'docs')],
    hiddenimports=['i18n', 'config_store', 'web_server', 'utils',
                   'web_bridge', 'savecodec', 'downloader', 'kgsm_logging',
                   'pages_download', 'pages_editor', 'pages_manual',
                   'ui_tk', 'core', 'core.app', 'core.ui_port', 'core.slots',
                   'core.flows', 'core.paths', 'core.server', 'core.download',
                   'core.editor'],
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
    name='KGSaveManagerLite',
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
    name='KGSaveManagerLite',
)
