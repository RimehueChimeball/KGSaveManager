# KGSaveManager

一个基于 Tkinter 的《Kittens Game》桌面伴侣：多存档位管理、中/英界面，内置本地静态 Web 服务（http.server + socketserver），一键启动游戏并在浏览器新窗口打开。

> 仅面向 Windows 环境开发与使用。

## 功能特性

- 四标签页，固定顺序：**KGSM → 启动游戏 → 存档管理 → 配置**
- KGSM 页：快速启动游戏；复制存档并启动（最近存档 / 首页指定存档可选）
- 启动游戏页：本地 Web 服务（仅绑定 127.0.0.1），一键启动并打开浏览器，实时服务日志（仅启动游戏时新建浏览器窗口，超链接常规打开）
- 存档管理页：6 个存档位，存/读档、备注自动保存、检查异常文件
- 配置页：Language（固定英文标签）、浏览器（首次初始化自动检测系统默认浏览器）、游戏目录、固定端口、首页指定存档，**修改自动保存**到 `kgsm_data/kgsm_config.json`；底部「关于」含项目与作者 GitHub 链接
- 文件校验：接收存档前校验非空、限制体积，等待导出文件写入完成
- 剪贴板容错：`pyperclip` 未安装时自动回退 Tkinter 剪贴板
- 数据集中：存档/配置全部在 `kgsm_data/`，备份或迁移只移动它

## 环境要求

- Windows
- Python 3.8+（含 `tkinter`）
- 可选依赖：`pyperclip`（不装也能运行）

## 安装与运行

```powershell
pip install -r requirements.txt   # 可选依赖
python KGSaveManager.py
```

## 使用说明

### KGSM（首页）

- **快速启动游戏**：要求已设置游戏目录，运行后起服务并在浏览器新窗口打开。
- **复制存档并启动游戏**：先选「最近存档」或「指定存档」（指定存档 = 配置页所选存档位；显示存档名，空则显示「（空）」），点击「运行」：所选存档为空或游戏目录未设置时会报错。
- 底部：「第一次使用？[配置程序]」按钮跳到配置页；两个「下载游戏」GitHub 链接（kitten-science / nuclear-unicorn）。

### 启动游戏

1. 设置服务目录（默认空；也可在配置页设「游戏目录」，两者同一值）；
2. 端口留空 = 自动选择空闲端口；
3. 「🚀 启动并打开浏览器」；「停止服务」随时停止。服务仅本机可访问。

### 存档管理

1. 「存档」：选中存档位 → 点存档 → 在游戏 Export 对话框中粘贴临时目录路径保存；
2. 「读档」：点读档 → 在游戏 Import 中粘贴（Ctrl+V）；
3. 备注在输入框填写即自动保存；「检查异常文件」查看不合规文件。

### 配置

语言切换立即生效并重建界面；浏览器、游戏目录、固定端口、首页指定存档修改后自动写入配置文件（浏览器可手动选择 exe 或恢复系统默认）。

## 目录结构

```
KGSaveManager/
├─ KGSaveManager.py       # 主程序（GUI + 存档逻辑）
├─ i18n.py                # 中/英翻译模块
├─ config_store.py        # 配置读写（自动保存、旧结构迁移）
├─ web_server.py          # 本地静态 Web 服务 + 浏览器打开
├─ utils.py               # Windows DPI / 高清缩放设置
├─ KGSaveManager.spec     # PyInstaller 打包配置
├─ requirements.txt       # 依赖清单
├─ README.md
├─ web_test/              # 测试用示例站点目录（_test 结尾，git 忽略）
└─ kgsm_data/             # 运行期个人数据（git 忽略）
   ├─ kittens_saves/      # 存档库
   ├─ kgsm_temp/          # 临时目录，接收游戏导出文件
   └─ kgsm_config.json    # 配置与备注（自动生成）
```

## 打包为可执行文件

```powershell
pip install pyinstaller
pyinstaller KGSaveManager.spec
```

打包产物输出到 `dist/KGSaveManager/`。

## 说明

- 仓库约定：临时/测试内容一律以 `_test` 结尾并被 git 忽略；`项目计划书.md` 为本地规划文档，不入库。
- 游戏下载链接为 `KGSaveManager.py` 顶部常量 `GAME_DOWNLOAD_URLS`（两个来源），可自行更换。
- 存档内容为游戏自身导出数据，本工具仅做归档与剪贴板中转，不做加密；「读档/复制存档」会把内容放入系统剪贴板，请勿在不受信任的环境使用。
