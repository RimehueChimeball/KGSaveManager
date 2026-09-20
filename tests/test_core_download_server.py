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
        self.launch_mode = "app"
        self.auto_resume = True
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

    def _controller(self, tmp, game_dir="", logger=None, paths=None):
        cfg = FakeConfig()
        cfg.game_dir = game_dir
        ui = NullUiPort(confirm_default=True)
        events = queue.Queue()
        ctl = ServerController(ui=ui, cfg=cfg, t=make_t(), events=events,
                               logger=logger, paths=paths)
        return ctl, cfg, ui

    # ---------------- 自动续玩 ----------------
    def test_session_snapshot_is_stored_and_restored(self):
        """关闭游戏时存进度；下次打开（页面连上）时自动灌回去，且只灌一次。"""
        from core.paths import AppPaths
        with TemporaryDirectory() as tmp:
            paths = AppPaths(tmp)
            ctl, cfg, ui = self._controller(tmp, str(Path(tmp)), paths=paths)

            # 关掉游戏：页面把进度发过来
            ctl._store_session("BLOB-STATE")
            self.assertEqual(paths.session.read_text(encoding="utf-8"),
                             "BLOB-STATE")
            self.assertTrue(any("msg.session_saved" in line
                                for _tag, line in ui.logs),
                            f"应提示已保存进度: {ui.logs}")

            # 相同内容不重复写（pagehide + beforeunload 会各来一次）
            before = len(ui.logs)
            ctl._store_session("BLOB-STATE")
            self.assertEqual(len(ui.logs), before, "内容没变就不该再提示")

            # 下次打开：页面连上 → 自动灌回去
            applied = []
            ctl.bridge = type("B", (), {
                "apply_save": lambda self, text, timeout=8.0:
                applied.append(text) or True})()
            ctl._restore_session()
            self.assertEqual(applied, ["BLOB-STATE"])
            self.assertTrue(any("msg.session_restored" in line
                                for _tag, line in ui.logs))

            # 再连一次（页面写完会 reload，于是又连上）不该重复灌
            ctl._restore_session()
            self.assertEqual(applied, ["BLOB-STATE"], "只应在每轮服务里恢复一次")

            # 游戏内删档：带 cleared 标记且已经存过 → 存的那份要删掉
            ctl._store_session("BLOB-STATE", cleared=True)
            self.assertFalse(paths.session.is_file(),
                             "游戏删档后不该留着旧进度")
            self.assertTrue(any("msg.session_cleared" in line
                                for _tag, line in ui.logs))
            # 删档后页面还会刷新一次，那几次 cleared 也不能把旧进度又存回来
            ctl._store_session("STALE-ENGINE-STATE", cleared=True)
            self.assertFalse(paths.session.is_file(),
                             "删档后的刷新不该把旧进度存回来")
            # 之后游戏真的存下了新进度（cleared=False）就该继续记录
            ctl._store_session("FRESH-GAME", cleared=False)
            self.assertEqual(paths.session.read_text(encoding="utf-8"),
                             "FRESH-GAME")

    def test_first_run_snapshot_is_kept(self):
        """刚开局、游戏还没自动保存过时 localStorage 也是空的：那是真实进度，要存。"""
        from core.paths import AppPaths
        with TemporaryDirectory() as tmp:
            paths = AppPaths(tmp)
            ctl, _cfg, _ui = self._controller(tmp, str(Path(tmp)), paths=paths)
            ctl._store_session("FIRST-RUN", cleared=True)
            self.assertEqual(paths.session.read_text(encoding="utf-8"),
                             "FIRST-RUN", "从没存过时 cleared 不该丢掉真实进度")

    def test_auto_resume_off_and_missing_file(self):
        from core.paths import AppPaths
        with TemporaryDirectory() as tmp:
            paths = AppPaths(tmp)
            ctl, cfg, _ui = self._controller(tmp, str(Path(tmp)), paths=paths)
            applied = []
            ctl.bridge = type("B", (), {
                "apply_save": lambda self, text, timeout=8.0:
                applied.append(text) or True})()

            # 没有文件 → 什么都不做
            ctl._restore_session()
            self.assertEqual(applied, [])

            # 关掉开关：既不恢复也不保存
            cfg.auto_resume = False
            paths.session.parent.mkdir(parents=True, exist_ok=True)
            paths.session.write_text("OLD", encoding="utf-8")
            ctl._restore_session()
            self.assertEqual(applied, [], "关闭自动续玩时不该恢复")
            ctl._store_session("NEW")
            self.assertEqual(paths.session.read_text(encoding="utf-8"), "OLD",
                             "关闭自动续玩时不该保存")

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
        """配置的固定端口被占用时本次改用自动端口，但配置里的端口要留住。

        早先这里会把自动端口写回配置，于是用户设的固定端口被悄悄换掉：只要
        另有一份程序在跑，每次启动都会换成新的随机端口（实测日志里一串
        「固定端口 N 已被占用，本次改用自动端口」就是这样来的）。
        """
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
                self.assertEqual(cfg.port, str(busy_port),
                                 "占用退回是本次运行的事，不该覆盖配置里的端口")
                self.assertFalse(cfg.updates,
                                 "退回自动端口时不应写配置")
                self.assertTrue(any("msg.port_busy_fallback" in m
                                    for _tag, m in ui.logs),
                                "应提示固定端口被占用")
                self.assertTrue(any(r[0] == "WARN"
                                    for r in logger.records),
                                f"运行日志应留下告警: {logger.records}")
                ctl.stop()
            finally:
                blocker.close()

    def test_open_game_window_follows_launch_settings(self):
        """游戏窗口按「游戏窗口位置/状态」打开（应用窗口或浏览器标签页）。"""
        import web_server
        calls = []

        def fake_open(cfg, url, width=1320, height=840):
            calls.append((cfg, url))
            return "app", ""

        orig = web_server.open_game_window
        web_server.open_game_window = fake_open
        try:
            with TemporaryDirectory() as tmp:
                game = Path(tmp) / "game"
                game.mkdir()
                ctl, cfg, _ui = self._controller(tmp, str(game))
                ctl.start()
                self.assertTrue(ctl.open_game_window())
                self.assertEqual(calls[-1][1], ctl.url)
                self.assertIs(calls[-1][0], cfg)
                ctl.stop()
        finally:
            web_server.open_game_window = orig

    def test_game_window_args_follow_config(self):
        """应用模式下游戏窗口用 --app=（不带 fit）；标签页模式不新开窗口。"""
        import web_server
        calls = []
        orig_popen = web_server.subprocess.Popen
        web_server.subprocess.Popen = lambda args: calls.append(args)
        try:
            with TemporaryDirectory() as tmp:
                exe = Path(tmp) / "msedge.exe"
                exe.write_bytes(b"")
                url = "http://127.0.0.1:9/"
                cfg = FakeConfig()
                cfg.browser = str(exe)
                web_server.open_game_window(cfg, url)
                self.assertIn(f"--app={url}", calls[-1], "游戏页不带 fit 参数")
                w, h = web_server.landscape_window_size()
                self.assertIn(f"--window-size={w},{h}", calls[-1],
                              "游戏窗口初始尺寸应与界面窗口一致")
                self.assertNotIn("--start-fullscreen", calls[-1],
                                 "窗口状态功能已删除")
                cfg.launch_mode = "tab"
                web_server.open_game_window(cfg, url)
                self.assertNotIn("--app=", " ".join(calls[-1]))
                self.assertNotIn("--new-window", calls[-1],
                                 "标签页模式不新开窗口")
        finally:
            web_server.subprocess.Popen = orig_popen

    def test_open_game_window_without_url(self):
        with TemporaryDirectory() as tmp:
            ctl, _cfg, _ui = self._controller(tmp)
            self.assertFalse(ctl.open_game_window())


if __name__ == "__main__":
    unittest.main()
