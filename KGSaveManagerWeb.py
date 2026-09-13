"""KGSaveManager（HTML 版）入口。

与 Tkinter 版共用 `core/` 的全部逻辑，只有界面不同：
- 后端是纯标准库的本地 HTTP 服务（`webapp/`）；
- 界面是 `webapp/assets/` 里的 HTML/CSS/JS，由系统浏览器（Edge/Chrome）
  以应用窗口方式打开（`--app=`，无地址栏与标签页）。

用法：
    python KGSaveManagerWeb.py [--port N] [--no-browser] [--serve] [--verbose]

- `--port N`     固定页面服务端口（默认自动分配）
- `--no-browser` 不自动打开窗口（只打印地址）
- `--serve`      不随页面关闭而退出（常驻服务）
- `--verbose`    打印访问日志
"""

import argparse
import sys
import time

from utils import setup_dpi_and_scaling
from web_server import open_app_window
from webapp.api import EventPump, WebApi, WebUiPort
from webapp.server import AppServer, EventBuffer

from core.app import APP_NAME, APP_VERSION, AppCore

# 页面停止心跳多久后退出（秒）；页面每 2 秒心跳一次
IDLE_EXIT_SECONDS = 12.0


def build_app(base_dir=None, port=0, verbose=False):
    """组装后端（供入口与测试共用）。"""
    outbox = EventBuffer()
    ui = WebUiPort(outbox)
    core = AppCore(ui, base_dir=base_dir)
    state = {"shutdown": False}

    def request_shutdown():
        state["shutdown"] = True

    api = WebApi(core, ui, on_shutdown=request_shutdown)
    pump = EventPump(core, outbox)
    server = AppServer(api, ui, outbox, core.paths.assets, port=port,
                       on_shutdown=request_shutdown)
    return {"core": core, "ui": ui, "api": api, "pump": pump,
            "server": server, "outbox": outbox, "state": state}


def main(argv=None):
    parser = argparse.ArgumentParser(description=f"{APP_NAME} (HTML UI)")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    setup_dpi_and_scaling()
    app = build_app(port=args.port, verbose=args.verbose)
    core = app["core"]
    server = app["server"]
    url = server.start()
    app["pump"].start()
    core.logger.action("WEB_UI", f"HTML 版启动: {url}")
    print(f"{APP_NAME} {APP_VERSION} (HTML UI)")
    print(f"  页面地址: {url}")
    print(f"  数据目录: {core.paths.data}")
    print("  关闭窗口或按 Ctrl+C 退出")

    if not args.no_browser:
        how = open_app_window(url, browser_path=core.cfg.browser)
        print(f"  打开方式: {how or '(失败，请手动打开上面的地址)'}")

    try:
        while not app["state"]["shutdown"]:
            time.sleep(0.3)
            if args.serve:
                continue
            api = app["api"]
            if (api.ever_seen
                    and time.time() - api.last_seen() > IDLE_EXIT_SECONDS):
                print("页面已关闭，退出。")
                break
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，退出。")
    finally:
        app["pump"].stop()
        server.stop()
        core.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
