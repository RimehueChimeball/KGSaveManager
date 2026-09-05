"""
本地静态文件 Web 服务（http.server + socketserver）。

- 只绑定 127.0.0.1，仅本机可访问
- 多线程处理（socketserver.ThreadingMixIn）
- 访问日志经事件队列转发到 UI 线程，不写控制台
"""

import functools
import http.server
import os
import socketserver
import subprocess
import webbrowser

EDGE_PATHS = [
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
]
CHROME_PATHS = [
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
]


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

    def start(self, directory, port=0):
        """启动服务。

        :param directory: 服务根目录（需已存在）
        :param port: 端口号，0 表示自动分配空闲端口
        :return: (url, actual_port)
        :raises OSError: 端口被占用/绑定失败等
        """
        if self.running:
            raise RuntimeError("服务已在运行")
        root = str(os.path.abspath(directory))
        _WebHandler._queue = self._queue
        handler = functools.partial(_WebHandler, directory=root)
        self._server = _ThreadingHTTPServer(("127.0.0.1", port), handler)
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


def open_in_browser(url, browser_path="", new_window=True):
    """用指定浏览器打开地址。

    :param url: 要打开的地址
    :param browser_path: 配置的浏览器 exe 路径；空串 = 系统默认浏览器
    :param new_window: True=新窗口（仅启动游戏用）；
                       False=常规打开（超链接用，在现有窗口新开标签页）
    :return: 使用的打开方式描述（'Edge'/'Chrome'/'custom'/'default browser'/None）
    """
    candidates = []
    custom = browser_path.strip() if browser_path else ""
    if custom:
        candidates.append(custom)
    for exe in EDGE_PATHS + CHROME_PATHS:
        if exe not in candidates:
            candidates.append(exe)

    for exe in candidates:
        if os.path.isfile(exe):
            try:
                args = [exe]
                if new_window:
                    args.append("--new-window")
                args.append(url)
                subprocess.Popen(args)
                if exe == custom:
                    return "custom"
                return "Edge" if exe in EDGE_PATHS else "Chrome"
            except OSError:
                break
    try:
        webbrowser.open(url, new=1 if new_window else 0)
        return "default browser"
    except Exception:
        return None
