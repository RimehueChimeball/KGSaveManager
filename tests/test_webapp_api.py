"""webapp 集成测试：真起 HTTP 服务，用标准库客户端跑一遍 API 与页面。

覆盖：静态页面、/api/state、/api/call 各类动作、事件增量拉取、
对话框（confirm/ask_text）经 /api/answer 应答、/api/shutdown。
不访问外网（下载相关接口全部打桩）。
"""

import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import downloader  # noqa: E402
import web_server  # noqa: E402
from webapp.api import EventPump, WebApi, WebUiPort  # noqa: E402
from webapp.server import AppServer, EventBuffer  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


class _FakeBridge:
    """替身存档桥：记录取档/下发调用，返回预设结果。"""

    def __init__(self, save_text=None, apply_ok=True, has_client=True):
        self.save_text = save_text
        self.apply_ok = apply_ok
        self.has_client = has_client
        self.requested = []
        self.applied = []

    def request_save(self, timeout=15):
        self.requested.append(timeout)
        return self.save_text

    def apply_save(self, blob, timeout=8.0):
        self.applied.append(blob)
        return self.apply_ok


class WebHarness:
    def __init__(self, tmp):
        from core.app import AppCore
        self.outbox = EventBuffer()
        self.ui = WebUiPort(self.outbox)
        self.core = AppCore(self.ui, base_dir=tmp)
        self.state = {"shutdown": False}
        self.api = WebApi(self.core, self.ui,
                          on_shutdown=lambda: self.state.update(shutdown=True))
        self.pump = EventPump(self.core, self.outbox)
        self.server = AppServer(self.api, self.ui, self.outbox,
                                REPO / "webapp" / "assets",
                                on_shutdown=lambda: self.state.update(
                                    shutdown=True))
        self.url = self.server.start()
        self.pump.start()

    def close(self):
        self.pump.stop()
        self.server.stop()
        try:
            self.core.logger.close()
        except Exception:
            pass

    # ---------- HTTP 客户端 ----------
    def get(self, path):
        with urllib.request.urlopen(self.url.rstrip("/") + path,
                                    timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")

    def get_json(self, path):
        status, body = self.get(path)
        return status, json.loads(body)

    def post_json(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url.rstrip("/") + path, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, json.loads(
                    resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))

    def call(self, method, **params):
        status, body = self.post_json("/api/call",
                                      {"method": method, "params": params})
        if status != 200 or not body.get("ok"):
            return None
        return body["result"]

    def events(self, since=0):
        _status, body = self.get_json(f"/api/events?since={since}")
        return body["events"], body["next"]

    def wait_event(self, kind, timeout=10.0, since=0):
        """等待某类事件出现，返回 (事件, 新的 since)。"""
        deadline = time.time() + timeout
        cursor = since
        seen = []
        while time.time() < deadline:
            events, cursor = self.events(cursor)
            for ev in events:
                seen.append(ev)
                if ev.get("type") == kind:
                    return ev, cursor
            time.sleep(0.1)
        raise AssertionError(f"未等到事件 {kind}；已收到: {seen}")


class TestWebApp(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.h = WebHarness(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.h.close)

    # ---------------- 静态与状态 ----------------
    def test_index_page_served(self):
        status, body = self.h.get("/")
        self.assertEqual(status, 200)
        self.assertIn("KGSaveManager", body)
        self.assertIn("/assets/app.js", body)
        self.assertIn("/assets/style.css", body)

    def test_assets_served(self):
        for name, marker in (("app.js", "pollEvents"), ("style.css", "--accent")):
            status, body = self.h.get("/assets/" + name)
            self.assertEqual(status, 200, name)
            self.assertIn(marker, body)

    def test_asset_traversal_is_blocked(self):
        try:
            status, _body = self.h.get("/assets/../KGSaveManager.py")
        except urllib.error.HTTPError as e:
            status = e.code
        self.assertIn(status, (403, 404))

    def test_icon_and_manifest_served(self):
        """应用窗口的图标与清单：浏览器会来取这几个资源。"""
        with urllib.request.urlopen(self.h.url.rstrip("/") +
                                    "/assets/favicon.ico", timeout=10) as r:
            self.assertEqual(r.headers.get("Content-Type"), "image/x-icon")
            body = r.read()
        self.assertTrue(body.startswith(b"\x00\x00\x01\x00"), "不是合法 ICO")
        with urllib.request.urlopen(self.h.url.rstrip("/") +
                                    "/assets/icon-192.png", timeout=10) as r:
            self.assertEqual(r.headers.get("Content-Type"), "image/png")
            png = r.read()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"), "不是合法 PNG")
        with urllib.request.urlopen(
                self.h.url.rstrip("/") + "/assets/manifest.webmanifest",
                timeout=10) as r:
            self.assertIn("application/manifest+json",
                          r.headers.get("Content-Type"))
            manifest = json.loads(r.read().decode("utf-8"))
        self.assertEqual(manifest["short_name"], "KGSaveManager")
        self.assertTrue(manifest["icons"])

    def test_page_declares_title_and_icons(self):
        """标题与图标都由页面决定：检查声明齐全（应用窗口据此显示）。"""
        _status, html = self.h.get("/")
        for marker in ('<link rel="icon" href="/assets/favicon.ico"',
                       'type="image/png" href="/assets/icon-192.png"',
                       '<link rel="manifest" href="/assets/manifest.webmanifest"',
                       '<meta name="application-name"',
                       "<title>"):
            self.assertIn(marker, html, f"页面缺少 {marker}")

    def test_state_contains_strings_and_slots(self):
        status, body = self.h.get_json("/api/state")
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertTrue(result["strings"])
        self.assertIn("tab.saves", result["strings"])
        self.assertEqual(len(result["slots"]), 10)
        self.assertEqual([r["key"] for r in result["repos"]],
                         ["author", "community"])
        self.assertTrue(result["mirrors"])

    def test_unknown_method_is_rejected(self):
        status, body = self.h.post_json("/api/call",
                                        {"method": "nope", "params": {}})
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])

    def test_default_slot_setting_is_gone(self):
        """「默认存档位」是为已删除的首页功能做的设置入口，两版都已移除。

        它原来只服务于 Tk 版首页的一个功能，功能删掉之后在 HTML 版连消费者
        都没有（`default_slot` 字段前端根本不读），所以连同配置与 i18n 一起删。
        """
        state = self.h.api.state()
        config = state["config"]
        self.assertNotIn("home_slot", config)
        self.assertNotIn("default_slot", state)
        self.assertNotIn("st.home_slot", state["strings"])
        index = (REPO / "webapp" / "assets" / "index.html").read_text(
            encoding="utf-8")
        self.assertNotIn("set-home-slot", index)

    def test_private_method_is_rejected(self):
        status, body = self.h.post_json("/api/call",
                                        {"method": "_close_manual",
                                         "params": {}})
        self.assertEqual(status, 400)

    # ---------------- 手动导入（页面文件选择器走同一个接口） ----------------
    def test_manual_import_text_writes_slot(self):
        import savecodec
        blob = savecodec.compress_base64('{"a":5}')
        out = self.h.call("manual_import_text", slot=4, text=blob)
        self.assertTrue(out["ok"])
        self.assertIn("存档5_5.kgsav",
                      [p.name for p in self.h.core.paths.saves.iterdir()])
        # 写入后 core 会发 slots_changed，页面据此刷新列表
        ev, _ = self.h.wait_event("slots_changed")
        self.assertEqual(ev["type"], "slots_changed")

    def test_manual_import_text_rejects_empty(self):
        out = self.h.call("manual_import_text", slot=0, text="   ")
        self.assertFalse(out["ok"])
        self.assertEqual(list(self.h.core.paths.saves.iterdir()), [])

    def test_manual_copy_library_pushes_clipboard(self):
        self.assertTrue(self.h.call("manual_copy_library"))
        ev, _ = self.h.wait_event("clipboard")
        self.assertEqual(ev["text"], str(self.h.core.paths.saves.resolve()))

    def test_state_exposes_save_library_path(self):
        """页面要用存档库路径拼“手动改名”的说明文字。"""
        out = self.h.call("refresh")
        self.assertEqual(out["paths"]["saves"],
                         str(self.h.core.paths.saves))

    # ---------------- 存档动作 ----------------
    def test_save_note_and_refresh(self):
        self.assertTrue(self.h.call("save_note", index=3, text="钢铁"))
        result = self.h.call("refresh")
        self.assertEqual(result["slots"][3]["note"], "钢铁")

    def test_rename_slot_roundtrip(self):
        self.h.core.slots.write(1, '{"a":1}', 1024 * 1024)
        out = self.h.call("rename_slot", slot=1, name="新名")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["name"], "新名_2.kgsav")

    def test_copy_save_pushes_clipboard_event(self):
        self.h.core.slots.write(0, '{"a":1}', 1024 * 1024)
        self.assertTrue(self.h.call("copy_save", slot=0))
        ev, _ = self.h.wait_event("clipboard")
        self.assertEqual(ev["text"], '{"a":1}')

    def test_check_library_logs(self):
        self.assertTrue(self.h.call("check_library"))
        ev, _ = self.h.wait_event("log")
        self.assertEqual(ev["channel"], "saves")

    # ---------------- 对话框往返 ----------------
    def test_confirm_dialog_roundtrip(self):
        """下载前若目标目录非空会先确认：确认框经 /api/answer 应答后流程继续。"""
        target = Path(self.tmp.name) / "busy_target"
        target.mkdir()
        (target / "index.html").write_text("x", encoding="utf-8")
        result = {}

        def worker():
            result["value"] = self.h.call(
                "download_start", repo="author", mirror="github.com",
                ref="refs/heads/master", target=str(target),
                set_dir=False, keep_temp=True)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        ev, _cursor = self.h.wait_event("dialog")
        self.assertEqual(ev["dialog"], "confirm")
        status, body = self.h.post_json("/api/answer",
                                        {"id": ev["id"], "ok": False})
        self.assertTrue(body["ok"])
        t.join(timeout=5)
        self.assertFalse(result.get("value"), "取消后不应开始下载")

    def test_ask_text_dialog_roundtrip(self):
        """ask_directory 走文本对话框，回答后应把路径交给 core。"""
        result = {}

        def worker():
            result["value"] = self.h.ui.ask_directory("pick", "C:/x")

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        ev, _cursor = self.h.wait_event("dialog")
        self.assertEqual(ev["dialog"], "text")
        self.assertEqual(ev["title"], "pick")
        self.h.post_json("/api/answer",
                         {"id": ev["id"], "ok": True, "text": "D:/chosen"})
        t.join(timeout=5)
        self.assertEqual(result.get("value"), "D:/chosen")

    def test_dialog_timeout_defaults_to_cancel(self):
        """无人作答时 confirm 应超时返回 False（这里直接把超时调小验证）。"""
        import webapp.api as api_mod
        old = api_mod.DIALOG_TIMEOUT
        api_mod.DIALOG_TIMEOUT = 0.2
        try:
            self.assertFalse(self.h.ui.confirm("no answer"))
        finally:
            api_mod.DIALOG_TIMEOUT = old

    # ---------------- 编辑器 ----------------
    def test_editor_flow(self):
        import savecodec
        blob = savecodec.compress_base64('{"a":{"b":1}}')
        self.h.core.slots.write(2, blob, 1024 * 1024)
        opened = self.h.call("editor_open_file", slot=2)
        self.assertTrue(opened["ok"])
        tree = self.h.call("editor_tree")
        self.assertTrue(tree["rows"])
        leaf = [r for r in tree["rows"] if r["kind"] == "leaf"][0]
        changed = self.h.call("editor_set_value", path=leaf["path"], raw="7")
        self.assertTrue(changed["ok"])
        written = self.h.call("editor_write", source_text=None)
        self.assertTrue(written["ok"])
        from core.editor import decode_to_obj
        saved = decode_to_obj(
            self.h.core.slots.path(2).read_text(encoding="utf-8"))
        self.assertEqual(saved["a"]["b"], 7)

    # ---------------- 编辑器：实时模式走事件 ----------------
    def _live_editor(self, blob=None, apply_ok=True, has_client=True):
        """把编辑器的桥换成替身，模拟「游戏页面已连接」。"""
        fake = _FakeBridge(blob, apply_ok=apply_ok, has_client=has_client)
        self.h.core.editor._get_bridge = lambda: fake
        self.h.core.editor._is_server_running = lambda: True
        return fake

    def test_editor_live_pull_pushes_event(self):
        """实时取档在后台进行：接口先回 pending，取到后推 editor_live 事件。"""
        import savecodec
        blob = savecodec.compress_base64('{"a":1}')
        fake = self._live_editor(blob)
        res = self.h.call("editor_open_live")
        self.assertTrue(res["ok"])
        self.assertTrue(res["pending"], "接口应立即返回「进行中」")
        ev, _ = self.h.wait_event("editor_live")
        self.assertTrue(ev["ok"])
        self.assertEqual(len(fake.requested), 1)
        tree = self.h.call("editor_tree")
        self.assertTrue([r for r in tree["rows"] if r["kind"] == "leaf"],
                        "取到的存档应已进入编辑器")

    def test_editor_live_pull_failure_pushes_event(self):
        fake = self._live_editor(None)
        res = self.h.call("editor_open_live")
        self.assertTrue(res["pending"])
        ev, _ = self.h.wait_event("editor_live")
        self.assertFalse(ev["ok"])
        self.assertTrue(fake.requested)

    def test_editor_live_write_waits_for_confirmation(self):
        """实时下发等页面确认：没确认时事件里是 None，不是谎报成功。"""
        import savecodec
        blob = savecodec.compress_base64('{"a":1}')
        fake = self._live_editor(blob, apply_ok=None)
        self.h.call("editor_open_live")
        self.h.wait_event("editor_live")
        res = self.h.call("editor_write", source_text=None)
        self.assertTrue(res["pending"], "下发应回「进行中」")
        ev, _ = self.h.wait_event("editor_sent")
        self.assertIsNone(ev["result"])
        self.assertEqual(len(fake.applied), 1)

    def test_editor_live_write_confirmed_pushes_event(self):
        import savecodec
        blob = savecodec.compress_base64('{"a":1}')
        fake = self._live_editor(blob, apply_ok=True)
        self.h.call("editor_open_live")
        self.h.wait_event("editor_live")
        res = self.h.call("editor_write", source_text=None)
        self.assertTrue(res["pending"])
        ev, _ = self.h.wait_event("editor_sent")
        self.assertIs(ev["result"], True)

    # ---------------- 下载（打桩） ----------------
    def test_download_versions_event(self):
        orig = downloader.list_versions
        downloader.list_versions = lambda owner, repo, **kw: [
            ("branch", "master", "refs/heads/master")]
        try:
            self.assertTrue(self.h.call("download_versions", repo="author"))
            ev, _ = self.h.wait_event("download_versions")
            self.assertEqual(ev["repo"], "author")
            self.assertEqual(ev["items"][0][1], "master")
        finally:
            downloader.list_versions = orig

    def test_download_start_and_done_event(self):
        orig = downloader.install_game

        def fake_install(repo, mirror, ref, target, progress=None,
                         cancel=None, delete_temp=True):
            if progress:
                progress(50, 100)
            (Path(target) / "index.html").write_text("x", encoding="utf-8")
            return target

        downloader.install_game = fake_install
        try:
            target = str(Path(self.tmp.name) / "game")
            self.assertTrue(self.h.call("download_start", repo="author",
                                        mirror="github.com",
                                        ref="refs/heads/master",
                                        target=target, set_dir=False,
                                        keep_temp=True))
            ev, _ = self.h.wait_event("download_done", timeout=15)
            self.assertEqual(ev["target"], target)
        finally:
            downloader.install_game = orig

    # ---------------- 生命周期 ----------------
    def test_shutdown_sets_flag(self):
        self.assertTrue(self.h.call("shutdown"))
        self.assertTrue(self.h.state["shutdown"])

    def test_no_heartbeat_endpoint(self):
        """没有页面心跳，也没有"页面多久没响应就退出"的看门狗。

        浏览器会把隐藏页面的定时器降频到约每分钟一次，心跳无法区分
        「用户离开了」与「窗口被最小化了」，因此这套机制已移除。
        """
        self.assertFalse(hasattr(self.h.api, "ping"))
        self.assertFalse(hasattr(self.h.api, "last_seen"))
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.h.get_json("/api/ping")
        self.assertEqual(ctx.exception.code, 404)


class TestAppWindow(unittest.TestCase):
    """HTML 版是用浏览器应用窗口打开的：这里只验证命令行构造，不真的启动浏览器。"""

    def test_app_window_args(self):
        args = web_server.app_window_args("C:/x/msedge.exe",
                                          "http://127.0.0.1:1234/",
                                          1200, 800)
        self.assertEqual(args[0], "C:/x/msedge.exe")
        # 页面用 fit=auto 自己把窗口调成横向尺寸（命令行尺寸只在干净配置下生效）
        self.assertIn("--app=http://127.0.0.1:1234/?fit=auto", args)
        self.assertIn("--window-size=1200,800", args)

    def test_app_window_args_append_fit_flag(self):
        args = web_server.app_window_args("C:/x/msedge.exe",
                                          "http://127.0.0.1:1234/?page=saves")
        self.assertIn("--app=http://127.0.0.1:1234/?page=saves&fit=auto", args)
        self.assertIn("--window-size=1320,840", args, "默认尺寸应为横向")

    def test_window_state_args(self):
        """最大化/全屏：窗口尺寸交给页面，全屏额外传 --start-fullscreen。"""
        exe = "C:/x/msedge.exe"
        url = "http://127.0.0.1:1234/"
        maxed = web_server.app_window_args(exe, url, fit="max")
        self.assertIn(f"--app={url}?fit=max", maxed)
        self.assertNotIn("--window-size=1320,840", maxed,
                         "最大化时由页面自己铺满工作区")
        self.assertNotIn("--start-fullscreen", maxed)
        full = web_server.app_window_args(exe, url, fit="full",
                                          fullscreen=True)
        self.assertIn(f"--app={url}?fit=full", full)
        self.assertIn("--start-fullscreen", full)

    def test_open_app_window_uses_app_mode(self):
        calls = []
        orig_popen = web_server.subprocess.Popen
        web_server.subprocess.Popen = lambda args: calls.append(args)
        try:
            with TemporaryDirectory() as tmp:
                exe = Path(tmp) / "msedge.exe"
                exe.write_bytes(b"")          # 只要存在即可，不会真的执行
                how = web_server.open_app_window("http://127.0.0.1:9/",
                                                 str(exe))
        finally:
            web_server.subprocess.Popen = orig_popen
        self.assertEqual(how, "app")
        self.assertEqual(len(calls), 1)
        self.assertIn("--app=http://127.0.0.1:9/?fit=auto", calls[0])

    def test_ui_window_ignores_game_window_settings(self):
        """窗口设置只作用于游戏窗口：界面窗口固定用应用窗口 + 页面侧横向尺寸。

        这条是需求本身（用户明确说过只作用于游戏窗口），所以直接在源码层面挡住
        回归：界面入口不许读 launch_mode/window_state。
        """
        entry = (REPO / "KGSaveManager.py").read_text(encoding="utf-8")
        self.assertIn("open_app_window(url", entry)
        self.assertNotIn("_window_plan", entry)
        self.assertNotIn("window_state", entry)
        self.assertNotIn("launch_mode", entry)

    def test_open_app_window_falls_back_without_browser(self):
        """配置的浏览器无效且系统默认浏览器也探测不到时，退回普通打开。"""
        import config_store
        calls = []
        orig_open = web_server.open_in_browser
        orig_detect = config_store.detect_browser_path
        web_server.open_in_browser = (
            lambda url, browser_path="", new_window=True:
            calls.append((url, new_window)) or "system default")
        config_store.detect_browser_path = lambda: ""
        try:
            how = web_server.open_app_window("http://127.0.0.1:9/",
                                             "D:/not/a/browser.txt")
        finally:
            web_server.open_in_browser = orig_open
            config_store.detect_browser_path = orig_detect
        self.assertEqual(how, "system default")
        self.assertEqual(calls, [("http://127.0.0.1:9/", True)])


class TestFrontendAssets(unittest.TestCase):
    """静态检查：页面引用的键、以及 JS 语法。"""

    def test_html_keys_exist_in_tables(self):
        import i18n
        html = (REPO / "webapp" / "assets" / "index.html").read_text(
            encoding="utf-8")
        import re
        keys = set(re.findall(r'data-i18n="([^"]+)"', html))
        self.assertTrue(keys)
        missing = sorted(k for k in keys if k not in i18n._ZH)
        self.assertEqual(missing, [], f"页面引用了不存在的翻译键: {missing}")

    def test_html_keys_have_both_languages(self):
        import i18n
        html = (REPO / "webapp" / "assets" / "index.html").read_text(
            encoding="utf-8")
        import re
        keys = set(re.findall(r'data-i18n="([^"]+)"', html))
        missing_en = sorted(k for k in keys if k not in i18n._EN)
        self.assertEqual(missing_en, [])

    def test_js_syntax_with_node(self):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("未找到 node")
        app_js = REPO / "webapp" / "assets" / "app.js"
        proc = subprocess.run([node, "--check", str(app_js)],
                              capture_output=True, encoding="utf-8",
                              errors="replace", timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_js_only_calls_known_api_methods(self):
        """页面调用的方法都必须存在于 WebApi 上。"""
        import re
        from webapp.api import WebApi
        js = (REPO / "webapp" / "assets" / "app.js").read_text(
            encoding="utf-8")
        called = set(re.findall(r'call\(\s*"([a-z_]+)"', js))
        available = {name for name in dir(WebApi)
                     if not name.startswith("_") and callable(
                         getattr(WebApi, name))}
        missing = sorted(called - available)
        self.assertEqual(missing, [], f"页面调用了不存在的 API: {missing}")


if __name__ == "__main__":
    unittest.main()
