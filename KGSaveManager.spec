# -*- mode: python ; coding: utf-8 -*-
# KGSaveManager（主版本：HTML 界面）PyInstaller 配置
# - 界面为 webapp/assets 下的 HTML/CSS/JS，由本地 HTTP 服务发给浏览器
# - datas：docs（离线文档）与 webapp/assets（前端资源）都要带上
# - console=True：启动时会打印页面地址，便于排错；改窗口模式时记得把地址显示到页面里
# - upx=False：不依赖外部 UPX 压缩工具

a = Analysis(
    ['KGSaveManager.py'],
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
    name='KGSaveManager',
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
    name='KGSaveManager',
)
