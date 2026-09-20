"""HTML 前端的本地 HTTP 服务：静态资源 + JSON API + 事件长轮询（纯标准库）。

只绑定 127.0.0.1；页面与 API 同源，因此浏览器不需要任何额外权限。
"""

import json
import os
import posixpath
import socketserver
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

MAX_BODY = 8 * 1024 * 1024        # 存档粘贴可能较大

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".ico": "image/x-icon",
    ".png": "image/png",
}


class EventBuffer:
    """线程安全的事件缓冲（带自增序号，页面按序号增量拉取）。"""

    def __init__(self, limit=800):
        self._items = []
        self._seq = 0
        self._lock = threading.Lock()
        self._limit = limit

    def push(self, item):
        with self._lock:
            self._seq += 1
            self._items.append((self._seq, item))
            if len(self._items) > self._limit:
                self._items = self._items[-self._limit:]

    def since(self, seq):
        with self._lock:
            items = [item for s, item in self._items if s > seq]
            return items, self._seq


class _Handler(BaseHTTPRequestHandler):
    server_version = "KGSaveManager/1.0"

    # 访问日志不写控制台（--verbose 时才打印，且立刻刷新，便于重定向到文件观察）
    def log_message(self, fmt, *args):
        if getattr(self.server, "kgsm_verbose", False):
            print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    # ---------------- 工具 ----------------
    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        if not path.is_file():
            self.send_error(404, "not found")
            return
        ctype = CONTENT_TYPES.get(path.suffix.lower(),
                                  "application/octet-stream")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0 or length > MAX_BODY:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # ---------------- 路由 ----------------
    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path
        if route in ("/", "/index.html"):
            self._file(self.server.assets / "index.html")
            return
        if route.startswith("/assets/"):
            rel = urllib.parse.unquote(route[len("/assets/"):])
            rel = posixpath.normpath(rel).lstrip("/")
            if rel.startswith("..") or os.path.isabs(rel):
                self.send_error(403, "forbidden")
                return
            self._file(self.server.assets / rel)
            return
        if route == "/api/state":
            self._json({"ok": True, "result": self.server.api.state()})
            return
        if route == "/api/events":
            query = urllib.parse.parse_qs(parsed.query)
            try:
                since = int(query.get("since", ["0"])[0])
            except ValueError:
                since = 0
            events, seq = self.server.outbox.since(since)
            self._json({"ok": True, "events": events, "next": seq})
            return
        self.send_error(404, "not found")

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path
        body = self._read_body()
        if route == "/api/call":
            method = str(body.get("method") or "")
            params = body.get("params") or {}
            func = getattr(self.server.api, method, None)
            if func is None or method.startswith("_") or not callable(func):
                self._json({"ok": False, "error": f"unknown method: {method}"},
                           status=400)
                return
            try:
                result = func(**params) if isinstance(params, dict) else func()
            except TypeError as e:
                self._json({"ok": False, "error": f"bad params: {e}"},
                           status=400)
                return
            except Exception as e:                       # noqa: BLE001
                self._json({"ok": False,
                            "error": f"{type(e).__name__}: {e}"},
                           status=500)
                return
            self._json({"ok": True, "result": result})
            return
        if route == "/api/answer":
            ok = self.server.ui.answer(body.get("id"), body.get("ok"),
                                       body.get("text"))
            self._json({"ok": bool(ok)})
            return
        if route == "/api/shutdown":
            self._json({"ok": True})
            if self.server.on_shutdown is not None:
                threading.Thread(target=self.server.on_shutdown,
                                 daemon=True).start()
            return
        self.send_error(404, "not found")


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


class AppServer:
    """页面与 API 的宿主机（生命周期管理）。"""

    def __init__(self, api, ui_port, outbox, assets, port=0,
                 on_shutdown=None, verbose=False):
        self.api = api
        self.ui = ui_port
        self.outbox = outbox
        self.assets = assets
        self.port = port
        self.on_shutdown = on_shutdown
        self.verbose = verbose
        self._server = None
        self._thread = None
        self.url = ""

    @property
    def running(self):
        return self._server is not None

    def start(self):
        handler = _Handler
        self._server = _ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self._server.api = self.api
        self._server.ui = self.ui
        self._server.outbox = self.outbox
        self._server.assets = self.assets
        self._server.on_shutdown = self.on_shutdown
        self._server.kgsm_verbose = self.verbose
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        name="webapp-http", daemon=True)
        self._thread.start()
        self.url = f"http://127.0.0.1:{self.port}/"
        return self.url

    def stop(self):
        server, self._server = self._server, None
        if server is None:
            return
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
