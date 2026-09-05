# KGSaveManager

一个基于 Tkinter 的《Kittens Game》存档管理器，用于管理多个存档位、为每个存档位保存备注，并衔接游戏内的导入（Import）/ 导出（Export）流程。

> 仅面向 Windows 环境开发与使用。

## 功能特性

- 6 个存档位，每个存档位独立显示存档时间与备注。
- 备注与配置自动持久化到 `kgsm_data/kgsm_config.json`，重启程序不丢失。
- 数据目录统一：存档库、临时目录、配置文件都集中在 `kgsm_data` 下，**备份 / 迁移只需复制这一个文件夹**。
- 「存档」：导出游戏存档到临时目录，自动检测并归档到存档库。
- 「读档」：将存档内容复制到剪贴板，方便粘贴进游戏导入。
- 「检查异常文件」：列出存档库与临时目录中不被程序管理的文件，以及内容为空的存档。
- 文件校验：接收存档前校验非空、限制体积，并等待文件写入完成，避免拿到半成品。
- 剪贴板容错：优先使用 `pyperclip`，未安装时自动回退到 Tkinter 自带剪贴板。
- 路径稳健：所有数据文件基于程序所在目录解析，兼容源码运行与 PyInstaller 打包。

## 环境要求

- Windows
- Python 3.8+（含 `tkinter`，通常随 Python 标准库自带）
- 可选依赖：`pyperclip`（不装也能运行，会自动回退）

## 安装与运行

```powershell
# 安装可选依赖（推荐）
pip install -r requirements.txt

# 运行
python KGSaveManager.py
```

## 使用说明

### 存档（导出）

1. 在右侧选择一个存档位，可先填写备注。
2. 点击「存档」。
3. 程序会把临时目录的路径复制到剪贴板。
4. 在游戏 `Options → Export` 的保存对话框中粘贴该路径，并保存为 `.txt` 文件。
5. 程序检测到新文件后会自动归档到存档库。

### 读档（导入）

1. 选择一个已有存档的存档位。
2. 点击「读档」，存档内容会被复制到剪贴板。
3. 在游戏 `Options → Import` 中粘贴（Ctrl+V）并确认。

### 检查异常文件

点击「检查异常文件」可查看存档库与临时目录中不被程序管理的文件，自行决定是否清理。

## 目录结构

```
KGSaveManager/
├─ KGSaveManager.py       # 主程序
├─ utils.py               # Windows DPI / 高清缩放设置
├─ KGSaveManager.spec     # PyInstaller 打包配置
├─ requirements.txt       # 依赖清单
├─ README.md
└─ kgsm_data/             # 程序数据目录（运行时自动创建，git 已忽略）
   ├─ kittens_saves/      # 存档库
   ├─ kgsm_temp/          # 临时目录，接收游戏导出文件
   └─ kgsm_config.json    # 配置与备注文件（保存备注后自动生成）
```

> `kgsm_data` 已在 `.gitignore` 中忽略，个人存档与配置不会被提交到仓库；换机或备份时只需复制该文件夹。

## 打包为可执行文件

```powershell
pip install pyinstaller
pyinstaller KGSaveManager.spec
```

打包产物输出到 `dist/KGSaveManager/`。

## 说明

- 存档内容是游戏自身的导出数据，本工具仅做归档与剪贴板中转，不做加密；请勿在不受信任的环境中使用「读档」功能（剪贴板内容可被其他进程读取）。
- 程序不会自动删除任何文件，异常文件由你在「检查异常文件」中自行决定处理。
