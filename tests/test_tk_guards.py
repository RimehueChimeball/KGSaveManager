"""Tk 版（Tkinter 界面）的防护测试。

覆盖 v1.2.3 回迁到主线的两处：
- 界面回调里的未处理异常必须留下痕迹（运行日志 + 页面日志 + 弹窗），
  不能在打包版（无控制台）里变成「点了没反应」；
- 关闭窗口时取消排队中的界面轮询任务。

没有可用 Tk 环境时自动跳过。

注意回收顺序：Tk 的 `Variable` 等对象如果留到别的线程才被 GC，`__del__` 会在那个
线程里调用 Tcl，抛出 “main thread is not in main loop”，并可能把那个线程卡住
（实测：HTTP 请求处理线程在 GC 时进入 `tkinter.Variable.__del__`，请求因此超时）。
所以关闭时先在主线程、解释器还活着的时候放掉引用并 `gc.collect()`。
"""

import gc
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
class TestTkGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        import KGSaveManagerTk as tkmod
        self.tkmod = tkmod
        self.app = None
        self.root = None

    def _build(self):
        # 让程序数据与日志落在临时目录里，避免污染仓库
        root = tk.Tk()
        root.withdraw()
        app = self.tkmod.KGSaveManager(root)
        self.app = app
        self.root = root
        self.addCleanup(self._close)
        return app, root

    def _close(self):
        """关闭应用并在这里把 Tk 对象回收掉（必须在主线程做）。"""
        app, root = self.app, self.root
        if app is not None:
            try:
                app._on_close()
            except Exception:
                pass
        # 先断开引用，再回收：Tk 解释器还活着，变量在这里干净地析构
        self.app = None
        self.root = None
        del app
        gc.collect()
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        gc.collect()

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

    def test_editor_slot_dropdown_is_filled_at_startup(self):
        """启动后「修改存档」页的槽位下拉必须已经列出存档。

        曾经下拉是空的，用户直接点「打开」只会得到「请先选择一个有存档的槽位」。
        """
        import savecodec
        tmp = Path(self.tmp.name)
        library = tmp / "kgsm_data" / "kittens_saves"
        library.mkdir(parents=True)
        blob = savecodec.compress_base64('{"a":1}')
        (library / "自检_3.kgsav").write_text(blob, encoding="utf-8")
        # 让程序数据与存档库落在临时目录里，避免污染仓库
        saved = (self.tkmod.BASE_DIR, self.tkmod.SAVE_LIBRARY,
                 self.tkmod.BACKUP_DIR)
        self.tkmod.BASE_DIR = tmp
        self.tkmod.SAVE_LIBRARY = library
        self.tkmod.BACKUP_DIR = tmp / "kgsm_data" / "backups"

        def restore():
            (self.tkmod.BASE_DIR, self.tkmod.SAVE_LIBRARY,
             self.tkmod.BACKUP_DIR) = saved
        self.addCleanup(restore)

        app, root = self._build()
        root.update()
        values = list(app.edit_slot_combo.cget("values"))
        self.assertTrue(values, "启动后编辑器槽位下拉不应为空")
        self.assertTrue(app.edit_slot_var.get(), "启动后应默认选中一个槽位")
        app.edit_slot_var.set(values[0])
        self.assertEqual(app._selected_edit_slot(), 2,
                         "下拉里的条目应能解析回槽位号")

    def test_editor_toolbar_rows_do_not_stretch(self):
        """「视图/源码」那一行不该被拉高（否则与上下控件间距过大）。"""
        app, root = self._build()
        root.update()
        page = app.notebook.nametowidget(
            app.notebook.tabs()[self.tkmod.TAB_ORDER.index("editor")])
        rows = sorted(page.winfo_children(), key=lambda w: w.winfo_y())
        view_row = rows[1] if len(rows) > 1 else None
        self.assertIsNotNone(view_row)
        root.update_idletasks()
        self.assertLessEqual(
            view_row.winfo_height(), 40,
            f"视图/源码行被撑高了: {view_row.winfo_height()}px")

    def test_poll_job_is_cancelled_on_close(self):
        app, _root = self._build()
        self.assertIsNotNone(getattr(app, "_poll_job", None),
                            "启动时应记录轮询任务 id")
        app._on_close()
        self.assertIsNone(app._poll_job, "退出时应清掉轮询任务 id")


if __name__ == "__main__":
    unittest.main()
