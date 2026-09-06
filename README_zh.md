# KGSaveManager（中文版）

Kittens Game 存档管理器（Windows，Python + Tkinter，零第三方依赖）。

## 功能

- 中英双语界面；首次运行时按系统语言自动选择
- 标签页固定顺序：KGSM、启动游戏、存档管理、修改存档、下载游戏、配置
- 存档管理：10 个存档位，按文件名（`名字_1.kgsav`…`名字_10.kgsav`）识别；自动存档（WebSocket 桥）、手动存档（放文件或粘贴文本）、复制存档、自动读档、改名、刷新、槽位备注、检查异常文件
- 修改存档：可打开槽位文件或运行中的游戏；视图/源码两种显示；数值编辑；打开前自动备份（.bak）；写回时按游戏格式重新压缩
- 启动游戏：本地静态 Web 服务（仅 127.0.0.1）并注入存档桥；以新窗口打开游戏
- 下载游戏：两个 GitHub 仓库；GitHub 直连或镜像源；连通性测试；解压摊平并校验根目录存在 index.html
- 配置：语言、浏览器、游戏目录、端口、首页指定存档；修改自动保存
- 外部翻译：支持程序目录下 `i18n/` 文件夹中的 JSON 与 PO 文件
- 运行数据集中在 `kgsm_data/`；运行日志位于 `kgsm_data/kgsm_log/`，每次启动一个文件

## 运行

```powershell
python KGSaveManager.py
```

## 快速开始

1. 下载游戏（下载游戏页，保持默认仓库与版本）。
2. 在配置页设置游戏目录（包含 index.html 的文件夹）。
3. 启动游戏（启动游戏页）。页面会自动连接存档桥。
4. 在存档管理页执行存档或读档。

## 使用

- 自动存档：需要游戏由 KGSM 启动且已连接；把游戏当前存档写入选中槽位，覆盖时先确认。
- 手动存档：对话框上部为临时文件夹路径（可复制），下部为文本输入区；把导出的存档文件放入临时文件夹，或粘贴文本后点「确定」。粘贴内容会先校验。
- 复制存档：把槽位内容复制到剪贴板，用于游戏导入。
- 自动读档：确认一次后把槽位内容发送到游戏页面，页面自动刷新载入。
- 改名：重命名槽位文件；槽位需先有存档。
- 刷新：重新扫描存档库。
- 修改存档：打开文件或实时源后编辑；视图模式改数值，源码模式改 JSON；写入即保存结果。

## 目录结构

```
程序目录/
├─ KGSaveManager.py
├─ i18n.py / config_store.py / web_server.py / web_bridge.py
├─ savecodec.py / downloader.py
├─ pages_download.py / pages_editor.py / save_flows.py
├─ kgsm_logging.py / utils.py
├─ docs/guide_en.html
└─ kgsm_data/
   ├─ kittens_saves/
   ├─ kgsm_temp/
   ├─ kgsm_log/
   └─ kgsm_config.json
```

## 打包

```powershell
pip install pyinstaller
pyinstaller KGSaveManager.spec
```

产物：`dist/KGSaveManager/KGSaveManager.exe`。
