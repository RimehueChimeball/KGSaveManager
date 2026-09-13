# -*- mode: python ; coding: utf-8 -*-
# KGSaveManager（HTML 版）PyInstaller 配置
# - 与 Tkinter 版共用 core/，界面为 webapp/assets 下的 HTML/CSS/JS
# - 打包后 exe 名建议带 -web 后缀，便于与 Tkinter 版并列分发
# - datas：docs（离线文档）与 webapp/assets（前端资源）都要带上
# - upx=False：不依赖外部 UPX 压缩工具

a = Analysis(
    ['KGSaveManagerWeb.py'],
    pathex=[],
    binaries=[],
    datas=[('docs', 'docs'),
           ('webapp/assets', 'webapp/assets')],
    hiddenimports=['i18n', 'config_store', 'web_server', 'utils',
                   'web_bridge', 'savecodec', 'downloader', 'kgsm_logging',
                   'core', 'core.app', 'core.ui_port', 'core.slots',
                   'core.flows', 'core.paths', 'core.server', 'core.download',
                   'core.editor', 'webapp', 'webapp.api', 'webapp.server'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KGSaveManagerWeb',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    name='KGSaveManagerWeb',
)
