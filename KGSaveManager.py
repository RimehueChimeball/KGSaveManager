"""
KittensGame 存档管理器 (KGSaveManager)
======================================

基于 Tkinter 的《Kittens Game》存档管理器（save manager）：存档管理、
备注与配置持久化、一键本地 Web 服务（http.server + socketserver）启动游戏、
在与游戏页面的本地 WebSocket 桥之间读写实时存档。

功能特性：
1. 备注与配置持久化：kgsm_data/kgsm_config.json（原子写入，自动保存）。
2. 数据目录统一：kgsm_data 收纳存档库/临时目录/配置文件，备份只移动它。
3. 线程安全：后台监控与界面通过事件队列通信，不跨线程操作 UI。
4. 文件校验：接收存档前校验非空、限体积，等待导出文件写入稳定。
5. 剪贴板：内置 tkinter 剪贴板实现，零第三方依赖。
6. 中英翻译：无配置文件时按系统语言探测，配置页可切换，自动保存。
7. 六个标签页：KGSM（导航与新手引导）、启动游戏（Web 服务）、存档管理、
   修改存档、下载游戏、配置（语言/游戏目录/固定端口/默认存档位）。

模块分层：`core/`（与界面无关的逻辑：槽位/存档流程/界面端口定义）、
`ui_tk.py`（Tkinter 对界面端口的实现）、各页面 Mixin（视图）、
i18n.py（翻译）、config_store.py（配置）、web_server.py（本地 Web 服务）、
web_bridge.py（页面桥）、savecodec.py（存档编解码）、downloader.py（下载）、
kgsm_logging.py（运行日志）、utils.py（DPI）。
"""

import os
import queue
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import scrolledtext, ttk

from config_store import AppConfig
from core.flows import SaveFlows, clean_temp_folder
from core.slots import SlotStore
from i18n import (LANG_EN, LANG_ZH, Translator,
                  load_external_translations)
from kgsm_logging import AppLogger
from pages_download import DownloadPageMixin
from pages_editor import EditorPageMixin
from pages_manual import ManualSaveMixin
from ui_tk import TkUiPort
from utils import setup_dpi_and_scaling
from web_bridge import WebSocketBridge
from web_server import LocalWebServer, open_in_browser

# ==================== 配置 ====================
APP_NAME = "KittensGame Save Manager"
APP_VERSION = "v1.2.2"
SLOT_COUNT = 10                                  # 存档位数量
MAX_NOTE_LEN = 200                               # 单条备注最大长度
MAX_SAVE_SIZE = 64 * 1024 * 1024                 # 单个存档最大体积（字节）
TEMP_KEEP_SECONDS = 7 * 24 * 3600                # 临时目录文件保留时长（秒）

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
BACKUP_DIR = DATA_FOLDER / "backups"             # 存档备份目录（编辑前备份）

# 标签页固定顺序：KGSM / 启动游戏 / 存档管理 / 修改存档 / 下载游戏 / 配置
TAB_ORDER = ("kgsm", "game", "saves", "editor", "download", "settings")


class KGSaveManager(ManualSaveMixin, EditorPageMixin, DownloadPageMixin):
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1120x640")
        self.root.minsize(800, 480)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 数据目录与配置（配置读取/首启自动创建）
        self._ensure_dirs()
        self.cfg = AppConfig(CONFIG_FILE)
        # 外部翻译（程序目录 i18n/ 下的 json/po）先于界面加载
        load_external_translations(BASE_DIR / "i18n")
        self.tr = Translator(self.cfg.language)

        # 运行日志（每次启动一个文件，记录启动信息与关键操作）
        self.logger = AppLogger(
            DATA_FOLDER / "kgsm_log", APP_VERSION,
            extra_header=[f"游戏目录: {self.cfg.game_dir or '(未设置)'}",
                          f"语言: {self.cfg.language}",
                          f"配置: {CONFIG_FILE}",
                          f"日志目录: {DATA_FOLDER / 'kgsm_log'}"])

        # 清理临时文件夹中的过期导出文件
        clean_temp_folder(TEMP_FOLDER, TEMP_KEEP_SECONDS, self.logger)

        # 当前选中的存档位索引（0-based）：默认取配置页指定的存档位
        home = self.cfg.home_slot
        if not (0 <= home < SLOT_COUNT):
            home = 0
        self.selected_slot = tk.IntVar(value=home)

        # 每个存档位的备注（来自配置，修改自动保存）
        self.notes = [self.cfg.get_note(i) for i in range(SLOT_COUNT)]

        # 后台线程与 UI 通信的事件队列
        self.event_queue = queue.Queue()

        # 本地 Web 服务与存档桥（多页共用同一个服务）
        self.lweb = LocalWebServer(self.event_queue)
        self.bridge = None
        # Mixin 页需要的基础常量
        self.base_dir = BASE_DIR
        self.tab_order = TAB_ORDER
        self.app_name = APP_NAME
        self.save_library = SAVE_LIBRARY
        self.max_save_size = MAX_SAVE_SIZE
        self.temp_folder = TEMP_FOLDER
        self.backup_dir = BACKUP_DIR

        # 逻辑层：界面端口 → 槽位存储 → 存档流程（core 不含任何 GUI 代码）
        self.ui = TkUiPort(self)
        self.slots = SlotStore(SAVE_LIBRARY, self.t, SLOT_COUNT)
        self.flows = SaveFlows(
            ui=self.ui, slots=self.slots, cfg=self.cfg, t=self.t,
            events=self.event_queue, app_name=APP_NAME,
            temp_folder=TEMP_FOLDER, max_save_size=MAX_SAVE_SIZE,
            get_bridge=lambda: self.bridge,
            is_server_running=lambda: self.lweb.running,
            logger=self.logger)

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
        for folder in (DATA_FOLDER, SAVE_LIBRARY, TEMP_FOLDER, BACKUP_DIR):
            folder.mkdir(parents=True, exist_ok=True)

    def t(self, key, **kw):
        return self.tr.t(key, **kw)

    def _widget_alive(self, widget):
        try:
            return widget is not None and widget.winfo_exists()
        except Exception:
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
            "editor": ttk.Frame(self.notebook, padding="8"),
            "download": ttk.Frame(self.notebook, padding="8"),
            "settings": ttk.Frame(self.notebook, padding="8"),
        }
        self.notebook.add(tabs["kgsm"], text=self.t("tab.kgsm"))
        self.notebook.add(tabs["game"], text=self.t("tab.game"))
        self.notebook.add(tabs["saves"], text=self.t("tab.saves"))
        self.notebook.add(tabs["editor"], text=self.t("tab.editor"))
        self.notebook.add(tabs["download"], text=self.t("tab.download"))
        self.notebook.add(tabs["settings"], text=self.t("tab.settings"))

        # 切换标签页时把焦点还给笔记本本身，避免输入框抢焦点
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        # 全局 Esc：让当前输入框失去焦点
        self.root.bind("<Escape>", self._clear_focus)

        self.build_kgm_tab(tabs["kgsm"], button_font)
        self.build_game_tab(tabs["game"], button_font, log_font)
        self.build_saves_tab(tabs["saves"], button_font, help_font, log_font)
        self.build_editor_tab(tabs["editor"], button_font, log_font)
        self.build_download_tab(tabs["download"], button_font, log_font)
        self.build_settings_tab(tabs["settings"], button_font, log_font)

    def _on_tab_changed(self, _event=None):
        """切页后不把焦点留在输入框上（还给笔记本）。"""
        if hasattr(self, "notebook") and self._widget_alive(self.notebook):
            self.notebook.focus_set()

    def _clear_focus(self, _event=None):
        """Esc：让当前输入框失去焦点。"""
        if hasattr(self, "notebook") and self._widget_alive(self.notebook):
            self.notebook.focus_set()

    def rebuild_ui(self, switch_to=None):
        """按当前语言重建整个界面（保留输入状态与服务运行状态）。"""
        self._flush_page_vars()

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
        """主页：标题 + 左侧页面按钮 + 右侧新手引导流程。"""
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(1, weight=1)

        ttk.Label(parent, text=self.t("kgsm.heading"),
                  font=('微软雅黑', 18, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        # 左侧：除 KGSM 外的所有页面，按钮垂直排列
        nav = ttk.Frame(parent, width=210)
        nav.grid(row=1, column=0, sticky="ns", padx=(0, 14))
        nav.grid_propagate(False)
        for key in ("game", "saves", "editor", "download", "settings"):
            ttk.Button(
                nav, text=self.t(f"tab.{key}"), style="Large.TButton",
                command=lambda k=key: self.notebook.select(
                    TAB_ORDER.index(k))).pack(fill=tk.X, pady=6)

        # 右侧：新手引导（垂直流程）
        guide = ttk.LabelFrame(parent, text=self.t("kgsm.guide_title"),
                               padding="18")
        guide.grid(row=1, column=1, sticky="nsew")
        guide.columnconfigure(0, weight=1)

        steps = (
            (1, "kgsm.step_doc", self.open_offline_doc),
            (2, "kgsm.step_dl",
             lambda: self.notebook.select(TAB_ORDER.index("download"))),
            (3, "kgsm.step_cfg",
             lambda: self.notebook.select(TAB_ORDER.index("settings"))),
            (4, "kgsm.step_run",
             lambda: self.notebook.select(TAB_ORDER.index("game"))),
        )
        for idx, (num, key, cmd) in enumerate(steps):
            if idx:
                ttk.Label(guide, text="↓", foreground="#999999").pack()
            row = ttk.Frame(guide)
            row.pack(fill=tk.X, pady=5)
            ttk.Label(row, text=str(num), width=3, anchor="center",
                      font=('微软雅黑', 12, 'bold')).pack(side=tk.LEFT)
            link = self._make_link(row, self.t(key), command=cmd)
            link.pack(side=tk.LEFT, padx=(10, 0))

        ttk.Separator(guide, orient=tk.HORIZONTAL).pack(fill=tk.X,
                                                        pady=(16, 10))
        ttk.Label(guide, text=self.t("kgsm.guide_hint"),
                  foreground="#888888", wraplength=560).pack(anchor="w")

    def open_offline_doc(self):
        """打开内置英文离线文档（单页 HTML）。"""
        doc = BASE_DIR / "docs" / "guide_en.html"
        if doc.is_file():
            open_in_browser(doc.as_uri(), browser_path=self.cfg.browser,
                            new_window=False)
        else:
            self.ui.fail(f"offline doc not found: {doc}",
                         self.t("err.launch_fail"))

    def _make_link(self, parent, text, command):
        lbl = ttk.Label(parent, text=text, foreground="#0645AD", cursor="hand2")
        lbl.bind("<Button-1>", lambda e: command())
        return lbl

    def _open_external(self, url):
        """用配置的浏览器打开外部超链接（不强制新窗口）。"""
        how = open_in_browser(url, browser_path=self.cfg.browser,
                              new_window=False)
        if how is None:
            self.ui.fail(f"open failed: {url}", self.t("err.launch_fail"))

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
        self.web_log(self.t("la.ready"), self.t("tag.start"))

    def _update_server_buttons(self, running):
        if not hasattr(self, "btn_web_start"):
            return
        self.btn_web_start.config(state=tk.DISABLED if running else tk.NORMAL)
        self.btn_web_stop.config(state=tk.NORMAL if running else tk.DISABLED)

    def web_start_action(self):
        self._start_server_from_cfg(open_browser=True)

    def web_stop_action(self):
        self._stop_web_all()
        self._update_server_buttons(False)
        self.web_log(self.t("msg.server_stopped"), self.t("tag.stop"))
        if getattr(self, "logger", None) is not None:
            self.logger.action("WEB_STOP", "服务与存档桥已停止")

    def _stop_web_all(self):
        """停止 Web 服务与存档桥（含重启与退出时）。"""
        self.lweb.stop()
        bridge, self.bridge = self.bridge, None
        if bridge is not None:
            try:
                bridge.stop()
            except Exception:
                pass

    def _start_server_from_cfg(self, open_browser=True):
        """按当前配置（游戏目录/固定端口）启动 Web 服务与存档桥。

        配置为唯一权威来源：两个页面的输入框在失焦(FocusOut)时已
        各自写回配置。若配置被程序更新（如自动端口），启动前同步界面。

        :return: url 或 None（失败时已弹出错误）
        """
        self._sync_page_vars()

        directory = self.cfg.game_dir.strip()
        if not directory:
            self.ui.fail(self.t("err.no_dir"), self.t("err.launch_fail"))
            return None
        root_dir = Path(directory)
        if not root_dir.is_dir():
            self.ui.fail(self.t("err.dir_missing", dir=directory),
                         self.t("err.launch_fail"))
            return None

        port_text = self.cfg.port.strip()
        port = 0
        if port_text:
            try:
                port = int(port_text)
                if not 0 < port < 65536:
                    raise ValueError
            except ValueError:
                self.ui.fail(self.t("err.port_invalid"),
                             self.t("err.launch_fail"))
                return None

        if self.lweb.running:
            self.web_log(self.t("msg.server_restart"), self.t("tag.start"))
            self._stop_web_all()

        bridge = None
        try:
            bridge = WebSocketBridge()
            bridge.set_ui_queue(self.event_queue)
            bridge.start()
            url, actual_port = self.lweb.start(str(root_dir), port,
                                               bridge=bridge)
        except OSError as e:
            if bridge is not None:
                try:
                    bridge.stop()
                except Exception:
                    pass
            self.web_log(self.t("msg.server_fail", e=e), self.t("tag.error"))
            self.logger.error(f"服务启动失败 port={port_text or '(auto)'}: {e}")
            self.ui.fail(f"port={port_text or '(auto)'}: {e}",
                         self.t("err.launch_fail"))
            return None
        self.bridge = bridge

        # 自动分配端口时回写实际端口
        if not port_text:
            self.cfg.update(port=str(actual_port))
            self._sync_page_vars()

        self._update_server_buttons(True)
        self.web_log(self.t("msg.server_started", url=url),
                     self.t("tag.start"))
        self.web_log(self.t("msg.server_dir", dir=root_dir),
                     self.t("tag.start"))
        self.web_log(self.t("msg.server_local"), self.t("tag.start"))
        if bridge is not None:
            self.web_log(f"存档桥已就绪: ws://127.0.0.1:{bridge.port}/",
                         self.t("tag.start"))

        if open_browser:
            self.root.after(300, self._open_browser_and_log, url)
        return url

    def _open_browser_and_log(self, url):
        """启动游戏：用配置的浏览器开新窗口。"""
        how = open_in_browser(url, browser_path=self.cfg.browser,
                              new_window=True)
        if how:
            self.web_log(self.t("msg.browser_opened", how=how),
                         self.t("tag.browser"))
        else:
            self.web_log(self.t("msg.browser_fail", url=url),
                         self.t("tag.error"))

    # ---------- 存档管理页 ----------
    def build_saves_tab(self, main, button_font, help_font, log_font):
        main.columnconfigure(0, weight=0)   # 左侧不缩放
        main.columnconfigure(1, weight=1)   # 右侧缩放
        main.rowconfigure(0, weight=1)

        # ---------- 左侧按钮区 ----------
        left = ttk.Frame(main, width=220)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 15))
        left.grid_propagate(False)

        self.btn_auto_save = ttk.Button(left, text=self.t("sv.btn_auto_save"),
                                        style="Large.TButton",
                                        command=self.auto_save_action)
        self.btn_auto_save.pack(fill=tk.X, pady=8, padx=15)

        self.btn_manual_save = ttk.Button(left,
                                          text=self.t("sv.btn_manual_save"),
                                          style="Large.TButton",
                                          command=self.manual_save_action)
        self.btn_manual_save.pack(fill=tk.X, pady=8, padx=15)

        self.btn_auto_load = ttk.Button(left, text=self.t("sv.btn_auto_load"),
                                        style="Large.TButton",
                                        command=self.auto_load_action)
        self.btn_auto_load.pack(fill=tk.X, pady=8, padx=15)

        self.btn_load = ttk.Button(left, text=self.t("sv.btn_load"),
                                   style="Large.TButton",
                                   command=self.load_action)
        self.btn_load.pack(fill=tk.X, pady=8, padx=15)

        self.btn_rename = ttk.Button(left, text=self.t("sv.btn_rename"),
                                     style="Large.TButton",
                                     command=self.rename_action)
        self.btn_rename.pack(fill=tk.X, pady=8, padx=15)

        self.btn_refresh = ttk.Button(left, text=self.t("sv.btn_refresh"),
                                      style="Large.TButton",
                                      command=self.refresh_action)
        self.btn_refresh.pack(fill=tk.X, pady=8, padx=15)

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

            name_lbl = ttk.Label(row, text=self.slots.label(i), width=17,
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
            self.log(self.t("msg.app_start"))
            self.log(self.t("msg.library_path", path=SAVE_LIBRARY))
            self.log(self.t("msg.temp_path", path=TEMP_FOLDER))

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

        # 默认存档位（启动时选中）
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
        doc_link = self._make_link(
            about, "Offline Guide (docs/guide_en.html)",
            command=self.open_offline_doc)
        doc_link.grid(row=1, column=0, sticky="w", pady=(4, 0))

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

    def _change_language(self, code):
        """切换语言：更新配置并重建界面。"""
        if code == self.cfg.language:
            return
        self.cfg.update(language=code)
        self.tr.lang = code
        self.rebuild_ui(switch_to="settings")

    def _browse_game_dir(self):
        initial = self.cfg.game_dir.strip() or str(BASE_DIR)
        chosen = self.ui.ask_directory(self.t("st.game_dir"), initial)
        if chosen:
            self.cfg.update(game_dir=chosen)
            self._sync_page_vars()

    def _browse_browser(self):
        """选择浏览器 exe。"""
        initial = self.cfg.browser.strip() or ""
        if not initial:
            for base in (r"%ProgramFiles(x86)%", r"%ProgramFiles%"):
                p = os.path.expandvars(base + r"\Microsoft\Edge\Application")
                if os.path.isdir(p):
                    initial = p
                    break
        chosen = self.ui.ask_file(
            self.t("st.browser"), initial,
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
        # 把各页输入框内容（可能带引号/斜杠）规范化后写回配置并保存
        ups = {}
        for var_attr, cfg_attr in (
                ("launch_dir_var", "game_dir"),
                ("launch_port_var", "port"),
                ("settings_dir_var", "game_dir"),
                ("settings_port_var", "port"),
                ("settings_browser_var", "browser")):
            var = getattr(self, var_attr, None)
            if var is None:
                continue
            value = var.get()
            if cfg_attr in ("game_dir", "browser"):
                from config_store import _clean_path
                value = _clean_path(value)
                var.set(value)
            else:
                value = value.strip()
            if getattr(self.cfg, cfg_attr) != value:
                ups[cfg_attr] = value
        if ups:
            self.cfg.update(**ups)

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
            self.cfg.set_note(idx, text)

    def commit_notes(self):
        changed = False
        for i, w in enumerate(self.slot_widgets):
            text = w['note_entry'].get()[:MAX_NOTE_LEN]
            if self.notes[i] != text:
                self.notes[i] = text
                self.cfg.set_note(i, text, save=False)
                changed = True
        if changed:
            self.cfg.save()

    def update_slots_display(self):
        """刷新存档位行的名字与时间；不重写备注输入框，避免打断输入。

        空槽位：名字区显示“空/empty”，时间列留白。
        """
        self.slots.refresh()
        for i, info in enumerate(self.slots.info):
            w = self.slot_widgets[i]
            w['name_lbl'].config(text=self.slots.label(i))
            if info.get('exists'):
                w['time_lbl'].config(text=info['time'])
            else:
                w['time_lbl'].config(text="")
        self._refresh_settings_slot_combo()
        self._refresh_edit_slots()

    def _refresh_edit_slots(self):
        """让修改存档页的槽位下拉跟随存档库刷新。"""
        if not hasattr(self, "_edit") or not hasattr(self, "edit_mode_var"):
            return
        if not self._widget_alive(self.edit_slot_combo):
            return
        ids = [i for i, info in enumerate(self.slots.info)
               if info.get('exists')]
        mapping = {self.slots.label(i): i for i in ids}
        self._edit["slot_ids"] = ids
        self._edit["slot_map"] = mapping
        cur = self.edit_slot_var.get()
        if self.edit_mode_var.get() == "file":
            values = list(mapping.keys())
            self.edit_slot_combo.configure(values=values)
            if cur not in mapping:
                self.edit_slot_var.set(values[0] if values else "")

    def _refresh_settings_slot_combo(self):
        """让配置页「默认存档位」下拉框跟随槽位名字刷新。"""
        if not hasattr(self, "home_slot_widget"):
            return
        if not self._widget_alive(self.home_slot_widget):
            return
        values = [self.slots.label(i) for i in range(SLOT_COUNT)]
        self.home_slot_widget.configure(values=values)
        cur = self.home_slot_widget.current()
        target = self.cfg.home_slot
        if cur != target or cur < 0:
            self.home_slot_widget.current(target)

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
        """重命名当前存档位：只改磁盘文件名（名字完全来自文件）。

        没有存档文件的槽位提示先存档；配置文件不保存槽位名。
        """
        self.commit_notes()
        slot = self.selected_slot.get()

        if not self.slots.exists(slot):
            self.ui.warn(self.t("err.rename_need_file"),
                         self.t("dlg.rename_title"))
            return

        old = self.slots.name(slot)
        old_file_name = self.slots.path(slot).name
        new = self.ui.ask_text(self.t("dlg.rename_title"),
                               self.t("dlg.rename_prompt"), old)
        if new is None:
            return
        path, error = self.slots.rename(slot, new)
        if path is None:
            if error:
                self.ui.fail(error, self.t("dlg.rename_title"))
            return
        if path.name == old_file_name:
            return                        # 名字没变
        self.log(self.t("msg.file_renamed", old=old_file_name,
                        new=path.name), self.t("tag.rename"))
        self.ui.slots_changed()

    def refresh_action(self):
        """手动刷新存档库（重新扫描文件名与修改日期）。"""
        self.commit_notes()
        self.update_slots_display()
        self.log(self.t("msg.refreshed"), self.t("tag.refresh"))

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
    # 存档管理页按钮（视图胶水：读输入框 → 调 core → 刷新显示）
    # =========================================================
    def auto_save_action(self):
        self.commit_notes()
        self.flows.auto_save(self.selected_slot.get())

    def auto_load_action(self):
        self.commit_notes()
        self.flows.auto_load(self.selected_slot.get())

    def load_action(self):
        self.commit_notes()
        self.flows.copy_save(self.selected_slot.get())

    def check_action(self):
        self.commit_notes()
        self.flows.check_library()

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
        if self.flows.handle_event(item):
            return
        if kind == "server_log":
            self.web_log(item[1], self.t("tag.server"))
        elif kind == "bridge_log":
            self.web_log(item[1], self.t("tag.bridge"))
        elif kind == "dl_log":
            self._dl_log(item[1])
        elif kind == "dl_versions":
            self._handle_dl_versions(item[2])
        elif kind == "dl_progress":
            self._handle_dl_progress(item[1])
        elif kind == "dl_done":
            self._handle_dl_done(item[1], item[2])
        elif kind == "dl_fail":
            self._handle_dl_fail(item[1],
                                 bool(item[2]) if len(item) > 2 else False)
        elif kind == "dl_canceled":
            self._handle_dl_cancel()
        elif kind == "dl_test_result":
            self._handle_dl_test_result(item[1])

    # =========================================================
    # 退出
    # =========================================================
    def _on_close(self):
        self.commit_notes()
        self._stop_web_all()
        if getattr(self, "logger", None) is not None:
            try:
                self.logger.action("EXIT", "程序退出")
                self.logger.close()
            except Exception:
                pass
        self.root.destroy()


if __name__ == "__main__":
    setup_dpi_and_scaling()
    root = tk.Tk()
    app = KGSaveManager(root)
    root.mainloop()
