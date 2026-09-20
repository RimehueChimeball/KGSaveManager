"""
本地静态文件 Web 服务（http.server + socketserver）。

- 只绑定 127.0.0.1，仅本机可访问
- 多线程处理（socketserver.ThreadingMixIn）
- 访问日志经事件队列转发到 UI 线程，不写控制台

另外负责按配置打开浏览器窗口（界面窗口固定用应用窗口；游戏窗口按配置页的
「游戏窗口位置/状态」，最大化由 Win32 的 ShowWindow 落实，见本文件末尾）。
"""

import ctypes
import functools
import http.server
import os
import socketserver
import subprocess
import sys
import time
import urllib.parse
import webbrowser

from web_bridge import bridge_js


class _WebHandler(http.server.SimpleHTTPRequestHandler):
    """静态文件请求处理器：访问日志转发到 UI 事件队列。"""

    _queue = None  # 启动服务前注入事件队列

    def log_message(self, fmt, *args):
        if self._queue is not None:
            msg = "%s - - [%s] %s" % (
                self.address_string(), self.log_date_time_string(), fmt % args)
            self._queue.put(("server_log", msg))


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """多线程版本地 HTTP 服务器（服务线程随主程序退出）。"""

    daemon_threads = True


class _BridgeWebHandler(_WebHandler):
    """带存档桥的处理器：HTML 响应注入 bridge.js，并提供 /kgsm-bridge.js。

    - LocalWebServer.start(bridge=...) 时启用；游戏文件本身不被修改，
      注入只发生在内存响应里。
    """

    def _bridge(self):
        return getattr(self.server, "kgsm_bridge", None)

    def do_GET(self):
        bridge = self._bridge()
        path = urllib.parse.urlsplit(self.path).path
        if bridge is not None and path == "/kgsm-bridge.js":
            js = bridge_js(getattr(self.server, "kgsm_ws_url", ""))
            body = js.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type",
                             "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if bridge is not None and (path.endswith((".html", ".htm"))
                                   or path == "/"):
            target = self.translate_path(path)
            if os.path.isdir(target):
                target = os.path.join(target, "index.html")
            if os.path.isfile(target):
                try:
                    with open(target, "rb") as f:
                        raw = f.read()
                except OSError:
                    self.send_error(403)
                    return
                text = raw.decode("utf-8", "replace")
                script = '<script src="/kgsm-bridge.js"></script>'
                low = text.lower()
                for marker_txt in ("</body>", "</html>"):
                    marker = low.rfind(marker_txt)
                    if marker >= 0:
                        text = (text[:marker] + script +
                                text[marker:])
                        break
                else:
                    text += script
                body = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type",
                                 "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
        super().do_GET()


class LocalWebServer:
    """本地静态文件服务的生命周期管理。"""

    def __init__(self, event_queue):
        self._queue = event_queue
        self._server = None
        self._thread = None
        self._url = None

    @property
    def running(self):
        return self._server is not None

    @property
    def url(self):
        return self._url

    def start(self, directory, port=0, bridge=None):
        """启动服务。

        :param directory: 服务根目录（需已存在）
        :param port: 端口号，0 表示自动分配空闲端口
        :param bridge: WebSocketBridge 实例；提供时启用页面注入
        :return: (url, actual_port)
        :raises OSError: 端口被占用/绑定失败等
        """
        if self.running:
            raise RuntimeError("服务已在运行")
        root = os.path.abspath(directory)
        _WebHandler._queue = self._queue
        handler_cls = _BridgeWebHandler if bridge is not None else _WebHandler
        handler = functools.partial(handler_cls, directory=root)
        self._server = _ThreadingHTTPServer(("127.0.0.1", port), handler)
        if bridge is not None:
            setattr(self._server, "kgsm_bridge", bridge)
            setattr(self._server, "kgsm_ws_url",
                    f"ws://127.0.0.1:{bridge.port}/")
        actual_port = self._server.server_address[1]
        self._thread = __import__("threading").Thread(
            target=self._server.serve_forever, name="web-server", daemon=True)
        self._thread.start()
        self._url = f"http://127.0.0.1:{actual_port}/"
        return self._url, actual_port

    def stop(self):
        """停止服务；未运行时静默返回。"""
        server, self._server = self._server, None
        self._url = None
        if server is None:
            return
        try:
            server.shutdown()   # 需由 serve_forever 所在线程之外调用
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
        self._thread = None


def _is_known_engine(exe):
    """是否为支持 --new-window 参数的主流浏览器内核。"""
    name = os.path.basename(exe).lower()
    return any(k in name for k in ("edge", "chrome", "chromium", "firefox"))


def _launch(exe, url, new_window):
    args = [exe]
    if new_window and _is_known_engine(exe):
        args.append("--new-window")
    args.append(url)
    subprocess.Popen(args)


def _window_plan(cfg):
    """从配置取出 (启动位置, 页面侧窗口状态, 窗口状态)。

    :return: (mode, fit, state)：mode 为 'app'/'tab'；fit 为 'auto'/'max'/'full'
    """
    mode = getattr(cfg, "launch_mode", "app")
    state = getattr(cfg, "window_state", "normal")
    fit = {"normal": "auto", "max": "max", "full": "full"}.get(state, "auto")
    return mode, fit, state


def app_window_args(exe, url, width=1320, height=840, fit="auto",
                    fullscreen=False, window_size=None):
    """应用窗口模式（无地址栏/标签页）的启动参数。

    :param fit: 写进 URL 的页面侧窗口状态（'auto' = 页面自己调成横向窗口）；
        传空串表示这个页面不认识该参数（例如游戏页）
    :param fullscreen: 命令行 --start-fullscreen，只在"浏览器进程由本次启动创建"
        时生效（实测：浏览器已经在运行时会被忽略，窗口沿用记忆尺寸），
        因此调用方还会用 Win32 兜底
    :param window_size: 是否带 --window-size；默认只在 fit=auto 时带
    """
    if fit:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}fit={fit}"
    if window_size is None:
        window_size = fit == "auto"
    args = [exe, f"--app={url}"]
    if window_size:
        args.append(f"--window-size={int(width)},{int(height)}")
    if fullscreen:
        args.append("--start-fullscreen")
    return args


def open_app_window(url, browser_path="", width=1320, height=840, fit="auto",
                    fullscreen=False, window_size=None):
    """以「应用窗口」方式打开地址（Edge/Chrome 的 --app=，无地址栏与标签页）。

    :return: 'app'（应用窗口）/ 其他打开方式字符串 / None（失败）
    """
    exe = (browser_path or "").strip()
    if not exe or not os.path.isfile(exe):
        try:
            from config_store import detect_browser_path
            exe = detect_browser_path() or ""
        except Exception:
            exe = ""
    if exe and os.path.isfile(exe) and _is_known_engine(exe):
        try:
            subprocess.Popen(app_window_args(exe, url, width, height, fit,
                                             fullscreen, window_size))
            return "app"
        except OSError:
            pass
    return open_in_browser(url, browser_path=browser_path, new_window=True)


def open_game_window(cfg, url, width=1320, height=840):
    """按配置打开游戏页（「启动游戏」用它）。

    只有游戏窗口受配置页的「游戏窗口位置/状态」影响：独立窗口（应用模式）或浏览器
    标签页；应用模式下「最大化/全屏」还会用 Win32 落实——命令行
    `--start-fullscreen` 只在本次启动创建浏览器进程时生效，浏览器已经在运行时会被
    忽略（实测），所以窗口出现后再按状态调整一次（`ShowWindow` 是跨进程可行的，
    实测客户区正好等于工作区）。

    :return: (打开方式描述, 提示标记)：标记为 'full_fallback' 时表示全屏参数被浏览器
        忽略、已退化为最大化；失败返回 (None, "")
    """
    mode, _fit, state = _window_plan(cfg)
    if mode == "tab":
        return open_in_browser(url, browser_path=cfg.browser,
                               new_window=False), ""
    before = _top_level_windows() if state != "normal" else None
    how = open_app_window(url, browser_path=cfg.browser, width=width,
                          height=height, fit="", window_size=True,
                          fullscreen=(state == "full"))
    if not (how == "app" and state != "normal"):
        return how, ""
    hwnd = _wait_new_window(before) if before is not None else None
    if not hwnd:
        return how, ""
    if state == "full":
        if _is_fullscreen(hwnd):
            return how, ""
        _maximize_window(hwnd)
        return how, "full_fallback"
    _maximize_window(hwnd)
    return how, ""


# ---------------- Win32：窗口状态的兜底 ----------------
# 页面侧的 resizeTo 只能把"窗口外框"设成工作区大小，四周会留下可见边框
# （实测客户区 1904×1024，看着像"手搓的最大化"）；ShowWindow(SW_MAXIMIZE)
# 得到的才是真正的最大化（实测客户区 1920×1032 = 工作区）。

_SW_MAXIMIZE = 3


def _win32():
    """返回 (user32, win32gui?)——非 Windows 或调用失败时返回 None。"""
    if sys.platform != "win32":
        return None
    try:
        return ctypes.windll.user32
    except Exception:
        return None


def _top_level_windows():
    """当前所有可见的 Chromium 顶层窗口句柄集合（用于找出新开的那个窗口）。"""
    user32 = _win32()
    if user32 is None:
        return set()
    found = set()
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _param):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            if buf.value.startswith("Chrome_WidgetWin"):
                found.add(int(hwnd))
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(CB(cb), 0)
    except Exception:
        return set()
    return found


def _wait_new_window(before, timeout=8.0):
    """等新开的窗口出现（返回句柄；超时返回 None）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        new = _top_level_windows() - set(before or ())
        if new:
            return sorted(new)[-1]
        time.sleep(0.25)
    return None


def _window_rect(hwnd):
    """窗口矩形 (left, top, right, bottom)；失败返回 None。"""
    user32 = _win32()
    if user32 is None or not hwnd:
        return None

    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    rect = _RECT()
    if not user32.GetWindowRect(ctypes.c_void_p(int(hwnd)),
                                ctypes.byref(rect)):
        return None
    return (rect.left, rect.top, rect.right, rect.bottom)


def _screen_height():
    user32 = _win32()
    return user32.GetSystemMetrics(1) if user32 is not None else 0


def _is_fullscreen(hwnd):
    """窗口是否已经真的全屏（高度≈屏幕高度；--start-fullscreen 生效时是这样）。"""
    rect = _window_rect(hwnd)
    height = _screen_height()
    return bool(rect and height and (rect[3] - rect[1]) >= height - 2)


def _maximize_window(hwnd):
    """把窗口设为真正的最大化（客户区正好等于工作区）。"""
    user32 = _win32()
    if user32 is None or not hwnd:
        return False
    try:
        user32.ShowWindow(ctypes.c_void_p(int(hwnd)), _SW_MAXIMIZE)
        return True
    except Exception:
        return False


def open_in_browser(url, browser_path="", new_window=True):
    """打开地址（逐级兜底，任何异常都不外抛）。

    :param url: 要打开的地址
    :param browser_path: 配置的浏览器 exe 路径
    :param new_window: True=新窗口（仅启动游戏用）；False=常规打开（超链接）
    :return: 使用方式描述（'custom'/'system default'/'shell default'/None）
    """
    # 1) 配置的浏览器（若路径仍有效）
    custom = (browser_path or "").strip()
    if custom and os.path.isfile(custom):
        try:
            _launch(custom, url, new_window)
            return "custom"
        except OSError:
            pass

    # 2) 动态检测系统默认浏览器（注册表）
    exe = ""
    try:
        from config_store import detect_browser_path
        exe = detect_browser_path() or ""
    except Exception:
        exe = ""
    if exe and os.path.isfile(exe):
        try:
            _launch(exe, url, new_window)
            return "system default"
        except OSError:
            pass

    # 3) 兜底：系统默认关联（webbrowser → os.startfile）
    try:
        ok = webbrowser.open(url, new=1 if new_window else 0)
        if ok:
            return "shell default"
    except Exception:
        pass
    try:
        os.startfile(url)
        return "shell default"
    except Exception:
        return None
