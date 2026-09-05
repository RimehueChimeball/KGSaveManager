"""
KittensGame 存档管理器 (KGSaveManager)
======================================

基于 Tkinter 的《Kittens Game》桌面伴侣：存档管理、备注与配置持久化、
一键本地 Web 服务（http.server + socketserver）启动游戏。

功能特性：
1. 备注与配置持久化：kgsm_data/kgsm_config.json（原子写入，自动保存）。
2. 数据目录统一：kgsm_data 收纳存档库/临时目录/配置文件，备份只移动它。
3. 线程安全：后台监控与界面通过事件队列通信，不跨线程操作 UI。
4. 文件校验：接收存档前校验非空、限体积，等待导出文件写入稳定。
5. 剪贴板：内置 tkinter 剪贴板实现，零第三方依赖。
6. 中英翻译：无配置文件时按系统语言探测，配置页可切换，自动保存。
7. 四标签页：KGSM（快速启动/复制存档并启动）、启动游戏（Web 服务）、
   存档管理（存档位）、配置（语言/游戏目录/固定端口/首页指定存档）。

模块拆分：i18n.py（翻译）、config_store.py（配置）、
web_server.py（本地 Web 服务）、utils.py（DPI）。
"""

import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

from config_store import AppConfig
from i18n import LANG_EN, LANG_ZH, Translator
from utils import setup_dpi_and_scaling
from web_server import LocalWebServer, open_in_browser

# ==================== 配置 ====================
APP_NAME = "KittensGame Save Manager"
APP_VERSION = "v1.0.0"
SLOT_COUNT = 10                                  # 存档位数量
MAX_NOTE_LEN = 200                               # 单条备注最大长度
MAX_SAVE_SIZE = 64 * 1024 * 1024                 # 单个存档最大体积（字节）
MONITOR_TIMEOUT = 300                            # 监控导出的超时时间（秒）

# 下载游戏链接：1=作者原版仓库（bloodrizer → nuclear-unicorn），2=社区版
GAME_DOWNLOAD_URLS = [
    "https://github.com/nuclear-unicorn/kittensgame",
    "https://github.com/kitten-science/kittensgame",
]
# 关于页链接（固定文案，不随语言翻译）
REPO_URL = "https://github.com/RimehueChimeball/KGSaveManager"
PROFILE_URL = "https://github.com/RimehueChimeball"

# ---- 程序目录：兼容源码运行与 PyInstaller 冻结 ----
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

DATA_FOLDER = BASE_DIR / "kgsm_data"             # 数据总目录：备份/迁移只移动它
SAVE_LIBRARY = DATA_FOLDER / "kittens_saves"     # 存档库文件夹
TEMP_FOLDER = DATA_FOLDER / "kgsm_temp"          # 临时文件夹（接收游戏导出文件）
CONFIG_FILE = DATA_FOLDER / "kgsm_config.json"   # 配置/备注持久化文件

# 标签页固定顺序：KGSM / 启动游戏 / 存档管理 / 配置
TAB_ORDER = ("kgsm", "game", "saves", "settings")


class KGSaveManager:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1120x640")
        self.root.minsize(800, 480)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 数据目录与配置（配置读取/首启自动创建）
        self._ensure_dirs()
        self.cfg = AppConfig(CONFIG_FILE)
        self.tr = Translator(self.cfg.language)

        # 当前选中的存档位索引（0-based）
        self.selected_slot = tk.IntVar(value=0)

        # 每个存档位的备注（来自配置，修改自动保存）
        self.notes = [self.cfg.get_note(i) for i in range(SLOT_COUNT)]

        # 存档信息列表
        self.slot_info = []
        self.load_slot_info()

        # 线程同步：监控标志 + 取消事件 + 事件队列
        self._state_lock = threading.Lock()
        self.monitoring = False
        self.cancel_event = threading.Event()
        self.event_queue = queue.Queue()
        self.monitor_thread = None

        # 本地 Web 服务（多页共用同一个服务）
        self.lweb = LocalWebServer(self.event_queue)

        # 首次构建标志（重建界面时不重复输出“程序启动”日志）
        self._first_build = True

        # 构建界面（KGSM / 启动游戏 / 存档管理 / 配置）
        self.build_ui()
        self._first_build = False

        # 启动事件队列轮询（所有后台结果都在 UI 线程处理）
        self.root.after(150, self._poll_queue)

    # =========================================================
    # 基础工具
    # =========================================================
    def _ensure_dirs(self):
        for folder in (DATA_FOLDER, SAVE_LIBRARY, TEMP_FOLDER):
            folder.mkdir(parents=True, exist_ok=True)

    def t(self, key, **kw):
        return self.tr.t(key, **kw)

    def slot_name(self, index):
        """槽位文件名前缀：自定义名优先，否则默认 存档N（文件名不翻译）。"""
        return self.cfg.slot_name(index)

    def _slot_name_text(self, index, exists):
        """槽位名字显示区：自定义名原样显示；无自定义名时仅在有存档
        文件时显示默认文件名前缀，无文件不显示（空）。"""
        custom = self.cfg.slot_names.get(str(index), "")
        if custom:
            return custom
        return self.slot_name(index) if exists else ""

    def slot_label(self, index):
        """槽位列表显示文本：<翻译前缀>NN.名字（前缀随语言，
        如 zh: 存档01.钢铁 / en: Save01.钢铁）。"""
        exists = False
        if hasattr(self, "slot_info") and index < len(self.slot_info):
            exists = bool(self.slot_info[index].get('exists'))
        prefix = self.t("sv.slot_prefix")
        return f"{prefix}{index + 1:02d}.{self._slot_name_text(index, exists)}"

    def slot_file_base(self, index):
        """槽位存档文件名前缀（不含 _N.kgsav）。"""
        return self.slot_name(index)

    def load_slot_info(self):
        """从存档库读取各存档位的信息（含时间与 mtime）。"""
        self.slot_info = []
        for i in range(SLOT_COUNT):
            slot_file = SAVE_LIBRARY / f"{self.slot_name(i)}_{i + 1}.kgsav"
            try:
                if slot_file.is_file():
                    st = slot_file.stat()
                    time_str = datetime.fromtimestamp(st.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S")
                    self.slot_info.append({
                        'exists': True,
                        'filename': str(slot_file),
                        'time': time_str,
                        'size': st.st_size,
                        'mtime': st.st_mtime,
                    })
                else:
                    self.slot_info.append({'exists': False, 'mtime': 0})
            except OSError:
                self.slot_info.append({'exists': False, 'mtime': 0})

    def _copy_to_clipboard(self, text):
        """安全地写入剪贴板（tkinter 内置，零依赖）。

        注意：剪贴板内容随本程序退出而清空；正常“复制后粘贴到游戏”
        流程中程序保持运行，不受影响。
        """
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            return True
        except Exception as e:
            self.log(f"写入剪贴板失败: {e}", "<错误>")
            messagebox.showerror("剪贴板错误", str(e))
            return False

    # =========================================================
    # 界面构建
    # =========================================================
    def build_ui(self):
        default_font = ('微软雅黑', 10)
        button_font = ('微软雅黑', 12)
        help_font = ('微软雅黑', 9)
        log_font = ('Consolas', 10)

        self.root.option_add('*Font', default_font)

        # 通用大按钮样式（先定义，供各标签页使用）
        btn_style = ttk.Style()
        btn_style.configure("Large.TButton", font=button_font, padding=9)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        tabs = {
            "kgsm": ttk.Frame(self.notebook, padding="8"),
            "game": ttk.Frame(self.notebook, padding="8"),
            "saves": ttk.Frame(self.notebook, padding="8"),
            "settings": ttk.Frame(self.notebook, padding="8"),
        }
        self.notebook.add(tabs["kgsm"], text=self.t("tab.kgsm"))
        self.notebook.add(tabs["game"], text=self.t("tab.game"))
        self.notebook.add(tabs["saves"], text=self.t("tab.saves"))
        self.notebook.add(tabs["settings"], text=self.t("tab.settings"))

        self.build_kgm_tab(tabs["kgsm"], button_font)
        self.build_game_tab(tabs["game"], button_font, log_font)
        self.build_saves_tab(tabs["saves"], button_font, help_font, log_font)
        self.build_settings_tab(tabs["settings"], button_font, log_font)

    def rebuild_ui(self, switch_to=None):
        """按当前语言重建整个界面（保留输入状态与服务运行状态）。"""
        self._flush_page_vars()

        old_mode = getattr(self, "kgm_mode_var", None)
        self._kgm_mode_default = old_mode.get() if old_mode else "recent"
        old_slot = getattr(self, "selected_slot", None)
        self._slot_restore = old_slot.get() if old_slot else 0

        if hasattr(self, "notebook"):
            try:
                self.notebook.destroy()
            except Exception:
                pass

        self.build_ui()

        # 恢复状态
        try:
            self.selected_slot.set(self._slot_restore)
        except Exception:
            pass
        if switch_to in TAB_ORDER:
            self.notebook.select(TAB_ORDER.index(switch_to))
        # 焦点交给笔记本本身，避免落在配置页下拉框上
        self.notebook.focus_set()

    # ---------- KGSM 页 ----------
    def build_kgm_tab(self, parent, button_font):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)   # 中间两个功能框占主要空间
        parent.rowconfigure(3, weight=0)

        # 标题
        ttk.Label(parent, text=self.t("kgsm.heading"),
                  font=('微软雅黑', 18, 'bold')).grid(
            row=0, column=0, sticky="w", pady=(0, 10))
        self.kgm_dir_lbl = ttk.Label(parent, font=('微软雅黑', 9),
                                     foreground="#666666")
        self.kgm_dir_lbl.grid(row=1, column=0, sticky="w", pady=(0, 6))
        self._refresh_kgm_dir()

        # 中间：左右两个功能框
        middle = ttk.Frame(parent)
        middle.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        middle.columnconfigure(0, weight=1, uniform="kgm")
        middle.columnconfigure(1, weight=1, uniform="kgm")
        middle.rowconfigure(0, weight=1)

        # 左：快速启动游戏
        quick = ttk.LabelFrame(middle, text=self.t("kgsm.quick_title"),
                               padding="12")
        quick.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        quick.columnconfigure(0, weight=1)
        quick.rowconfigure(1, weight=1)
        ttk.Label(quick, text=self.t("kgsm.quick_desc"), wraplength=380,
                  justify=tk.LEFT).grid(row=0, column=0, sticky="w", pady=(0, 6))
        run_quick = ttk.Button(quick, text=self.t("kgsm.btn_run"),
                               style="Large.TButton", command=self.kgm_quick_run)
        run_quick.grid(row=2, column=0, sticky="e", pady=(8, 0))

        # 右：复制存档并启动游戏
        copy = ttk.LabelFrame(middle, text=self.t("kgsm.copy_title"),
                              padding="12")
        copy.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        copy.columnconfigure(0, weight=1)
        ttk.Label(copy, text=self.t("kgsm.copy_desc"), wraplength=380,
                  justify=tk.LEFT).grid(row=0, column=0, sticky="w", pady=(0, 8))

        # 单选：最近存档 / 指定存档
        default_mode = getattr(self, "_kgm_mode_default", "recent")
        self.kgm_mode_var = tk.StringVar(value=default_mode)
        radios = ttk.Frame(copy)
        radios.grid(row=1, column=0, sticky="w", pady=(0, 6))
        ttk.Radiobutton(radios, text=self.t("kgsm.mode_recent"),
                        variable=self.kgm_mode_var, value="recent",
                        command=self._refresh_kgm_save).pack(side=tk.LEFT,
                                                             padx=(0, 16))
        ttk.Radiobutton(radios, text=self.t("kgsm.mode_slot"),
                        variable=self.kgm_mode_var, value="slot",
                        command=self._refresh_kgm_save).pack(side=tk.LEFT)

        # 当前将复制的存档
        self.kgm_save_lbl = ttk.Label(copy, foreground="#0a58ca",
                                      font=('微软雅黑', 10, 'bold'))
        self.kgm_save_lbl.grid(row=2, column=0, sticky="w", pady=(2, 8))

        run_copy = ttk.Button(copy, text=self.t("kgsm.btn_run"),
                              style="Large.TButton", command=self.kgm_copy_run)
        run_copy.grid(row=3, column=0, sticky="e", pady=(8, 0))
        self._refresh_kgm_save()

        # 底部：左侧“第一次使用？”+ 配置按钮；右侧两个下载游戏链接
        bottom = ttk.Frame(parent)
        bottom.grid(row=3, column=0, sticky="sew", pady=(2, 0))
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=1)

        first_box = ttk.Frame(bottom)
        first_box.grid(row=0, column=0, sticky="w")
        ttk.Label(first_box, text=self.t("kgsm.first_use_q")).pack(
            side=tk.LEFT)
        ttk.Button(first_box, text=self.t("kgsm.btn_config"),
                   command=lambda: self.notebook.select(
                       TAB_ORDER.index("settings"))).pack(side=tk.LEFT,
                                                          padx=(10, 0))

        dl_box = ttk.Frame(bottom)
        dl_box.grid(row=0, column=1, sticky="e")
        for key, url in (("kgsm.download_1", GAME_DOWNLOAD_URLS[0]),
                         ("kgsm.download_2", GAME_DOWNLOAD_URLS[1])):
            link = self._make_link(dl_box, self.t(key),
                                   command=lambda u=url: self._open_external(u))
            link.pack(side=tk.TOP, anchor="e")

    def _make_link(self, parent, text, command):
        lbl = ttk.Label(parent, text=text, foreground="#0645AD", cursor="hand2")
        lbl.bind("<Button-1>", lambda e: command())
        return lbl

    def _refresh_kgm_dir(self):
        if not hasattr(self, "kgm_dir_lbl"):
            return
        if not self._widget_alive(self.kgm_dir_lbl):
            return
        d = self.cfg.game_dir.strip()
        if d:
            self.kgm_dir_lbl.config(text=self.t("kgsm.dir_set", dir=d))
        else:
            self.kgm_dir_lbl.config(text=self.t("kgsm.dir_none"))

    def _resolve_kgm_save(self):
        """返回 (slot_index, exists) ；无可选时 (None, False)。"""
        if self.kgm_mode_var.get() == "slot":
            idx = self.cfg.home_slot
            return idx, bool(self.slot_info[idx].get('exists'))
        best_i, best_t = None, -1.0
        for i, info in enumerate(self.slot_info):
            if info.get('exists') and info.get('mtime', 0) > best_t:
                best_t = info['mtime']
                best_i = i
        if best_i is None:
            return None, False
        return best_i, True

    def _refresh_kgm_save(self):
        if not hasattr(self, "kgm_save_lbl"):
            return
        if not self._widget_alive(self.kgm_save_lbl):
            return
        idx, exists = self._resolve_kgm_save()
        prefix = self.t("kgsm.cur_prefix")
        if idx is None:
            text = prefix + self.t("ui.empty_short")
        elif exists:
            text = (prefix + f"{self.slot_label(idx)} · "
                    f"{self.slot_info[idx]['time']}")
        else:
            text = prefix + f"{self.slot_label(idx)} · " \
                + self.t("ui.empty_short")
        self.kgm_save_lbl.config(text=text)

    def _open_external(self, url):
        """用配置的浏览器打开外部超链接（不强制新窗口）。"""
        how = open_in_browser(url, browser_path=self.cfg.browser,
                              new_window=False)
        if how is None:
            messagebox.showerror(self.t("err.launch_fail"),
                                 f"open failed: {url}")

    # ---------- 启动游戏页 ----------
    def build_game_tab(self, parent, button_font, log_font):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        cfg = ttk.LabelFrame(parent, text=self.t("la.title"), padding="10")
        cfg.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        cfg.columnconfigure(1, weight=1)

        # 服务目录（与配置页「游戏目录」同一值）
        ttk.Label(cfg, text=self.t("la.dir")).grid(row=0, column=0, sticky="w",
                                                   pady=4, padx=(0, 6))
        self.launch_dir_var = tk.StringVar(value=self.cfg.game_dir)
        ent_dir = ttk.Entry(cfg, textvariable=self.launch_dir_var)
        ent_dir.grid(row=0, column=1, sticky="ew", pady=4)
        ent_dir.bind("<FocusOut>", lambda e: self._flush_page_vars())
        ttk.Button(cfg, text=self.t("ui.browse"),
                   command=self._browse_game_dir).grid(row=0, column=2,
                                                       padx=(6, 0), pady=4)

        # 端口（与配置页「固定端口」同一值）
        ttk.Label(cfg, text=self.t("la.port")).grid(row=1, column=0,
                                                    sticky="w", pady=4,
                                                    padx=(0, 6))
        self.launch_port_var = tk.StringVar(value=self.cfg.port)
        ent_port = ttk.Entry(cfg, textvariable=self.launch_port_var, width=10)
        ent_port.grid(row=1, column=1, sticky="w", pady=4)
        ent_port.bind("<FocusOut>", lambda e: self._flush_page_vars())
        ttk.Label(cfg, text=self.t("ui.auto_port"),
                  foreground="#666666").grid(row=1, column=2, sticky="w",
                                             padx=(6, 0), pady=4)

        btns = ttk.Frame(cfg)
        btns.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 2))
        self.btn_web_start = ttk.Button(btns, text=self.t("la.btn_start"),
                                        style="Large.TButton",
                                        command=self.web_start_action)
        self.btn_web_start.pack(side=tk.LEFT, padx=(0, 10))
        self.btn_web_stop = ttk.Button(btns, text=self.t("la.btn_stop"),
                                       style="Large.TButton",
                                       command=self.web_stop_action)
        self.btn_web_stop.pack(side=tk.LEFT)

        ttk.Label(parent, text=self.t("la.hint"),
                  foreground="#666666").grid(row=1, column=0, sticky="w",
                                             pady=(0, 4))

        log_frame = ttk.LabelFrame(parent, text=self.t("la.log_title"),
                                   padding="6")
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.web_log_text = scrolledtext.ScrolledText(log_frame,
                                                      wrap=tk.WORD,
                                                      font=log_font)
        self.web_log_text.grid(row=0, column=0, sticky="nsew")
        self.web_log_text.config(state=tk.DISABLED)

        # 与运行状态同步按钮
        self._update_server_buttons(self.lweb.running)
        self.web_log(self.t("la.ready"), "<启动>")

    def _update_server_buttons(self, running):
        if not hasattr(self, "btn_web_start"):
            return
        self.btn_web_start.config(state=tk.DISABLED if running else tk.NORMAL)
        self.btn_web_stop.config(state=tk.NORMAL if running else tk.DISABLED)

    def web_start_action(self):
        self._start_server_from_cfg(open_browser=True)

    def web_stop_action(self):
        self.lweb.stop()
        self._update_server_buttons(False)
        self.web_log("服务已停止。", "<停止>")

    def _start_server_from_cfg(self, open_browser=True):
        """按当前配置（游戏目录/固定端口）启动 Web 服务。

        配置为唯一权威来源：两个页面的输入框在失焦(FocusOut)时已
        各自写回配置。若配置被程序更新（如自动端口），启动前同步界面。

        :return: url 或 None（失败时已弹出错误）
        """
        self._sync_page_vars()

        directory = self.cfg.game_dir.strip()
        if not directory:
            messagebox.showerror(self.t("err.launch_fail"),
                                 self.t("err.no_dir"))
            return None
        root_dir = Path(directory)
        if not root_dir.is_dir():
            messagebox.showerror(self.t("err.launch_fail"),
                                 self.t("err.dir_missing", dir=directory))
            return None

        port_text = self.cfg.port.strip()
        port = 0
        if port_text:
            try:
                port = int(port_text)
                if not 0 < port < 65536:
                    raise ValueError
            except ValueError:
                messagebox.showerror(self.t("err.launch_fail"),
                                     self.t("err.port_invalid"))
                return None

        if self.lweb.running:
            self.web_log("检测到运行中的服务，重启以应用当前设置", "<启动>")
            self.lweb.stop()

        try:
            url, actual_port = self.lweb.start(str(root_dir), port)
        except OSError as e:
            self.web_log(f"启动失败: {e}", "<错误>")
            messagebox.showerror(self.t("err.launch_fail"),
                                 f"port={port_text or '(auto)'}: {e}")
            return None

        # 自动分配端口时回写实际端口
        if not port_text:
            self.cfg.update(port=str(actual_port))
            self._sync_page_vars()

        self._update_server_buttons(True)
        self.web_log(f"服务已启动: {url}", "<启动>")
        self.web_log(f"服务目录: {root_dir}", "<启动>")
        self.web_log("仅监听 127.0.0.1，只有本机可以访问。", "<启动>")

        if open_browser:
            self.root.after(300, self._open_browser_and_log, url)
        return url

    def _open_browser_and_log(self, url):
        """启动游戏：用配置的浏览器开新窗口。"""
        how = open_in_browser(url, browser_path=self.cfg.browser,
                              new_window=True)
        if how:
            self.web_log(f"已在浏览器新窗口打开（{how}）。", "<打开浏览器>")
        else:
            self.web_log("打开浏览器失败，请手动访问: " + url, "<错误>")

    # ---------- 存档管理页 ----------
    def build_saves_tab(self, main, button_font, help_font, log_font):
        main.columnconfigure(0, weight=0)   # 左侧不缩放
        main.columnconfigure(1, weight=1)   # 右侧缩放
        main.rowconfigure(0, weight=1)

        # ---------- 左侧按钮区 ----------
        left = ttk.Frame(main, width=220)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 15))
        left.grid_propagate(False)

        self.btn_save = ttk.Button(left, text=self.t("sv.btn_save"),
                                   style="Large.TButton",
                                   command=self.save_action)
        self.btn_save.pack(fill=tk.X, pady=8, padx=15)

        self.btn_load = ttk.Button(left, text=self.t("sv.btn_load"),
                                   style="Large.TButton",
                                   command=self.load_action)
        self.btn_load.pack(fill=tk.X, pady=8, padx=15)

        self.btn_cancel = ttk.Button(left, text=self.t("sv.btn_cancel"),
                                     style="Large.TButton",
                                     command=self.cancel_action)
        self.btn_cancel.pack(fill=tk.X, pady=8, padx=15)

        self.btn_rename = ttk.Button(left, text=self.t("sv.btn_rename"),
                                     style="Large.TButton",
                                     command=self.rename_action)
        self.btn_rename.pack(fill=tk.X, pady=8, padx=15)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10,
                                                       padx=15)

        self.btn_check = ttk.Button(left, text=self.t("sv.btn_check"),
                                    style="Large.TButton",
                                    command=self.check_action)
        self.btn_check.pack(fill=tk.X, pady=8, padx=15)

        help_label = ttk.Label(left, text=self.t("sv.help"), justify=tk.LEFT,
                               font=help_font, wraplength=190)
        help_label.pack(side=tk.BOTTOM, fill=tk.X, pady=15, padx=15)

        # ---------- 右侧区域 ----------
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")

        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)   # 存档位区域
        right.rowconfigure(1, weight=2)   # 日志区域

        slots_frame = ttk.LabelFrame(right, text=self.t("sv.title_slots"),
                                     padding="8")
        slots_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        slots_frame.columnconfigure(0, weight=1)
        slots_frame.rowconfigure(0, weight=1)

        canvas = tk.Canvas(slots_frame, highlightthickness=0,
                           yscrollincrement=38)
        scrollbar = ttk.Scrollbar(slots_frame, orient=tk.VERTICAL,
                                  command=canvas.yview)
        inner = ttk.Frame(canvas)

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        canvas_window = canvas.create_window((0, 0), window=inner, anchor=tk.NW)

        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(canvas_window, width=e.width))

        # 记录画布引用并启用滚轮滚动（指针位于存档位列表区域内时）
        self.slot_canvas = canvas
        self.slot_inner = inner
        self.root.unbind_all("<MouseWheel>")
        self.root.bind_all("<MouseWheel>", self._on_slot_mousewheel)

        self.slot_widgets = []
        for i in range(SLOT_COUNT):
            row = ttk.Frame(inner, relief=tk.FLAT, padding=5)
            row.pack(fill=tk.X, pady=3)

            rb = ttk.Radiobutton(row, variable=self.selected_slot, value=i)
            rb.pack(side=tk.LEFT, padx=8)

            name_lbl = ttk.Label(row, text=self.slot_label(i), width=17,
                                 anchor=tk.W, font=('微软雅黑', 10))
            name_lbl.pack(side=tk.LEFT, padx=8)

            time_lbl = ttk.Label(row, width=19, anchor=tk.W,
                                 font=('微软雅黑', 9))
            time_lbl.pack(side=tk.LEFT, padx=8)

            note_entry = ttk.Entry(row, width=32)
            note_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
            note_entry.insert(0, self.notes[i])
            note_entry.bind("<FocusOut>",
                            lambda e, idx=i: self.save_note(idx,
                                                            e.widget.get()))

            self.slot_widgets.append({
                'name_lbl': name_lbl,
                'time_lbl': time_lbl,
                'note_entry': note_entry,
            })

        self.update_slots_display()

        log_frame = ttk.LabelFrame(right, text=self.t("sv.title_log"),
                                   padding="8")
        log_frame.grid(row=1, column=0, sticky="nsew")

        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD,
                                                  font=log_font)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.config(state=tk.DISABLED)

        if self._first_build:
            self.log("程序启动")
            self.log(f"存档库: {SAVE_LIBRARY}")
            self.log(f"临时文件夹: {TEMP_FOLDER}")

    # ---------- 配置页 ----------
    def build_settings_tab(self, parent, button_font, log_font):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)

        frame = ttk.LabelFrame(parent, text=self.t("tab.settings"),
                               padding="12")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(1, weight=1)

        # Language（标签固定英文，不随语言翻译）
        ttk.Label(frame, text=self.t("st.lang")).grid(row=0, column=0,
                                                      sticky="w", pady=6,
                                                      padx=(0, 10))
        self._lang_codes = [LANG_ZH, LANG_EN]
        lang_values = [self.t("st.lang_zh"), self.t("st.lang_en")]
        lang_box = ttk.Combobox(frame, state="readonly", width=14,
                                values=lang_values, takefocus=0)
        lang_box.current(self._lang_codes.index(self.cfg.language)
                         if self.cfg.language in self._lang_codes else 0)
        lang_box.grid(row=0, column=1, sticky="w", pady=6)
        lang_box.bind("<<ComboboxSelected>>", self._on_language_selected)
        self.lang_combo_widget = lang_box

        # 浏览器（游戏启动与超链接共用；首次初始化时自动检测写入）
        ttk.Label(frame, text=self.t("st.browser")).grid(row=1, column=0,
                                                         sticky="w", pady=6,
                                                         padx=(0, 10))
        self.settings_browser_var = tk.StringVar(value=self.cfg.browser)
        ent_browser = ttk.Entry(frame, textvariable=self.settings_browser_var)
        ent_browser.grid(row=1, column=1, sticky="ew", pady=6)
        ent_browser.bind("<FocusOut>", lambda e: self._flush_page_vars())
        br_btns = ttk.Frame(frame)
        br_btns.grid(row=1, column=2, padx=(10, 0), pady=6)
        ttk.Button(br_btns, text=self.t("ui.browse"),
                   command=self._browse_browser).pack(side=tk.LEFT)
        ttk.Button(br_btns, text=self.t("st.browser_default"),
                   command=self._browser_use_default).pack(side=tk.LEFT,
                                                           padx=(8, 0))

        # 游戏目录（Web 服务根目录）
        ttk.Label(frame, text=self.t("st.game_dir")).grid(row=2, column=0,
                                                          sticky="w", pady=6,
                                                          padx=(0, 10))
        self.settings_dir_var = tk.StringVar(value=self.cfg.game_dir)
        ent_dir = ttk.Entry(frame, textvariable=self.settings_dir_var)
        ent_dir.grid(row=2, column=1, sticky="ew", pady=6)
        ent_dir.bind("<FocusOut>", lambda e: self._flush_page_vars())
        ttk.Button(frame, text=self.t("ui.browse"),
                   command=self._browse_game_dir).grid(row=2, column=2,
                                                       padx=(10, 0), pady=6)

        # 固定端口
        ttk.Label(frame, text=self.t("st.port")).grid(row=3, column=0,
                                                      sticky="w", pady=6,
                                                      padx=(0, 10))
        self.settings_port_var = tk.StringVar(value=self.cfg.port)
        ent_port = ttk.Entry(frame, textvariable=self.settings_port_var,
                             width=12)
        ent_port.grid(row=3, column=1, sticky="w", pady=6)
        ent_port.bind("<FocusOut>", lambda e: self._flush_page_vars())
        ttk.Label(frame, text=self.t("st.port_auto"),
                  foreground="#666666").grid(row=3, column=2, sticky="w",
                                             padx=(10, 0), pady=6)

        # 首页指定存档
        ttk.Label(frame, text=self.t("st.home_slot")).grid(row=4, column=0,
                                                           sticky="w", pady=6,
                                                           padx=(0, 10))
        self.home_slot_var = tk.StringVar()
        slot_box = ttk.Combobox(frame, textvariable=self.home_slot_var,
                                state="readonly", width=20,
                                takefocus=0)
        slot_box.grid(row=4, column=1, sticky="w", pady=6)
        slot_box.bind("<<ComboboxSelected>>", self._on_home_slot_selected)
        self.home_slot_widget = slot_box
        self._refresh_settings_slot_combo()

        # 提示
        self.settings_hint_lbl = ttk.Label(
            frame, text=self.t("st.hint", path=CONFIG_FILE),
            foreground="#888888")
        self.settings_hint_lbl.grid(row=5, column=0, columnspan=3, sticky="w",
                                    pady=(14, 0))

        # 关于（链接文案固定，不随语言翻译）
        about = ttk.LabelFrame(parent, text=self.t("st.about"), padding="10")
        about.grid(row=1, column=0, sticky="ew")
        about.columnconfigure(0, weight=1)
        about.columnconfigure(1, weight=1)
        repo_link = self._make_link(
            about, "KGSaveManager - Github",
            command=lambda: self._open_external(REPO_URL))
        repo_link.grid(row=0, column=0, sticky="w")
        profile_link = self._make_link(
            about, "霁绣凇铃RimehueChimeball - Github",
            command=lambda: self._open_external(PROFILE_URL))
        profile_link.grid(row=0, column=1, sticky="e")

        self._refresh_browser_eff()

    def _refresh_browser_eff(self):
        """在提示行里显示“系统默认浏览器”模式下实际将使用的浏览器。"""
        if not hasattr(self, "settings_hint_lbl"):
            return
        base = self.t("st.hint", path=CONFIG_FILE)
        if self.cfg.browser.strip():
            text = base
        else:
            try:
                from config_store import detect_browser_path
                exe = detect_browser_path()
            except Exception:
                exe = ""
            if exe:
                eff = exe
            else:
                eff = self.t("st.browser_auto")
            text = base + "\n" + self.t("st.browser_eff") + ": " + eff
        if self._widget_alive(self.settings_hint_lbl):
            self.settings_hint_lbl.config(text=text)

    def _on_language_selected(self, _event=None):
        cur = self.lang_combo_widget.current()
        if 0 <= cur < len(self._lang_codes):
            code = self._lang_codes[cur]
            if code != self.cfg.language:
                self._change_language(code)

    def _on_home_slot_selected(self, _event=None):
        cur = self.home_slot_widget.current()
        if 0 <= cur < SLOT_COUNT:
            self.cfg.update(home_slot=cur)
        self._refresh_kgm_save()

    def _change_language(self, code):
        """切换语言：更新配置并重建界面。"""
        if code == self.cfg.language:
            return
        self.cfg.update(language=code)
        self.tr.lang = code
        self.rebuild_ui(switch_to="settings")

    def _browse_game_dir(self):
        initial = self.cfg.game_dir.strip() or str(BASE_DIR)
        chosen = filedialog.askdirectory(title=self.t("st.game_dir"),
                                         initialdir=initial)
        if chosen:
            self.cfg.update(game_dir=chosen)
            self._sync_page_vars()
            self._refresh_kgm_dir()

    def _browse_browser(self):
        """选择浏览器 exe。"""
        initial = self.cfg.browser.strip() or ""
        if not initial:
            import os as _os
            for base in (r"%ProgramFiles(x86)%", r"%ProgramFiles%"):
                p = _os.path.expandvars(base + r"\Microsoft\Edge\Application")
                if _os.path.isdir(p):
                    initial = p
                    break
        chosen = filedialog.askopenfilename(
            title=self.t("st.browser"), initialdir=initial,
            filetypes=[("可执行程序", "*.exe"), ("所有文件", "*.*")])
        if chosen:
            self.cfg.update(browser=chosen)
            self._sync_page_vars()
            self._refresh_browser_eff()

    def _browser_use_default(self):
        """清空浏览器配置 = 使用系统默认浏览器（动态检测）。"""
        self.cfg.update(browser="")
        self._sync_page_vars()
        self._refresh_browser_eff()

    # ---------- 页面变量同步 ----------
    def _flush_page_vars(self):
        """把各页输入框内容写回配置并保存（重建/启动前调用）。"""
        changed = False
        for var_attr, cfg_attr in (
                ("launch_dir_var", "game_dir"),
                ("launch_port_var", "port"),
                ("settings_dir_var", "game_dir"),
                ("settings_port_var", "port"),
                ("settings_browser_var", "browser")):
            var = getattr(self, var_attr, None)
            if var is None:
                continue
            value = var.get().strip()
            if getattr(self.cfg, cfg_attr) != value:
                setattr(self.cfg, cfg_attr, value)
                changed = True
        if changed:
            self.cfg.save()
        self._refresh_kgm_dir()

    def _sync_page_vars(self):
        """把配置值同步回所有页面输入框。"""
        for var_attr, value in (
                ("launch_dir_var", self.cfg.game_dir),
                ("launch_port_var", self.cfg.port),
                ("settings_dir_var", self.cfg.game_dir),
                ("settings_port_var", self.cfg.port),
                ("settings_browser_var", self.cfg.browser)):
            var = getattr(self, var_attr, None)
            if var is not None:
                var.set(value)

    # =========================================================
    # 备注
    # =========================================================
    def save_note(self, idx, text):
        text = text[:MAX_NOTE_LEN]
        if self.notes[idx] != text:
            self.notes[idx] = text
            self.cfg.notes[str(idx)] = text
            self.cfg.save()

    def commit_notes(self):
        changed = False
        for i, w in enumerate(self.slot_widgets):
            text = w['note_entry'].get()[:MAX_NOTE_LEN]
            if self.notes[i] != text:
                self.notes[i] = text
                self.cfg.notes[str(i)] = text
                changed = True
        if changed:
            self.cfg.save()

    def update_slots_display(self):
        """刷新存档位行的名字与时间；不重写备注输入框，避免打断输入。"""
        self.load_slot_info()
        for i, info in enumerate(self.slot_info):
            w = self.slot_widgets[i]
            w['name_lbl'].config(text=self.slot_label(i))
            if info.get('exists'):
                w['time_lbl'].config(text=info['time'])
            else:
                w['time_lbl'].config(text=self.t("ui.empty_short"))
        self._refresh_settings_slot_combo()
        self._refresh_kgm_save()

    def _refresh_settings_slot_combo(self):
        """让配置页「首页指定存档」下拉框跟随槽位名字刷新。"""
        if not hasattr(self, "home_slot_widget"):
            return
        if not self._widget_alive(self.home_slot_widget):
            return
        values = [self.slot_label(i) for i in range(SLOT_COUNT)]
        self.home_slot_widget.configure(values=values)
        cur = self.home_slot_widget.current()
        target = self.cfg.home_slot
        if cur != target or cur < 0:
            self.home_slot_widget.current(target)

    @staticmethod
    def _widget_alive(widget):
        try:
            return widget is not None and widget.winfo_exists()
        except Exception:
            return False

    def _on_slot_mousewheel(self, event):
        """滚轮滚动存档位列表：仅当指针位于该区域内时生效。"""
        if not hasattr(self, "slot_canvas"):
            return
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget is self.slot_canvas or widget is self.slot_inner:
                step = -1 if event.delta > 0 else 1
                self.slot_canvas.yview_scroll(step * 2, "units")
                return "break"
            widget = getattr(widget, "master", None)

    def rename_action(self):
        """重命名当前选中的存档位（界面名 + 磁盘存档文件名同步）。"""
        self.commit_notes()
        slot = self.selected_slot.get()
        old = self.slot_name(slot)

        new = simpledialog.askstring(
            self.t("dlg.rename_title"), self.t("dlg.rename_prompt"),
            initialvalue=old, parent=self.root)
        if new is None:
            return
        new = new.strip()
        if not new or len(new) > 40 or any(c in new for c in '\\/:*?"<>|'):
            messagebox.showerror(self.t("dlg.rename_title"),
                                 self.t("err.name_invalid"))
            return
        if new == old:
            return

        # 磁盘文件同步改名：旧名_N.kgsav → 新名_N.kgsav
        old_file = SAVE_LIBRARY / f"{old}_{slot + 1}.kgsav"
        new_file = SAVE_LIBRARY / f"{new}_{slot + 1}.kgsav"
        if old_file.is_file():
            if new_file.exists():
                messagebox.showerror(
                    self.t("dlg.rename_title"),
                    self.t("err.name_file_exists", file=new_file.name))
                return
            try:
                os.replace(str(old_file), str(new_file))
            except OSError as e:
                messagebox.showerror(self.t("dlg.rename_title"), str(e))
                return
            self.log(f"存档文件已改名: {old_file.name} → {new_file.name}",
                     "<改名>")

        self.cfg.set_slot_name(slot, new)
        self.update_slots_display()
        self.log(f"存档位已改名: {self.slot_label(slot)}", "<改名>")

    # =========================================================
    # 日志（按页显示：存档操作→存档管理页；服务→启动游戏页）
    # =========================================================
    def _append_log(self, widget, msg, tag=""):
        timestamp = datetime.now().strftime("%H:%M:%S")
        if tag:
            formatted = f"[{timestamp}] {tag} {msg}"
        else:
            formatted = f"[{timestamp}] {msg}"
        widget.config(state=tk.NORMAL)
        widget.insert(tk.END, formatted + "\n")
        widget.see(tk.END)
        widget.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def log(self, msg, tag=""):
        """写入「存档管理」页的输出日志。"""
        if not hasattr(self, "log_text") or self.log_text is None:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {tag} {msg}" if tag else f"[{timestamp}] {msg}")
            return
        self._append_log(self.log_text, msg, tag)

    def web_log(self, msg, tag=""):
        """写入「启动游戏」页的服务日志。"""
        if not hasattr(self, "web_log_text") or self.web_log_text is None:
            return
        self._append_log(self.web_log_text, msg, tag)

    # =========================================================
    # 存档监控（存档管理页逻辑，沿用事件队列）
    # =========================================================
    def _is_monitoring(self):
        with self._state_lock:
            return self.monitoring

    def _set_monitoring(self, value):
        with self._state_lock:
            self.monitoring = value

    def cancel_monitor(self):
        if self._is_monitoring():
            self.cancel_event.set()
            self.log("正在取消存档操作...", "<取消存档>")
            return True
        self.log("当前没有进行中的存档操作", "<取消存档>")
        return False

    def cancel_action(self):
        self.commit_notes()
        self.cancel_monitor()

    def stop_ongoing_operation(self):
        if self._is_monitoring():
            self.cancel_monitor()

    def save_action(self):
        self.commit_notes()

        if self._is_monitoring():
            self.log("已有存档操作进行中，请先取消或等待完成", "<执行存档>")
            return

        slot = self.selected_slot.get()
        slot_text = self.slot_label(slot)

        if self.slot_info[slot].get('exists'):
            msg = self.t("dlg.save_overwrite", slot=slot_text)
        else:
            msg = self.t("dlg.save_new", slot=slot_text)

        if not messagebox.askokcancel(APP_NAME, msg):
            self.log("用户取消存档操作", "<取消存档>")
            return

        self.log(f"开始对 {slot_text} 进行存档操作", "<执行存档>")

        temp_abs = str(TEMP_FOLDER.resolve())
        if not self._copy_to_clipboard(temp_abs):
            return
        self.log(f"已复制路径到剪贴板: {temp_abs}")
        self.log("请在游戏中点击 Options → Export，粘贴此路径并保存为 .txt 文件。")

        self.start_monitoring(slot)

    def start_monitoring(self, slot):
        if self._is_monitoring():
            return
        self._set_monitoring(True)
        self.cancel_event.clear()
        try:
            before_files = set(os.listdir(TEMP_FOLDER))
        except OSError:
            before_files = set()
        self.monitor_thread = threading.Thread(
            target=self._monitor_worker, args=(slot, before_files), daemon=True)
        self.monitor_thread.start()

    def _monitor_worker(self, slot, before_files):
        try:
            start = time.time()
            while time.time() - start < MONITOR_TIMEOUT:
                if self.cancel_event.is_set():
                    self.event_queue.put(("cancelled",))
                    return
                time.sleep(0.5)
                now_files = set(os.listdir(TEMP_FOLDER))
                new_files = now_files - before_files
                txt_files = [f for f in new_files if f.lower().endswith(".txt")]
                if txt_files:
                    latest = max(
                        txt_files,
                        key=lambda f: self._safe_mtime(
                            os.path.join(TEMP_FOLDER, f)))
                    if self._wait_stable(latest):
                        self.event_queue.put(("save_ready", latest, slot))
                        return
            self.event_queue.put(("timeout",))
        except Exception as e:
            self.event_queue.put(("error", str(e)))
        finally:
            self._set_monitoring(False)

    def _safe_mtime(self, path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    def _wait_stable(self, filename, max_wait=5.0):
        path = os.path.join(TEMP_FOLDER, filename)
        last_size = -1
        start = time.time()
        while time.time() - start < max_wait:
            try:
                size = os.path.getsize(path)
            except OSError:
                return False
            if size == last_size and size > 0:
                return True
            last_size = size
            time.sleep(0.3)
        return False

    def process_new_file(self, filename, slot):
        src = os.path.join(TEMP_FOLDER, filename)
        dest_name = f"{self.slot_name(slot)}_{slot + 1}.kgsav"
        dest = os.path.join(SAVE_LIBRARY, dest_name)
        try:
            size = os.path.getsize(src)
            if size <= 0:
                raise ValueError("导出文件为空")
            if size > MAX_SAVE_SIZE:
                raise ValueError(f"导出文件过大（{size} 字节）")
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(64)
            if not head.strip():
                raise ValueError("导出文件内容为空")
            shutil.move(src, dest)
            self.log(f"成功存档: {filename} → {dest_name}", "<完成存档>")
            self.update_slots_display()
            self._refresh_kgm_save()
        except Exception as e:
            self.log(f"处理存档失败: {e}", "<执行存档>")
            messagebox.showerror("存档失败", str(e))

    # =========================================================
    # KGSM 页运行逻辑
    # =========================================================
    def kgm_quick_run(self):
        """快速启动：服务目录非空则起服务并打开浏览器。"""
        if not self.cfg.game_dir.strip():
            messagebox.showerror(self.t("err.launch_fail"),
                                 self.t("err.no_dir"))
            return
        self._start_server_from_cfg(open_browser=True)

    def kgm_copy_run(self):
        """复制存档并启动：校验所选存档非空后复制到剪贴板再启动。"""
        if not self.cfg.game_dir.strip():
            messagebox.showerror(self.t("err.launch_fail"),
                                 self.t("err.no_dir"))
            return

        idx, exists = self._resolve_kgm_save()
        if idx is None:
            messagebox.showerror(self.t("err.launch_fail"),
                                 self.t("err.no_saves"))
            return
        if not exists:
            messagebox.showerror(self.t("err.launch_fail"),
                                 self.t("err.no_save"))
            return

        try:
            content = self._read_save_file(self.slot_info[idx]['filename'])
        except Exception as e:
            self.log(f"读取存档失败: {e}", "<读档操作>")
            messagebox.showerror("读档失败", str(e))
            return

        if not self._copy_to_clipboard(content):
            return
        self.log(f"已将 {self.slot_label(idx)} 的存档内容复制到剪贴板",
                 "<读档操作>")
        self.log("游戏打开后点击 Options → Import，粘贴 (Ctrl+V) 即可导入。")

        self._start_server_from_cfg(open_browser=True)

    def _read_save_file(self, path):
        """读取存档文件并做基本校验，返回文本内容。"""
        size = os.path.getsize(path)
        if size <= 0:
            raise ValueError("存档文件为空")
        if size > MAX_SAVE_SIZE:
            raise ValueError(f"存档文件过大（{size} 字节）")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    # =========================================================
    # 存档管理页操作（读档/检查）
    # =========================================================
    def load_action(self):
        self.stop_ongoing_operation()
        self.commit_notes()

        slot = self.selected_slot.get()
        if not self.slot_info[slot].get('exists'):
            messagebox.showwarning(APP_NAME,
                                   self.t("dlg.no_file",
                                          slot=self.slot_label(slot)))
            return

        slot_file = self.slot_info[slot]['filename']
        try:
            content = self._read_save_file(slot_file)
            if not self._copy_to_clipboard(content):
                return
            self.log(f"已将 {self.slot_label(slot)} 的存档内容复制到剪贴板",
                     "<读档操作>")
            self.log("请打开游戏，点击 Options → Import，粘贴 (Ctrl+V) 并确认。")
            messagebox.showinfo(
                APP_NAME,
                self.t("dlg.copied_ok", slot=self.slot_label(slot)))
        except Exception as e:
            self.log(f"读取存档失败: {e}", "<读档操作>")
            messagebox.showerror("读档失败", str(e))

    def check_action(self):
        self.stop_ongoing_operation()
        self.commit_notes()

        self.log("开始检查异常文件...", "<检查异常>")

        valid_names = {f"{self.slot_name(i)}_{i + 1}.kgsav"
                       for i in range(SLOT_COUNT)}

        try:
            library_files = sorted(os.listdir(SAVE_LIBRARY))
        except OSError:
            library_files = []
        try:
            temp_files = sorted(os.listdir(TEMP_FOLDER))
        except OSError:
            temp_files = []

        invalid_lib = [f for f in library_files if f not in valid_names]
        empty_lib = []
        for name in valid_names:
            p = os.path.join(SAVE_LIBRARY, name)
            try:
                if os.path.isfile(p) and os.path.getsize(p) == 0:
                    empty_lib.append(name)
            except OSError:
                pass

        self.log("=" * 50, "<检查异常>")
        if invalid_lib:
            self.log("【存档库】发现以下不合规文件（程序不会处理）：", "<检查异常>")
            for f in invalid_lib:
                self.log(f"  - {f}", "<检查异常>")
        else:
            self.log("【存档库】没有不合规文件。", "<检查异常>")

        if empty_lib:
            self.log("【存档库】以下存档文件内容为空：", "<检查异常>")
            for f in empty_lib:
                self.log(f"  - {f}", "<检查异常>")

        if temp_files:
            self.log("【临时文件夹】发现以下文件（程序不会处理）：", "<检查异常>")
            for f in temp_files:
                self.log(f"  - {f}", "<检查异常>")
        else:
            self.log("【临时文件夹】为空。", "<检查异常>")

        self.log("这些文件不会被程序管理，请自行判断是否转移或删除。", "<检查异常>")
        self.log("=" * 50, "<检查异常>")

    # =========================================================
    # 事件队列轮询（UI 线程）
    # =========================================================
    def _poll_queue(self):
        try:
            while True:
                item = self.event_queue.get_nowait()
                self._handle_event(item)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(150, self._poll_queue)

    def _handle_event(self, item):
        kind = item[0]
        if kind == "save_ready":
            self.process_new_file(item[1], item[2])
        elif kind == "timeout":
            self.log("存档超时：未在5分钟内检测到新文件，请确保已正确导出存档。",
                     "<超时>")
        elif kind == "cancelled":
            self.log("用户取消存档操作", "<取消存档>")
        elif kind == "error":
            self.log(f"监控出错: {item[1]}", "<错误>")
        elif kind == "server_log":
            self.web_log(item[1], "<服务>")

    # =========================================================
    # 退出
    # =========================================================
    def _on_close(self):
        self.commit_notes()
        self.cancel_event.set()
        self.lweb.stop()
        self.root.destroy()


if __name__ == "__main__":
    setup_dpi_and_scaling()
    root = tk.Tk()
    app = KGSaveManager(root)
    root.mainloop()
