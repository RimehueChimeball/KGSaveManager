# KGSaveManager（中文版）

Kittens Game 存档管理器（Windows，Python + Tkinter，零第三方依赖）。

## 功能

- 四标签页，固定顺序：KGSM → 启动游戏 → 存档管理 → 配置（界面中/英可切换）
- 存档管理：10 个存档位，自动按文件名 `名字_槽位号.kgsav` 识别；支持存档/读档、改名（仅改磁盘文件）、手动刷新、备注自动保存、检查异常文件
- 启动游戏：本地静态 Web 服务（仅绑定 127.0.0.1），一键启动并在浏览器新窗口打开，含实时服务日志
- KGSM 首页：快速启动游戏；复制存档并启动；两个游戏下载链接（作者原版 / 社区版，均来自 GitHub）
- 配置：语言、浏览器（默认自动检测系统默认浏览器）、游戏目录、端口、首页指定存档；修改自动保存到 `kgsm_data/kgsm_config.json`
- 数据集中在 `kgsm_data/`（存档库/临时目录/配置），备份或迁移只复制该文件夹

## 运行

```powershell
python KGSaveManager.py
```

## 使用

- 存档：选存档位 → 点「存档」→ 在游戏 Export 对话框粘贴程序复制的路径并保存为 .txt
- 读档：选存档位 → 点「读档」→ 在游戏 Import 中粘贴 (Ctrl+V)
- 改名：需要该位已有存档；改名 = 重命名磁盘文件（`新名字_槽位号.kgsav`），不含存档文件的空槽位请先存档
- 刷新：程序外部放入/改名文件后，点「刷新」重新扫描存档库
- 启动游戏：先在配置页设置游戏目录（指向游戏文件所在文件夹）
- 首次使用：到配置页设置游戏目录，并在 KGSM 页下载游戏

## 目录结构

```
KGSaveManager/
├─ KGSaveManager.py     # 主程序
├─ i18n.py              # 中/英翻译
├─ config_store.py      # 配置读写（自动保存）
├─ web_server.py        # 本地 Web 服务
├─ utils.py             # Windows DPI 设置
├─ KGSaveManager.spec   # PyInstaller 配置
├─ README.md (en) / README_zh.md (zh)
└─ kgsm_data/           # 运行期数据（git 忽略）
   ├─ kittens_saves/    # 存档库
   ├─ kgsm_temp/        # 导出中转目录
   └─ kgsm_config.json  # 配置（备注也在其中）
```

## 打包

```powershell
pip install pyinstaller
pyinstaller KGSaveManager.spec
```

产物在 `dist/KGSaveManager/`。

## 说明

- 槽位名取自存档文件名，不随界面语言翻译（文件名即真实存档文件名）。
- 存档保存 = 游戏导出到临时目录后，程序移动、重命名并覆盖写入存档库。
