"""
KittensGame 存档管理器 (KGSaveManager)
======================================

一个基于 Tkinter 的《Kittens Game》存档管理工具，支持存档位管理、
备注持久化、游戏存档的导入/导出对接，以及一键启动本地静态 Web 服务。

功能特性：
1. 备注与配置持久化：保存到 ``kgsm_data/kgsm_config.json``（原子写入），
   重启不丢失，也为后续扩展预留配置位。
2. 数据目录统一：存档库/临时目录/配置文件统一收纳在 ``kgsm_data`` 下，
   备份或迁移时只需复制/移动这一个文件夹；路径基于“程序所在目录”
   解析，不依赖当前工作目录（CWD），兼容 PyInstaller 冻结打包。
3. 线程安全：后台监控线程与 Tkinter 界面通过队列通信，不直接跨线程
   操作 UI；监控状态用锁保护，异常统一走 try/finally。
4. 输入/文件校验：限制备注长度、存档文件大小，校验内容非空，
   并等待导出文件写入稳定后再接收，避免拿到半成品。
5. 剪贴板异常处理：读写剪贴板失败不会导致崩溃，且缺少 pyperclip 时
   自动回退到 tkinter 自带剪贴板。
6. 多标签页 GUI：默认页「存档管理」，另有「启动」页——内置本地静态
   Web 服务（http.server + socketserver），一键起服务并打开浏览器
   （优先 Edge/Chrome 新窗口，其次 webbrowser）。
"""

import functools
import http.server
import json
import os
import queue
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    import pyperclip
except ImportError:  # pyperclip 未安装时回退到 tkinter 自带剪贴板
    pyperclip = None

from utils import setup_dpi_and_scaling

# ==================== 配置 ====================
APP_NAME = "KittensGame Save Manager"
APP_VERSION = "v1.0.0"
SLOT_COUNT = 6                                   # 存档位数量
SLOT_NAMES = [f"存档{i + 1}" for i in range(SLOT_COUNT)]
MAX_NOTE_LEN = 200                               # 单条备注最大长度
MAX_SAVE_SIZE = 64 * 1024 * 1024                 # 单个存档最大体积（字节）
MONITOR_TIMEOUT = 300                            # 监控导出的超时时间（秒）

# ---- 程序目录：兼容源码运行与 PyInstaller 冻结 ----
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

DATA_FOLDER = BASE_DIR / "kgsm_data"             # 数据总目录：备份/迁移只移动它
SAVE_LIBRARY = DATA_FOLDER / "kittens_saves"     # 存档库文件夹
TEMP_FOLDER = DATA_FOLDER / "kgsm_temp"          # 临时文件夹（接收游戏导出文件）
CONFIG_FILE = DATA_FOLDER / "kgsm_config.json"   # 配置/备注持久化文件
WEB_ROOT = BASE_DIR / "web"                      # 启动页默认服务目录


# ---- 本地静态 Web 服务 ----
class _WebHandler(http.server.SimpleHTTPRequestHandler):
    """静态文件请求处理器：访问日志转发到 UI 事件队列，不在控制台输出。"""

    _queue = None  # 启动服务前由主程序注入事件队列

    def log_message(self, fmt, *args):
        if self._queue is not None:
            msg = "%s - - [%s] %s" % (
                self.address_string(), self.log_date_time_string(), fmt % args)
            self._queue.put(("server_log", msg))


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """多线程版本地 HTTP 服务器（服务线程随主程序退出）。"""

    daemon_threads = True


class KGSaveManager:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1100x600")
        self.root.minsize(750, 400)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 创建必要的文件夹
        self._ensure_dirs()

        # 当前选中的存档位索引（0-based）
        self.selected_slot = tk.IntVar(value=0)

        # 每个存档位的备注（先从磁盘加载）
        self.notes = ["" for _ in range(SLOT_COUNT)]
        self._load_notes()

        # 存档信息列表
        self.slot_info = []
        self.load_slot_info()

        # 线程同步：监控标志 + 取消事件 + 事件队列
        self._state_lock = threading.Lock()
        self.monitoring = False
        self.cancel_event = threading.Event()
        self.event_queue = queue.Queue()
        self.monitor_thread = None

        # 本地 Web 服务状态（启动页）
        self.web_server = None
        self.web_thread = None
        self.web_url = None

        # 构建界面
        self.build_ui()

        # 启动事件队列轮询（所有后台结果都在 UI 线程处理）
        self.root.after(150, self._poll_queue)

    # ---------------- 基础工具 ----------------
    def _ensure_dirs(self):
        for folder in (DATA_FOLDER, SAVE_LIBRARY, TEMP_FOLDER):
            folder.mkdir(parents=True, exist_ok=True)

    def _is_monitoring(self):
        with self._state_lock:
            return self.monitoring

    def _set_monitoring(self, value):
        with self._state_lock:
            self.monitoring = value

    def _load_notes(self):
        """从磁盘加载备注；失败或缺失时保持默认空备注。"""
        if not CONFIG_FILE.exists():
            return
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for i in range(SLOT_COUNT):
                    raw = data.get(str(i), "")
                    self.notes[i] = str(raw)[:MAX_NOTE_LEN]
        except Exception as e:
            self.log(f"加载备注失败（已忽略）: {e}", "<警告>")

    def _save_notes(self):
        """原子写入配置（含备注）：先写临时文件再替换，避免写一半损坏。"""
        data = {str(i): self.notes[i] for i in range(SLOT_COUNT)}
        tmp = CONFIG_FILE.with_suffix(".json.tmp")
        try:
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(CONFIG_FILE)
        except Exception as e:
            self.log(f"保存备注失败: {e}", "<警告>")

    def load_slot_info(self):
        """从存档库读取各存档位的信息。"""
        self.slot_info = []
        for i in range(SLOT_COUNT):
            slot_file = SAVE_LIBRARY / f"{SLOT_NAMES[i]}_{i + 1}.kgsav"
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
                    })
                else:
                    self.slot_info.append({'exists': False})
            except OSError:
                self.slot_info.append({'exists': False})

    def _copy_to_clipboard(self, text):
        """安全地写入剪贴板，失败时提示而非崩溃。

        优先使用 pyperclip（程序退出后内容仍保留在系统剪贴板）；
        未安装时回退到 tkinter 自带剪贴板（程序运行期间有效）。
        """
        try:
            if pyperclip is not None:
                pyperclip.copy(text)
            else:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.root.update()
            return True
        except Exception as e:
            self.log(f"写入剪贴板失败: {e}", "<错误>")
            messagebox.showerror("剪贴板错误", f"无法写入剪贴板：{e}")
            return False

    # ---------------- 界面 ----------------
    def build_ui(self):
        default_font = ('微软雅黑', 10)
        button_font = ('微软雅黑', 12)
        help_font = ('微软雅黑', 9)
        log_font = ('Consolas', 10)

        self.root.option_add('*Font', default_font)

        # 多标签页界面：存档管理（默认页）+ 启动
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        tab_save = ttk.Frame(self.notebook, padding="6")
        tab_launch = ttk.Frame(self.notebook, padding="6")
        self.notebook.add(tab_save, text="存档管理")
        self.notebook.add(tab_launch, text="启动")

        self.build_save_tab(tab_save, button_font, help_font, log_font)
        self.build_launch_tab(tab_launch, button_font, log_font)

    def build_save_tab(self, main, button_font, help_font, log_font):
        """「存档管理」页：左侧按钮 + 右侧存档位与日志。"""
        main.columnconfigure(0, weight=0)   # 左侧不缩放
        main.columnconfigure(1, weight=1)   # 右侧缩放
        main.rowconfigure(0, weight=1)

        # ---------- 左侧按钮区 ----------
        left = ttk.Frame(main, width=220)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 15))
        left.grid_propagate(False)

        btn_style = ttk.Style()
        btn_style.configure("Large.TButton", font=button_font, padding=12)

        self.btn_save = ttk.Button(left, text="存档", style="Large.TButton",
                                   command=self.save_action)
        self.btn_save.pack(fill=tk.X, pady=8, padx=15)

        self.btn_load = ttk.Button(left, text="读档", style="Large.TButton",
                                   command=self.load_action)
        self.btn_load.pack(fill=tk.X, pady=8, padx=15)

        self.btn_cancel = ttk.Button(left, text="取消存档", style="Large.TButton",
                                     command=self.cancel_action)
        self.btn_cancel.pack(fill=tk.X, pady=8, padx=15)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10, padx=15)

        self.btn_check = ttk.Button(left, text="检查异常文件", style="Large.TButton",
                                    command=self.check_action)
        self.btn_check.pack(fill=tk.X, pady=8, padx=15)

        help_text = (
            "📖 操作说明\n\n"
            "【存档】\n"
            "1. 选中一个存档位\n"
            "2. 点击「存档」\n"
            "3. 在游戏导出对话框中粘贴路径并保存\n\n"
            "【读档】\n"
            "1. 选中一个存档位\n"
            "2. 点击「读档」\n"
            "3. 在游戏导入中粘贴 (Ctrl+V)\n\n"
            "【备注】\n"
            "在右侧输入框填写，自动保存到本地。\n\n"
            "【检查异常文件】\n"
            "查看不合规文件。\n"
        )
        help_label = ttk.Label(left, text=help_text, justify=tk.LEFT,
                               font=help_font, wraplength=190)
        help_label.pack(side=tk.BOTTOM, fill=tk.X, pady=15, padx=15)

        # ---------- 右侧区域 ----------
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")

        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)   # 存档位区域
        right.rowconfigure(1, weight=2)   # 日志区域

        slots_frame = ttk.LabelFrame(right, text="存档位", padding="8")
        slots_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        slots_frame.columnconfigure(0, weight=1)
        slots_frame.rowconfigure(0, weight=1)

        canvas = tk.Canvas(slots_frame, highlightthickness=0)
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

        self.slot_widgets = []
        for i in range(SLOT_COUNT):
            row = ttk.Frame(inner, relief=tk.FLAT, padding=5)
            row.pack(fill=tk.X, pady=3)

            rb = ttk.Radiobutton(row, variable=self.selected_slot, value=i)
            rb.pack(side=tk.LEFT, padx=8)

            lbl = ttk.Label(row, text=f"{i + 1:02d}. {SLOT_NAMES[i]}",
                            width=12, anchor=tk.W, font=('微软雅黑', 10))
            lbl.pack(side=tk.LEFT, padx=8)

            time_lbl = ttk.Label(row, width=20, anchor=tk.W,
                                 font=('微软雅黑', 9))
            time_lbl.pack(side=tk.LEFT, padx=8)

            note_entry = ttk.Entry(row, width=35)
            note_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
            note_entry.insert(0, self.notes[i])
            note_entry.bind("<FocusOut>",
                            lambda e, idx=i: self.save_note(idx, e.widget.get()))

            self.slot_widgets.append({
                'time_lbl': time_lbl,
                'note_entry': note_entry,
            })

        self.update_slots_display()

        log_frame = ttk.LabelFrame(right, text="输出日志", padding="8")
        log_frame.grid(row=1, column=0, sticky="nsew")

        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD,
                                                  font=log_font)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.config(state=tk.DISABLED)

        self.log("程序启动")
        self.log(f"存档库: {SAVE_LIBRARY}")
        self.log(f"临时文件夹: {TEMP_FOLDER}")

    # ---------------- 启动页（本地静态 Web 服务） ----------------
    def build_launch_tab(self, parent, button_font, log_font):
        """「启动」页：一键创建本地 Web 服务并在浏览器新窗口打开。"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        cfg = ttk.LabelFrame(parent, text="本地 Web 服务（仅绑定 127.0.0.1）",
                             padding="10")
        cfg.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        cfg.columnconfigure(1, weight=1)

        ttk.Label(cfg, text="服务目录:").grid(row=0, column=0, sticky="w",
                                             pady=4, padx=(0, 6))
        self.web_dir_var = tk.StringVar(value=str(WEB_ROOT))
        ttk.Entry(cfg, textvariable=self.web_dir_var).grid(row=0, column=1,
                                                           sticky="ew", pady=4)
        ttk.Button(cfg, text="浏览...",
                   command=self.web_browse_dir).grid(row=0, column=2,
                                                     padx=(6, 0), pady=4)

        ttk.Label(cfg, text="端口:").grid(row=1, column=0, sticky="w",
                                          pady=4, padx=(0, 6))
        self.web_port_var = tk.StringVar(value="")
        ttk.Entry(cfg, textvariable=self.web_port_var, width=10).grid(
            row=1, column=1, sticky="w", pady=4)
        ttk.Label(cfg, text="留空 = 自动选择空闲端口",
                  foreground="#666666").grid(row=1, column=2, sticky="w",
                                             padx=(6, 0), pady=4)

        btns = ttk.Frame(cfg)
        btns.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 2))
        self.btn_web_start = ttk.Button(
            btns, text="🚀 启动并打开浏览器", style="Large.TButton",
            command=self.web_start_action)
        self.btn_web_start.pack(side=tk.LEFT, padx=(0, 10))
        self.btn_web_stop = ttk.Button(
            btns, text="停止服务", style="Large.TButton",
            command=self.web_stop_action, state=tk.DISABLED)
        self.btn_web_stop.pack(side=tk.LEFT)

        ttk.Label(parent, text="提示：把需要访问的站点/游戏文件放入服务目录"
                               "（默认 web/），启动后浏览器访问 "
                               "http://127.0.0.1:<端口>/",
                  foreground="#666666").grid(row=1, column=0, sticky="w",
                                             pady=(0, 4))

        log_frame = ttk.LabelFrame(parent, text="服务日志", padding="6")
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.web_log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD,
                                                      font=log_font)
        self.web_log_text.grid(row=0, column=0, sticky="nsew")
        self.web_log_text.config(state=tk.DISABLED)

        self.web_log("就绪：选择服务目录与端口后，点击「启动并打开浏览器」。",
                     "<启动>")

    def web_browse_dir(self):
        """选择服务目录。"""
        initial = self.web_dir_var.get().strip()
        if not os.path.isdir(initial):
            initial = str(BASE_DIR)
        chosen = filedialog.askdirectory(title="选择服务目录", initialdir=initial)
        if chosen:
            self.web_dir_var.set(chosen)

    def web_start_action(self):
        """一键创建本地 Web 服务并打开浏览器。"""
        if self.web_server is not None:
            self.web_log("服务已在运行，请先「停止服务」。", "<启动>")
            return

        # 服务目录：不存在则自动创建
        root_dir = Path(self.web_dir_var.get().strip())
        if not root_dir.is_dir():
            try:
                root_dir.mkdir(parents=True, exist_ok=True)
                self.web_log(f"服务目录不存在，已自动创建: {root_dir}", "<启动>")
            except OSError as e:
                messagebox.showerror("启动失败", f"无法使用服务目录 {root_dir}：{e}")
                return

        # 端口：留空自动选择
        port_text = self.web_port_var.get().strip()
        port = 0  # 0 = 由系统分配空闲端口
        if port_text:
            try:
                port = int(port_text)
                if not 0 < port < 65536:
                    raise ValueError
            except ValueError:
                messagebox.showerror("端口无效",
                                     "端口必须是 1-65535 之间的数字，或留空自动选择。")
                return

        try:
            _WebHandler._queue = self.event_queue
            handler = functools.partial(_WebHandler,
                                        directory=str(root_dir.resolve()))
            self.web_server = _ThreadingHTTPServer(("127.0.0.1", port), handler)
            actual_port = self.web_server.server_address[1]
        except OSError as e:
            self.web_server = None
            self.web_log(f"启动失败: {e}", "<错误>")
            messagebox.showerror(
                "启动失败",
                f"无法在端口 {port_text or '(自动)'} 启动服务：\n{e}")
            return

        self.web_thread = threading.Thread(target=self.web_server.serve_forever,
                                           name="web-server", daemon=True)
        self.web_thread.start()
        self.web_url = f"http://127.0.0.1:{actual_port}/"
        self.web_port_var.set(str(actual_port))
        self.btn_web_start.config(state=tk.DISABLED)
        self.btn_web_stop.config(state=tk.NORMAL)
        self.web_log(f"服务已启动: {self.web_url}", "<启动>")
        self.web_log(f"服务目录: {root_dir.resolve()}", "<启动>")
        self.web_log("仅监听 127.0.0.1，只有本机可以访问。", "<启动>")
        # 等服务就绪后在浏览器（新窗口）打开
        self.root.after(300, lambda: self._open_browser_new_window(self.web_url))

    def web_stop_action(self):
        """停止本地 Web 服务。"""
        if self.web_server is None:
            self.web_log("服务未在运行。", "<停止>")
            return
        self._web_stop_internal()
        self.web_log("服务已停止。", "<停止>")
        self.btn_web_start.config(state=tk.NORMAL)
        self.btn_web_stop.config(state=tk.DISABLED)

    def _web_stop_internal(self):
        """内部停止服务（不更新界面），退出程序时也调用。"""
        server, self.web_server = self.web_server, None
        if server is None:
            return
        try:
            server.shutdown()  # 须由服务线程之外的线程调用
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
        self.web_thread = None

    def _open_browser_new_window(self, url):
        """优先用 Edge/Chrome 在新窗口打开；找不到则回退 webbrowser。"""
        candidates = [
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(
                r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(
                r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        ]
        for exe in candidates:
            if os.path.isfile(exe):
                try:
                    subprocess.Popen([exe, "--new-window", url])
                    self.web_log("已在浏览器新窗口打开。", "<打开浏览器>")
                    return
                except OSError:
                    break
        try:
            webbrowser.open(url, new=1)
            self.web_log("已调用系统默认浏览器打开。", "<打开浏览器>")
        except Exception as e:
            self.web_log(f"打开浏览器失败: {e}", "<错误>")

    # ---------------- 备注 ----------------
    def save_note(self, idx, text):
        """单条备注变更时调用（FocusOut 触发），限制长度并持久化。"""
        text = text[:MAX_NOTE_LEN]
        if self.notes[idx] != text:
            self.notes[idx] = text
            self._save_notes()

    def commit_notes(self):
        """把所有输入框当前内容同步进内存并持久化（操作前/关闭时调用）。"""
        for i, w in enumerate(self.slot_widgets):
            text = w['note_entry'].get()[:MAX_NOTE_LEN]
            if self.notes[i] != text:
                self.notes[i] = text
        self._save_notes()

    def update_slots_display(self):
        """只刷新时间显示；不重写备注输入框，避免打断正在输入的内容。"""
        self.load_slot_info()
        for i, info in enumerate(self.slot_info):
            if info['exists']:
                self.slot_widgets[i]['time_lbl'].config(text=info['time'])
            else:
                self.slot_widgets[i]['time_lbl'].config(text="(空)")

    # ---------------- 日志 ----------------
    def _append_log(self, widget, msg, tag=""):
        """向指定日志控件追加一行带时间戳的消息。"""
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
        # 界面尚未构建完成时（例如 __init__ 早期加载备注失败）退化为打印
        if not hasattr(self, "log_text") or self.log_text is None:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {tag} {msg}" if tag else f"[{timestamp}] {msg}")
            return
        self._append_log(self.log_text, msg, tag)

    def web_log(self, msg, tag=""):
        """写入「启动」页的服务日志。"""
        if not hasattr(self, "web_log_text") or self.web_log_text is None:
            return
        self._append_log(self.web_log_text, msg, tag)

    # ---------------- 取消 / 中断 ----------------
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

    # ---------------- 存档 ----------------
    def save_action(self):
        self.commit_notes()

        if self._is_monitoring():
            self.log("已有存档操作进行中，请先取消或等待完成", "<执行存档>")
            return

        slot = self.selected_slot.get()
        slot_name = SLOT_NAMES[slot]
        slot_num = slot + 1

        if self.slot_info[slot]['exists']:
            msg = (f"对 {slot_num:02d} 号位 {slot_name} 进行存档操作？"
                   f"将会覆盖现有存档。")
        else:
            msg = f"对 {slot_num:02d} 号位 {slot_name} 进行存档操作？"

        if not messagebox.askokcancel(APP_NAME, msg):
            self.log("用户取消存档操作", "<取消存档>")
            return

        self.log(f"开始对 {slot_num:02d} 号位进行存档操作", "<执行存档>")

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
        """后台线程：监控临时文件夹中新增的 .txt 文件。"""
        try:
            start = time.time()
            while time.time() - start < MONITOR_TIMEOUT:
                if self.cancel_event.is_set():
                    self.event_queue.put(("cancelled",))
                    return
                time.sleep(0.5)
                now_files = set(os.listdir(TEMP_FOLDER))
                new_files = now_files - before_files
                txt_files = [f for f in new_files
                             if f.lower().endswith(".txt")]
                if txt_files:
                    latest = max(
                        txt_files,
                        key=lambda f: self._safe_mtime(os.path.join(TEMP_FOLDER, f)),
                    )
                    # 等待文件写入稳定，避免读到半成品
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
        """等待文件大小在一段时间内保持不变且非空。"""
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

    # ---------------- 事件队列轮询（UI 线程） ----------------
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

    def process_new_file(self, filename, slot):
        """校验并移动检测到的新文件到存档库。"""
        src = os.path.join(TEMP_FOLDER, filename)
        dest_name = f"{SLOT_NAMES[slot]}_{slot + 1}.kgsav"
        dest = os.path.join(SAVE_LIBRARY, dest_name)

        try:
            size = os.path.getsize(src)
            if size <= 0:
                raise ValueError("导出文件为空")
            if size > MAX_SAVE_SIZE:
                raise ValueError(f"导出文件过大（{size} 字节）")

            # 内容非空校验
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(64)
            if not head.strip():
                raise ValueError("导出文件内容为空")

            shutil.move(src, dest)
            self.log(f"成功存档: {filename} → {dest_name}", "<完成存档>")
            self.update_slots_display()
        except Exception as e:
            self.log(f"处理存档失败: {e}", "<执行存档>")
            messagebox.showerror("存档失败", str(e))

    # ---------------- 读档 ----------------
    def load_action(self):
        self.stop_ongoing_operation()
        self.commit_notes()

        slot = self.selected_slot.get()
        if not self.slot_info[slot]['exists']:
            messagebox.showwarning(APP_NAME, f"{SLOT_NAMES[slot]} 没有存档文件")
            return

        slot_file = self.slot_info[slot]['filename']
        try:
            size = os.path.getsize(slot_file)
            if size <= 0:
                raise ValueError("存档文件为空")
            if size > MAX_SAVE_SIZE:
                raise ValueError(f"存档文件过大（{size} 字节）")

            with open(slot_file, "r", encoding="utf-8") as f:
                content = f.read()

            if not self._copy_to_clipboard(content):
                return

            self.log(f"已将 {SLOT_NAMES[slot]} 的存档内容复制到剪贴板",
                     "<读档操作>")
            self.log("请打开游戏，点击 Options → Import，粘贴 (Ctrl+V) 并确认。")
            messagebox.showinfo(
                APP_NAME,
                f"已复制 {SLOT_NAMES[slot]} 存档到剪贴板，可以导入到游戏中了。")
        except Exception as e:
            self.log(f"读取存档失败: {e}", "<读档操作>")
            messagebox.showerror("读档失败", str(e))

    # ---------------- 检查异常文件 ----------------
    def check_action(self):
        self.stop_ongoing_operation()
        self.commit_notes()

        self.log("开始检查异常文件...", "<检查异常>")

        valid_names = {f"{SLOT_NAMES[i]}_{i + 1}.kgsav"
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

        # 合规文件名但内容为空
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

    # ---------------- 退出 ----------------
    def _on_close(self):
        self.commit_notes()
        self.cancel_event.set()
        self._web_stop_internal()
        self.root.destroy()


if __name__ == "__main__":
    setup_dpi_and_scaling()
    root = tk.Tk()
    app = KGSaveManager(root)
    root.mainloop()
