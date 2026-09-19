"""本地 Web 服务与存档桥的生命周期（逻辑层，无 GUI 依赖）。

前端只需要：`start()`（可选顺带打开浏览器）、`stop()`、`status()`；
所有日志通过 `UiPort.web_log` 输出，失败通过 `UiPort.fail` 提示。
"""

import socket
from pathlib import Path

from web_bridge import WebSocketBridge
from web_server import LocalWebServer, open_in_browser


def _port_in_use(port, timeout=0.35):
    """端口上是否已有服务在监听。

    Windows 的 SO_REUSEADDR 语义允许重复绑定，光靠绑定失败判断不出来，
    所以直接尝试连接一次。
    """
    if not port:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", int(port))) == 0


class ServerController:
    """启动/停止「启动游戏」用的本地静态服务与存档桥。"""

    def __init__(self, *, ui, cfg, t, events, logger=None,
                 browser_new_window=True):
        self.ui = ui
        self.cfg = cfg
        self.t = t
        self.logger = logger
        self.browser_new_window = browser_new_window
        self._events = events
        self.lweb = LocalWebServer(events)
        self.bridge = None

    # ---------------- 状态 ----------------
    @property
    def running(self):
        return self.lweb.running

    @property
    def url(self):
        return self.lweb.url

    def status(self):
        """给前端用的状态快照。"""
        return {
            "running": self.running,
            "url": self.url or "",
            "bridge_port": self.bridge.port if self.bridge else None,
            "has_client": bool(self.bridge and self.bridge.has_client),
            "game_dir": self.cfg.game_dir,
            "port": self.cfg.port,
        }

    # ---------------- 启停 ----------------
    def start(self, open_browser=False):
        """按配置启动服务。

        :return: 访问地址；失败返回 None（已通过界面端口提示）
        """
        directory = self.cfg.game_dir.strip()
        if not directory:
            self.ui.fail(self.t("err.no_dir"), self.t("err.launch_fail"))
            return None
        root_dir = Path(directory)
        if not root_dir.is_dir():
            self.ui.fail(self.t("err.dir_missing", dir=directory),
                         self.t("err.launch_fail"))
            return None

        port = 0
        port_text = self.cfg.port.strip()
        if port_text:
            try:
                port = int(port_text)
                if not 0 < port < 65536:
                    raise ValueError
            except ValueError:
                self.ui.fail(self.t("err.port_invalid"),
                             self.t("err.launch_fail"))
                return None
            # Windows 下 SO_REUSEADDR 会"成功"绑定已占用的端口，导致服务起了却
            # 收不到连接，所以先探一下端口是否真的空闲，占用就退回自动端口。
            if _port_in_use(port):
                self.ui.web_log(
                    self.t("msg.port_busy_fallback", port=port),
                    self.t("tag.error"))
                self._log_warn(f"固定端口 {port} 已被占用，本次改用自动端口")
                port_text, port = "", 0

        if self.running:
            self.ui.web_log(self.t("msg.server_restart"), self.t("tag.start"))
            self.stop()

        bridge = None
        try:
            bridge = WebSocketBridge()
            bridge.set_ui_queue(self._events)
            bridge.start()
            url, actual_port = self.lweb.start(str(root_dir), port,
                                               bridge=bridge)
        except OSError as e:
            if bridge is not None:
                try:
                    bridge.stop()
                except Exception:
                    pass
            self.ui.web_log(self.t("msg.server_fail", e=e), self.t("tag.error"))
            self._log_error(f"服务启动失败 port={port_text or '(auto)'}: {e}")
            self.ui.fail(f"port={port_text or '(auto)'}: {e}",
                         self.t("err.launch_fail"))
            return None
        self.bridge = bridge

        # 没配固定端口时，把这次实际用的端口记为固定端口（下次默认用它）。
        # 若下次该端口被占用，上面那段会退回自动端口并再次记下来，不会卡死。
        if not port_text:
            self.cfg.update(port=str(actual_port))
            self.ui.web_log(self.t("msg.port_auto_saved", port=actual_port),
                            self.t("tag.start"))

        self.ui.web_log(self.t("msg.server_started", url=url),
                        self.t("tag.start"))
        self.ui.web_log(self.t("msg.server_dir", dir=root_dir),
                        self.t("tag.start"))
        self.ui.web_log(self.t("msg.server_local"), self.t("tag.start"))
        self.ui.web_log(f"存档桥已就绪: ws://127.0.0.1:{bridge.port}/",
                        self.t("tag.start"))
        if open_browser:
            self.open_game_window(url)
        return url

    def stop(self):
        """停止服务与桥（未运行时静默返回）。"""
        bridge, self.bridge = self.bridge, None
        if bridge is not None:
            try:
                bridge.stop()
            except Exception:
                pass
        try:
            self.lweb.stop()
        except Exception:
            pass
        self._log_action("WEB_STOP", "服务与存档桥已停止")

    def open_game_window(self, url=None):
        """用配置的浏览器打开游戏页（新窗口）。"""
        url = url or self.url
        if not url:
            return False
        how = open_in_browser(url, browser_path=self.cfg.browser,
                              new_window=self.browser_new_window)
        if how:
            self.ui.web_log(self.t("msg.browser_opened", how=how),
                            self.t("tag.browser"))
            return True
        self.ui.web_log(self.t("msg.browser_fail", url=url),
                        self.t("tag.error"))
        return False

    # ---------------- 内部 ----------------
    def _log_error(self, msg):
        if self.logger is not None:
            self.logger.error(msg)

    def _log_warn(self, msg):
        if self.logger is not None:
            self.logger.warn(msg)

    def _log_action(self, action, detail):
        if self.logger is not None:
            self.logger.action(action, detail)
