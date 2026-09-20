"""KGSaveManager（主版本：HTML 界面）入口。

界面是 `webapp/assets/` 里的 HTML/CSS/JS，由纯标准库的本地 HTTP 服务
（`webapp/`）发给系统浏览器，并以应用窗口方式打开（Edge/Chrome 的
`--app=`，无地址栏与标签页；界面窗口本身不受配置页的窗口设置影响）。逻辑与
旁边的 Tk 版（`KGSaveManagerTk.py`）完全共用 `core/`。

用法：
    python KGSaveManager.py [--port N] [--no-browser] [--verbose]

- `--port N`     固定页面服务端口（默认自动分配）
- `--no-browser` 不自动打开窗口（只打印地址）
- `--verbose`    打印访问日志

退出方式只有两种：页面里的「退出」按钮，或 Ctrl+C / 关闭控制台窗口。
程序**不会**因为页面停止响应而自行退出：浏览器会把最小化/被遮住页面的定时器
降频到约每分钟一次，"页面多久没心跳"无法区分"用户离开了"和"窗口被最小化了"。
"""

import argparse
import sys
import threading

from utils import setup_dpi_and_scaling
from web_server import open_app_window
from webapp.api import EventPump, WebApi, WebUiPort
from webapp.server import AppServer, EventBuffer

from core.app import APP_NAME, APP_VERSION, AppCore


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
                       on_shutdown=request_shutdown, verbose=verbose)
    return {"core": core, "ui": ui, "api": api, "pump": pump,
            "server": server, "outbox": outbox, "state": state}


def main(argv=None):
    parser = argparse.ArgumentParser(description=f"{APP_NAME} (main version)")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    setup_dpi_and_scaling()
    app = build_app(port=args.port, verbose=args.verbose)
    core = app["core"]
    server = app["server"]
    url = server.start()
    app["pump"].start()
    core.logger.action("WEB_UI", f"主版本（HTML 界面）启动: {url}")
    print(f"{APP_NAME} {APP_VERSION}")
    print(f"  页面地址: {url}")
    print(f"  数据目录: {core.paths.data}")
    print("  退出：页面里的「退出」按钮，或按 Ctrl+C")

    # 界面窗口固定用应用窗口（无地址栏/标签页），页面自己调成横向尺寸。
    # 配置页的「游戏窗口位置/状态」只作用于游戏窗口，不影响这里。
    if not args.no_browser:
        how = open_app_window(url, browser_path=core.cfg.browser)
        print(f"  打开方式: {how or '(失败，请手动打开上面的地址)'}")

    # 只等两种退出信号：页面的「退出」按钮（state["shutdown"]）与 Ctrl+C。
    # 不做"页面多久没心跳就退出"的看门狗——浏览器会降低隐藏页面的定时器频率，
    # 无法区分"用户离开了"和"窗口被最小化了"。
    stop = threading.Event()
    try:
        while not app["state"]["shutdown"] and not stop.wait(0.3):
            pass
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，退出。")
    finally:
        app["pump"].stop()
        server.stop()
        core.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
