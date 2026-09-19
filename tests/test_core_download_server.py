"""core.download / core.server 测试（不访问真实网络，全部打桩）。"""

import queue
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import downloader  # noqa: E402
import web_server  # noqa: E402
import core.server as core_server  # noqa: E402
from core.download import DownloadController  # noqa: E402
from core.server import ServerController  # noqa: E402
from core.ui_port import NullUiPort  # noqa: E402


class FakeConfig:
    def __init__(self):
        self.game_dir = ""
        self.port = ""
        self.browser = ""
        self.updates = []

    def update(self, **kw):
        self.updates.append(kw)
        for k, v in kw.items():
            setattr(self, k, v)


def make_t():
    def t(key, **kw):
        return key + ("|" + ",".join(f"{k}={v}"
                                     for k, v in sorted(kw.items()))
                      if kw else "")
    return t


class FakeLogger:
    """只记录调用，用于断言"运行日志里有没有留痕"。"""

    def __init__(self):
        self.records = []

    def info(self, msg):
        self.records.append(("INFO", msg))

    def warn(self, msg):
        self.records.append(("WARN", msg))

    def error(self, msg):
        self.records.append(("ERROR", msg))

    def action(self, action, detail):
        self.records.append(("ACTION", f"{action} {detail}"))

    def close(self):
        pass


class DownloadHarness:
    def __init__(self, tmp, *, confirm=True):
        self.tmp = Path(tmp)
        self.cfg = FakeConfig()
        self.ui = NullUiPort(confirm_default=confirm)
        self.events = queue.Queue()
        self.dl = DownloadController(ui=self.ui, cfg=self.cfg, t=make_t(),
                                     events=self.events,
                                     base_dir=self.tmp)

    def drain(self, timeout=3.0):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain_until(self, kind, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            item = self.drain(timeout=0.5)
            if item and item[0] == kind:
                return item
        return None


class TestDownloadBasics(unittest.TestCase):
    def test_choices_and_defaults(self):
        with TemporaryDirectory() as tmp:
            h = DownloadHarness(tmp)
            self.assertEqual([k for _l, k in h.dl.repo_choices()],
                             ["author", "community"])
            self.assertEqual(h.dl.mirrors(), list(downloader.MIRRORS))
            self.assertEqual(Path(h.dl.default_target()).name, "KittensGame")

    def test_start_requires_ref(self):
        with TemporaryDirectory() as tmp:
            h = DownloadHarness(tmp)
            self.assertFalse(h.dl.start("author", "github.com", "",
                                        str(h.tmp / "game")))
            self.assertEqual(h.ui.messages[0][0], "warn")

    def test_start_requires_target(self):
        with TemporaryDirectory() as tmp:
            h = DownloadHarness(tmp)
            self.assertFalse(h.dl.start("author", "github.com",
                                        "refs/heads/master", "   "))
            self.assertEqual(h.ui.messages[0][0], "fail")

    def test_existing_content_needs_confirmation(self):
        with TemporaryDirectory() as tmp:
            h = DownloadHarness(tmp, confirm=False)
            target = h.tmp / "game"
            target.mkdir()
            (target / "index.html").write_text("x", encoding="utf-8")
            self.assertFalse(h.dl.start("author", "github.com",
                                        "refs/heads/master", str(target)))
            self.assertEqual(h.ui.messages[0][0], "confirm")
            self.assertFalse(h.dl.busy)


class TestDownloadRun(unittest.TestCase):
    def setUp(self):
        self.orig_install = downloader.install_game

    def tearDown(self):
        downloader.install_game = self.orig_install

    def test_success_updates_config_and_emits_events(self):
        def fake_install(repo, mirror, ref, target, progress=None,
                         cancel=None, delete_temp=True):
            if progress:
                progress(0, None, f"url:{mirror}")
                progress(50, 100)
                progress(0, None, "extract")
                progress(100, 100)
            (Path(target) / "index.html").write_text("x", encoding="utf-8")
            return target

        downloader.install_game = fake_install
        with TemporaryDirectory() as tmp:
            h = DownloadHarness(tmp)
            target = str(h.tmp / "game")
            self.assertTrue(h.dl.start("author", "ghfast.top",
                                       "refs/heads/master", target,
                                       set_service_dir=True))
            busy = h.drain_until("dl_busy")
            self.assertEqual(busy, ("dl_busy", True))
            self.assertTrue(h.dl.busy)
            done = h.drain_until("dl_done")
            self.assertIsNotNone(done, "未收到完成事件")
            self.assertEqual(done[1], target)
            self.assertTrue(done[2])
            self.assertEqual(h.cfg.game_dir, target)
            h.dl.sync_event(done)
            self.assertFalse(h.dl.busy, "完成后应解除忙碌状态")

    def test_progress_callback_maps_extract_to_log(self):
        def fake_install(repo, mirror, ref, target, progress=None,
                         cancel=None, delete_temp=True):
            progress(0, None, "extract")
            progress(10, 100)
            return target

        downloader.install_game = fake_install
        with TemporaryDirectory() as tmp:
            h = DownloadHarness(tmp)
            h.dl.start("author", "github.com", "refs/heads/master",
                       str(h.tmp / "game"))
            seen = []
            deadline = time.time() + 5
            while time.time() < deadline:
                item = h.drain(0.5)
                if item:
                    seen.append(item)
                if item and item[0] == "dl_done":
                    break
            kinds = [i[0] for i in seen]
            self.assertIn("dl_log", kinds)       # 解压阶段
            self.assertIn("dl_progress", kinds)  # 下载百分比
            self.assertIn("dl_done", kinds)

    def test_cancel_emits_canceled(self):
        def fake_install(repo, mirror, ref, target, progress=None,
                         cancel=None, delete_temp=True):
            raise downloader.DownloadCancelled()

        downloader.install_game = fake_install
        with TemporaryDirectory() as tmp:
            h = DownloadHarness(tmp)
            h.dl.start("author", "github.com", "refs/heads/master",
                       str(h.tmp / "game"))
            item = h.drain_until("dl_canceled")
            self.assertIsNotNone(item)
            h.dl.sync_event(item)
            self.assertFalse(h.dl.busy)

    def test_failure_emits_fail_with_message(self):
        def fake_install(repo, mirror, ref, target, progress=None,
                         cancel=None, delete_temp=True):
            raise downloader.DownloadError("boom")

        downloader.install_game = fake_install
        with TemporaryDirectory() as tmp:
            h = DownloadHarness(tmp)
            h.dl.start("author", "github.com", "refs/heads/master",
                       str(h.tmp / "game"))
            item = h.drain_until("dl_fail")
            self.assertIsNotNone(item)
            self.assertIn("boom", item[1])
            h.dl.sync_event(item)
            self.assertFalse(h.dl.busy)


class TestVersionsAndTest(unittest.TestCase):
    def test_refresh_versions_emits_items(self):
        orig = downloader.list_versions
        downloader.list_versions = lambda owner, repo, **kw: [
            ("branch", "master", "refs/heads/master")]
        try:
            with TemporaryDirectory() as tmp:
                h = DownloadHarness(tmp)
                h.dl.refresh_versions("author")
                item = h.drain_until("dl_versions")
                self.assertIsNotNone(item)
                self.assertEqual(item[1], "author")
                self.assertEqual(item[2][0][1], "master")
        finally:
            downloader.list_versions = orig

    def test_refresh_versions_logs_notes(self):
        """诊断提示（限流/缓存）要先写进下载日志。"""
        orig = downloader.list_versions

        def with_note(owner, repo, notes=None, refresh=False):
            if notes is not None:
                notes.append("GitHub API 不可用（可能触发限流），已实测默认分支：master")
            return [("branch", "master", "refs/heads/master")]

        downloader.list_versions = with_note
        try:
            with TemporaryDirectory() as tmp:
                h = DownloadHarness(tmp)
                h.dl.refresh_versions("author", refresh=True)
                item = h.drain_until("dl_log")
                self.assertIsNotNone(item, "未收到诊断日志事件")
                self.assertIn("限流", item[1])
                self.assertIsNotNone(h.drain_until("dl_versions"))
        finally:
            downloader.list_versions = orig

    def test_refresh_versions_failure_emits_fail(self):
        orig = downloader.list_versions

        def boom(owner, repo, **kw):
            raise OSError("offline")

        downloader.list_versions = boom
        try:
            with TemporaryDirectory() as tmp:
                h = DownloadHarness(tmp)
                h.dl.refresh_versions("author", silent=True)
                item = h.drain_until("dl_fail")
                self.assertIsNotNone(item)
                self.assertTrue(item[2])          # silent=True
        finally:
            downloader.list_versions = orig

    def test_connectivity_test_lines(self):
        orig = downloader.test_sources
        downloader.test_sources = lambda repo, ref, timeout=6: {
            name: (True, "0.4s") for name in downloader.MIRRORS}
        try:
            with TemporaryDirectory() as tmp:
                h = DownloadHarness(tmp)
                self.assertTrue(h.dl.test_connectivity(
                    "author", "refs/heads/master"))
                self.assertEqual(h.drain_until("dl_test_start"),
                                 ("dl_test_start",))
                item = h.drain_until("dl_test_result")
                self.assertIsNotNone(item)
                self.assertTrue(all("OK" in line for line in item[1]))
        finally:
            downloader.test_sources = orig

    def test_connectivity_requires_ref(self):
        with TemporaryDirectory() as tmp:
            h = DownloadHarness(tmp)
            self.assertFalse(h.dl.test_connectivity("author", None))
            self.assertEqual(h.ui.messages[0][0], "warn")


class TestServerController(unittest.TestCase):
    def setUp(self):
        self.orig_open = web_server.open_in_browser

    def tearDown(self):
        web_server.open_in_browser = self.orig_open

    def _controller(self, tmp, game_dir="", logger=None):
        cfg = FakeConfig()
        cfg.game_dir = game_dir
        ui = NullUiPort(confirm_default=True)
        events = queue.Queue()
        ctl = ServerController(ui=ui, cfg=cfg, t=make_t(), events=events,
                               logger=logger)
        return ctl, cfg, ui

    def test_start_without_directory(self):
        with TemporaryDirectory() as tmp:
            ctl, _cfg, ui = self._controller(tmp)
            self.assertIsNone(ctl.start())
            self.assertEqual(ui.messages[0][0], "fail")
            self.assertFalse(ctl.running)

    def test_start_with_missing_directory(self):
        with TemporaryDirectory() as tmp:
            ctl, _cfg, ui = self._controller(tmp, str(Path(tmp) / "nope"))
            self.assertIsNone(ctl.start())
            self.assertIn("err.dir_missing", ui.messages[0][2])

    def test_start_with_bad_port(self):
        with TemporaryDirectory() as tmp:
            game = Path(tmp) / "game"
            game.mkdir()
            ctl, cfg, ui = self._controller(tmp, str(game))
            cfg.port = "70000"
            self.assertIsNone(ctl.start())
            self.assertIn("err.port_invalid", ui.messages[0][2])

    def test_start_stop_and_status(self):
        with TemporaryDirectory() as tmp:
            game = Path(tmp) / "game"
            game.mkdir()
            (game / "index.html").write_text("<html></html>",
                                             encoding="utf-8")
            ctl, cfg, ui = self._controller(tmp, str(game))
            url = ctl.start()
            self.assertIsNotNone(url)
            self.assertTrue(ctl.running)
            self.assertIsNotNone(ctl.bridge)
            status = ctl.status()
            self.assertTrue(status["running"])
            self.assertEqual(status["url"], url)
            self.assertIsNotNone(status["bridge_port"])
            # 没配固定端口时，本次自动分配的端口会被记为固定端口
            http_port = url.rsplit(":", 1)[1].strip("/")
            self.assertEqual(cfg.port, http_port, "自动端口应记为固定端口")
            self.assertTrue(cfg.updates)
            self.assertTrue(any("msg.port_auto_saved" in m
                                for _tag, m in ui.logs),
                            "应提示端口已记为固定端口")
            ctl.stop()
            self.assertFalse(ctl.running)
            self.assertIsNone(ctl.bridge)
            self.assertFalse(ctl.status()["running"])

    def test_busy_fixed_port_falls_back_to_auto(self):
        """配置的固定端口被占用时改用自动端口，并把新端口记进配置。"""
        import socket as _socket
        with TemporaryDirectory() as tmp:
            game = Path(tmp) / "game"
            game.mkdir()
            (game / "index.html").write_text("<html></html>",
                                             encoding="utf-8")
            blocker = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            busy_port = blocker.getsockname()[1]
            self.addCleanup(blocker.close)
            logger = FakeLogger()
            try:
                ctl, cfg, ui = self._controller(tmp, str(game), logger)
                cfg.port = str(busy_port)
                url = ctl.start()
                self.assertIsNotNone(url, "占用端口应退回自动端口而不是失败")
                used = int(url.rsplit(":", 1)[1].strip("/"))
                self.assertNotEqual(used, busy_port)
                self.assertEqual(cfg.port, str(used))
                self.assertTrue(any("msg.port_busy_fallback" in m
                                    for _tag, m in ui.logs),
                                "应提示固定端口被占用")
                self.assertTrue(any(r[0] == "WARN"
                                    for r in logger.records),
                                f"运行日志应留下告警: {logger.records}")
                ctl.stop()
            finally:
                blocker.close()

    def test_open_game_window_uses_browser(self):
        calls = []
        orig = core_server.open_in_browser
        core_server.open_in_browser = (
            lambda url, browser_path="", new_window=True:
            calls.append((url, new_window)) or "custom")
        try:
            with TemporaryDirectory() as tmp:
                game = Path(tmp) / "game"
                game.mkdir()
                ctl, _cfg, _ui = self._controller(tmp, str(game))
                ctl.start()
                self.assertTrue(ctl.open_game_window())
                self.assertEqual(calls[-1][1], True)
                ctl.stop()
        finally:
            core_server.open_in_browser = orig

    def test_open_game_window_without_url(self):
        with TemporaryDirectory() as tmp:
            ctl, _cfg, _ui = self._controller(tmp)
            self.assertFalse(ctl.open_game_window())


if __name__ == "__main__":
    unittest.main()
