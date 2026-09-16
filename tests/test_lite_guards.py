"""Lite 版（Tkinter 界面）的防护测试。

覆盖 v1.2.3 回迁到主线的两处：
- 界面回调里的未处理异常必须留下痕迹（运行日志 + 页面日志 + 弹窗），
  不能在打包版（无控制台）里变成「点了没反应」；
- 关闭窗口时取消排队中的界面轮询任务。

没有可用 Tk 环境时自动跳过。
"""

import sys
import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _tk_available():
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


@unittest.skipUnless(_tk_available(), "无可用 Tk 环境")
class TestLiteGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        import KGSaveManagerLite as lite
        self.lite = lite
        self.app = None

    def _build(self):
        # 让程序数据与日志落在临时目录里，避免污染仓库
        root = tk.Tk()
        root.withdraw()
        core_base = Path(self.tmp.name)
        app = self.lite.KGSaveManager(root)
        self.addCleanup(self._close, app, root)
        self.app = app
        return app, root

    def _close(self, app, root):
        try:
            app._on_close()
        except Exception:
            try:
                root.destroy()
            except Exception:
                pass

    def test_callback_exception_is_logged_and_reported(self):
        app, _root = self._build()
        dialogs = []
        app.ui.fail = lambda message, title="": dialogs.append((title, message))

        app.root.report_callback_exception(ValueError, ValueError("boom"),
                                           None)

        run_log = Path(app.logger.path).read_text(encoding="utf-8")
        self.assertIn("界面回调异常", run_log)
        self.assertIn("boom", run_log)
        self.assertIn("boom", app.log_text.get("1.0", "end"))
        self.assertTrue(dialogs, "应弹窗告知用户")
        self.assertIn("boom", dialogs[0][1])
        self.assertIn(str(app.paths.logs), dialogs[0][1])

    def test_poll_job_is_cancelled_on_close(self):
        app, _root = self._build()
        self.assertIsNotNone(getattr(app, "_poll_job", None),
                            "启动时应记录轮询任务 id")
        app._on_close()
        self.assertIsNone(app._poll_job, "退出时应清掉轮询任务 id")


if __name__ == "__main__":
    unittest.main()
