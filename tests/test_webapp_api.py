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
from webapp.api import EventPump, WebApi, WebUiPort  # noqa: E402
from webapp.server import AppServer, EventBuffer  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


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

    def test_private_method_is_rejected(self):
        status, body = self.h.post_json("/api/call",
                                        {"method": "_close_manual",
                                         "params": {}})
        self.assertEqual(status, 400)

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

    # ---------------- 下载（打桩） ----------------
    def test_download_versions_event(self):
        orig = downloader.list_versions
        downloader.list_versions = lambda owner, repo: [
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

    def test_ping_marks_page_seen(self):
        status, _body = self.h.get_json("/api/ping")
        self.assertEqual(status, 200)
        self.assertTrue(self.h.api.ever_seen)


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
