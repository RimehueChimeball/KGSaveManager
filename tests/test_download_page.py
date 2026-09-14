"""下载页回归测试：点「开始下载」必须真的启动下载，而不是静默失败。

这个用例针对 v1.2.0–v1.2.2 的真实故障：版本映射表存的是 ref 字符串，
`_dl_start` 却按两个值拆包，回调里抛 ValueError；打包版没有控制台，
用户看到的就是「点了没反应、也没有日志」。这里用替身把整条路径跑一遍。
"""

import sys
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import downloader  # noqa: E402
import KGSaveManager as kgm  # noqa: E402


def _tk_available():
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


class FakeDownloader:
    """替换 downloader.install_game：不联网，只回答「被调用了」。"""

    def __init__(self):
        self.calls = []
        self.done = threading.Event()

    def __call__(self, repo, mirror, ref, target, progress=None, cancel=None,
                 delete_temp=True):
        self.calls.append({"repo": repo, "mirror": mirror, "ref": ref,
                           "target": target, "delete_temp": delete_temp})
        if progress:
            progress(10, 100)
        Path(target).mkdir(parents=True, exist_ok=True)
        (Path(target) / "index.html").write_text("x", encoding="utf-8")
        if progress:
            progress(100, 100)
        self.done.set()
        return target


@unittest.skipUnless(_tk_available(), "无可用 Tk 环境")
class TestDownloadStart(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.orig_install = downloader.install_game
        self.fake = FakeDownloader()
        downloader.install_game = self.fake
        self.addCleanup(self._restore)

        self.root = tk.Tk()
        self.root.withdraw()
        self.app = kgm.KGSaveManager(self.root)
        self.addCleanup(self._close_app)
        self.pump(1.0)

    def _close_app(self):
        """按正常退出流程关闭（会取消排队中的 after，避免 Tcl 噪音）。"""
        try:
            self.app._on_close()
        except Exception:
            try:
                self.root.destroy()
            except Exception:
                pass

    def _restore(self):
        downloader.install_game = self.orig_install

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.root.update()
            time.sleep(0.03)

    def _version_map(self, items):
        """模拟版本拉取结果落到界面状态。"""
        self.app._handle_dl_versions(items)

    def test_version_map_values_are_refs(self):
        self._version_map([("branch", "master", "refs/heads/master"),
                           ("tag", "v1.6.1", "refs/tags/v1.6.1")])
        ver_map = self.app.dl["ver_map"]
        for label, value in ver_map.items():
            self.assertIsInstance(value, str,
                                  f"{label} 的映射值应为 ref 字符串")

    def test_start_downloads_without_exception(self):
        target = str(Path(self.tmp.name) / "KittensGame")
        self._version_map([("branch", "master", "refs/heads/master")])
        self.app.dl_dir_var.set(target)
        self.app.dl_version_combo.current(0)

        self.app._dl_start()                      # 旧版在这里抛 ValueError
        self.assertTrue(self.app.dl.get("busy"), "点开始后应进入忙碌状态")
        self.assertTrue(self.fake.done.wait(5), "下载线程未被启动")
        self.pump(1.0)                            # 处理完成事件
        self.assertFalse(self.app.dl.get("busy"), "完成后应解除忙碌状态")
        self.assertEqual(self.fake.calls[0]["ref"], "refs/heads/master")
        self.assertEqual(self.fake.calls[0]["target"], target)
        self.assertTrue((Path(target) / "index.html").is_file())

    def test_start_logs_and_unlocks_after_done(self):
        target = str(Path(self.tmp.name) / "KittensGame2")
        self._version_map([("branch", "master", "refs/heads/master")])
        self.app.dl_dir_var.set(target)
        self.app.dl_version_combo.current(0)
        self.app._dl_start()

        deadline = time.time() + 8
        while time.time() < deadline and self.app.dl.get("busy"):
            self.pump(0.1)
        self.assertFalse(self.app.dl.get("busy"), "完成后应解除忙碌状态")
        log = self.app.dl_log_text.get("1.0", "end")
        self.assertIn(self.app.t("dl.done", dir="").split("{")[0].strip()[:6],
                      log, f"完成日志缺失: {log!r}")

    def test_start_without_version_warns(self):
        self.app.dl["ver_map"] = {}
        self.app.dl_version_combo.set("")
        self.app._dl_start()          # 不应抛异常
        self.assertFalse(self.app.dl.get("busy"))

    def test_callback_exception_is_reported(self):
        """回调异常必须有痕迹：运行日志 + 页面日志，而不是静默消失。"""
        self.root.report_callback_exception(ValueError, ValueError("boom"),
                                            None)
        logged = Path(self.app.logger.path).read_text(encoding="utf-8")
        self.assertIn("界面回调异常", logged)
        self.assertIn("boom", self.app.log_text.get("1.0", "end"))


if __name__ == "__main__":
    unittest.main()
