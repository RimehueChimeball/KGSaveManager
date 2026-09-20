# KGSaveManager（中文版）

Kittens Game 存档管理器（Windows，Python 编写，零第三方依赖）。

两套前端共用同一套逻辑层与同一份 `kgsm_data/`：
- **主版本 · HTML 界面**（`KGSaveManager.py` + `webapp/`）——界面是本地网页，
  以浏览器应用窗口打开；窗口标题与图标由页面决定（`<title>`、`favicon.ico`、
  `manifest.webmanifest`），也可以在浏览器菜单里把它装成独立应用。
- **Tk 版 · Tkinter 界面**（`KGSaveManagerTk.py`）——经典桌面窗口，界面自身不依赖
  浏览器、也不开放本地端口（选文件夹用系统对话框；游戏本身仍是网页，仍需浏览器打开），
  适合偏好传统窗口或机器上没有 Edge/Chrome 的情况。

## 功能

- 中英双语界面；首次运行时按系统语言自动选择
- 标签页固定顺序：KGSM、启动游戏、存档管理、修改存档、下载游戏、配置
- 存档管理：10 个存档位，按文件名（`名字_1.kgsav`…`名字_10.kgsav`）识别；自动存档（WebSocket 桥）、手动导入（选文件或粘贴文本）、复制存档、自动读档、改名、刷新、槽位备注、检查异常文件
- 修改存档：可打开槽位文件或运行中的游戏；视图/源码两种显示；数值编辑；打开前自动备份（.bak）；写回时按游戏格式重新压缩
- 启动游戏：本地静态 Web 服务（仅 127.0.0.1）并注入存档桥；以新窗口打开游戏；桥会在日志中标注存档来自游戏引擎还是浏览器自动保存快照
- 下载游戏：两个 GitHub 仓库；GitHub 直连或镜像源；连通性测试；解压摊平并校验根目录存在 index.html
- 配置：语言、浏览器、游戏目录、端口、默认存档位（启动时选中）；修改自动保存
- 外部翻译：支持程序目录下 `i18n/` 文件夹中的 JSON 与 PO 文件
- 运行数据集中在 `kgsm_data/`；运行日志位于 `kgsm_data/kgsm_log/`，每次启动一个文件
- 分层结构：`core/` 存放全部与界面无关的逻辑，只通过界面端口（`core/ui_port.py`）与屏幕交互，因此另一套前端（例如 HTML/webview 界面）可以原样复用

## 运行

```powershell
python KGSaveManager.py        # 主版本（HTML 界面，自动打开浏览器应用窗口）
python KGSaveManagerTk.py     # Tk 版（Tkinter 界面）
```

主版本支持 `--port N`、`--no-browser`、`--verbose`；启动时会打印页面地址，地址后加
`?selftest=1` 可跑它的自检。退出只有两种方式：页面里的「退出」按钮，或 Ctrl+C；
它不会因为页面停止响应而自行退出（浏览器会把隐藏窗口的定时器降频到约每分钟一次）。

## 快速开始

1. 下载游戏（下载游戏页，保持默认仓库与版本）。
2. 在配置页设置游戏目录（包含 index.html 的文件夹）。
3. 启动游戏（启动游戏页）。页面会自动连接存档桥。
4. 在存档管理页执行存档或读档。

## 使用

- 自动存档：需要游戏由 KGSM 启动且已连接；把游戏当前存档写入选中槽位，覆盖时先确认。
- 手动导入：对话框显示存档库文件夹路径（可复制）；点「浏览选择存档文件」选择游戏导出的存档文件，或把存档文本粘贴到输入框后点「确定」。写入前会校验内容，你选的文件不会被删除或改动，覆盖槽位前会把原存档备份到 `kgsm_data/backups/`。
- 复制存档：把槽位内容复制到剪贴板，用于游戏导入。
- 自动读档：确认一次后把槽位内容发送到游戏页面，页面自动刷新载入；未收到页面确认时会明确提示。
- 改名：重命名槽位文件；槽位需先有存档。存档归属哪个槽位由文件名（`名字_1.kgsav`…`名字_10.kgsav`）决定，所以在文件管理器里改过的名字点「刷新」即可生效。
- 刷新：重新扫描存档库。
- 修改存档：打开文件或实时源后编辑；视图模式改数值，源码模式改 JSON；写入即保存结果。

## 目录结构

```
程序目录/
├─ KGSaveManager.py              主版本入口（HTML 界面）
├─ KGSaveManagerTk.py            Tk 版入口（Tkinter 界面）
├─ i18n.py / config_store.py / web_server.py / web_bridge.py
├─ savecodec.py / downloader.py
├─ pages_download.py / pages_editor.py / pages_manual.py  (Tkinter 视图)
├─ ui_tk.py                      Tkinter 界面端口实现
├─ core/                         与界面无关的逻辑（paths / slots / flows /
│                                server / download / editor / ui_port / app）
├─ webapp/                       HTML 版后端（api.py、server.py）
│   └─ assets/                   index.html / app.js / style.css / selftest.js
├─ kgsm_logging.py / utils.py
├─ docs/guide_en.html / docs/guide_zh.html
├─ CHANGELOG.md / CHANGELOG_zh.md
├─ tests/                单元测试（仅标准库）
└─ kgsm_data/
   ├─ kittens_saves/
   ├─ backups/
   ├─ kgsm_log/
   └─ kgsm_config.json
```

## 测试

```powershell
python -m unittest discover -s tests -t .
```

覆盖存档编解码（有 Node.js 与游戏源码时还会与游戏自带 `lib/lz-string.js` 做一致性对照）、下载解压与镜像配置、WebSocket 桥协议与保活、注入脚本（DOM 元素误判、引擎晚到、存档来源标注）、core 逻辑层（槽位、存档流程、编辑器、下载、服务/桥）、HTML 后端（真起 HTTP 服务跑一遍 API 与对话框往返）、翻译表（同时扫描 Python 与前端资源）；装了 Edge/Chrome 时还会用无头浏览器跑一遍 HTML 界面的自检。出现未使用的导入、没有被调用的函数或没有引用的翻译键时测试同样失败。

## 打包

```powershell
pip install pyinstaller
pyinstaller KGSaveManager.spec        # dist/KGSaveManager/KGSaveManager.exe（主版本）
pyinstaller KGSaveManagerTk.spec      # dist/KGSaveManagerTk/KGSaveManagerTk.exe（Tk）
```

产物：主版本 `dist/KGSaveManager/KGSaveManager.exe`（已把 `webapp/assets` 打进包）；
Tk 版 `dist/KGSaveManagerTk/KGSaveManagerTk.exe`。

## 许可

MIT License，见 [LICENSE](LICENSE)。Copyright (c) 2026 RimehueChimeball。
