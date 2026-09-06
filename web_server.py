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
                marker = text.lower().rfind("</body>")
                script = '<script src="/kgsm-bridge.js"></script>'
                if marker >= 0:
                    text = text[:marker] + script + text[marker:]
                else:
                    text += script
                body = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type",
                                 "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
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
