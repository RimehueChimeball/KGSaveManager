"""手动存档检测状态机的回归测试（本次修复的核心）。

覆盖三类真实缺陷：
1. 候选文件被改名/删除后，旧逻辑会永远空转（detecting_path 不重置、
   size<=0 恒真），真正的存档再也导不进来；
2. 浏览器/下载器留下的半成品（.crdownload/.part）不该被当作存档；
3. "先导出文件、再点手动存档"的顺序过去完全无效。

用替身驱动真实的 _manual_poll：不需要用户交互。
"""

import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from save_flows import SaveFlowMixin  # noqa: E402

import save_flows  # noqa: E402

SAVE_JSON = '{"saveVersion":2,"resources":{"catnip":{"value":1}}}'

# 测试里不要弹真实对话框（假窗口没有 .tk，会直接抛异常）
DIALOGS = []
save_flows.messagebox.showinfo = (
    lambda *a, **k: DIALOGS.append(("info", a)))
save_flows.messagebox.showwarning = (
    lambda *a, **k: DIALOGS.append(("warn", a)))
save_flows.messagebox.showerror = (
    lambda *a, **k: DIALOGS.append(("error", a)))
save_flows.messagebox.askyesno = (
    lambda *a, **k: (DIALOGS.append(("ask", a)), True)[1])


class FakeWindow:
    """替代 Toplevel：记录排队的轮询（不真的开窗口）。"""

    def __init__(self):
        self.queue = []

    def after(self, _ms, func):
        self.queue.append(func)

    def run_next(self):
        if not self.queue:
            return False
        self.queue.pop(0)()
        return True

    def destroy(self):
        self.queue.clear()

    def winfo_exists(self):
        return True


class Stub(SaveFlowMixin):
    def __init__(self, temp_folder, library):
        self.app_name = "TEST"
        self.temp_folder = Path(temp_folder)
        self.save_library = Path(library)
        self.max_save_size = 1024 * 1024
        self.backup_dir = Path(library).parent / "backups"
        self.slot_names = {}
        self.logs = []
        self.written = []
        self._manual_win = None
        self._manual_ctx = None

    # ---- 依赖桩 ----
    def t(self, key, **kw):
        return key + (str(kw) if kw else "")

    def log(self, msg, tag=""):
        self.logs.append((tag, msg))

    def slot_name(self, index):
        return self.slot_names.get(index, "")

    def slot_default_base(self, index):
        return f"Save{index + 1:02d}"

    def slot_label(self, index):
        return f"Save{index + 1:02d}"

    def update_slots_display(self):
        pass

    def _widget_alive(self, _widget):
        return True

    def _write_save_to_slot(self, slot, text):
        self.written.append((slot, text))
        dest = Path(self.save_library) / f"Save{slot + 1:02d}_{slot + 1}.kgsav"
        dest.write_text(text, encoding="utf-8")
        return dest


class ManualPollHarness:
    def __init__(self, tmp):
        self.tmp = Path(tmp)
        self.temp = self.tmp / "kgsm_temp"
        self.temp.mkdir(parents=True, exist_ok=True)
        self.lib = self.tmp / "kittens_saves"
        self.lib.mkdir(parents=True, exist_ok=True)
        self.stub = Stub(self.temp, self.lib)
        self.win = FakeWindow()

    def open_dialog(self):
        self.stub._manual_ctx = {
            "slot": 0, "win": self.win, "closed": False,
            "before": self.stub._temp_snapshot(),
            "detecting_path": None, "last_size": -1, "last_mtime": -1,
            "scanned_existing": False, "candidate_at": time.time(),
        }
        # 真实流程里 manual_save_action 会 after(700, _manual_poll)，
        # 夹具等价于把它排进队列
        self.win.queue.append(self.stub._manual_poll)
        return self.stub._manual_ctx

    def tick(self, times=3):
        for _ in range(times):
            self.win.run_next()


class TestManualDetection(unittest.TestCase):
    def test_new_file_is_imported(self):
        with TemporaryDirectory() as tmp:
            h = ManualPollHarness(tmp)
            h.open_dialog()
            (h.temp / "export.kgsav").write_text(SAVE_JSON, encoding="utf-8")
            h.tick(4)
            self.assertEqual(len(h.stub.written), 1, "新文件应被导入")
            self.assertEqual(h.stub.written[0][1], SAVE_JSON)

    def test_existing_file_before_dialog_is_imported(self):
        """先导出文件、再点手动存档（旧逻辑完全无效）。"""
        with TemporaryDirectory() as tmp:
            h = ManualPollHarness(tmp)
            (h.temp / "already.kgsav").write_text(SAVE_JSON, encoding="utf-8")
            h.open_dialog()
            h.tick(4)
            self.assertEqual(len(h.stub.written), 1,
                             "开窗前放入的文件也应被导入")
            self.assertTrue(any("msg.manual_using_existing" in m
                                for _t, m in h.stub.logs))

    def test_partial_download_is_ignored(self):
        with TemporaryDirectory() as tmp:
            h = ManualPollHarness(tmp)
            h.open_dialog()
            (h.temp / "save.kgsav.crdownload").write_text("half", encoding="utf-8")
            (h.temp / "save.kgsav.part").write_text("half", encoding="utf-8")
            h.tick(4)
            self.assertEqual(h.stub.written, [], "半成品不应被导入")
            (h.temp / "real.kgsav").write_text(SAVE_JSON, encoding="utf-8")
            h.tick(4)
            self.assertEqual(len(h.stub.written), 1, "真正的存档随后应被导入")

    def test_candidate_renamed_does_not_stall(self):
        """候选被改名（浏览器下载完成后改名）后必须继续工作，不能卡死。"""
        with TemporaryDirectory() as tmp:
            h = ManualPollHarness(tmp)
            h.open_dialog()
            downloading = h.temp / "game.kgsav.crdownload"
            downloading.write_text("partial", encoding="utf-8")
            h.tick(2)
            # 半成品被忽略；下载完成 → 正式文件名出现
            downloading.rename(h.temp / "game.kgsav")
            (h.temp / "game.kgsav").write_text(SAVE_JSON, encoding="utf-8")
            h.tick(6)
            self.assertEqual(len(h.stub.written), 1, "改名后的文件应被导入")

    def test_candidate_deleted_resets_and_rescans(self):
        with TemporaryDirectory() as tmp:
            h = ManualPollHarness(tmp)
            h.open_dialog()
            ghost = h.temp / "ghost.kgsav"
            ghost.write_text(SAVE_JSON, encoding="utf-8")
            h.tick(1)                     # 只记录候选，还没读取
            self.assertIsNotNone(h.stub._manual_ctx["detecting_path"])
            ghost.unlink()                # 候选在读取前消失
            h.tick(2)
            self.assertIsNone(h.stub._manual_ctx["detecting_path"],
                              "候选消失后必须重置，否则会永远空转")
            (h.temp / "later.kgsav").write_text(SAVE_JSON, encoding="utf-8")
            h.tick(4)
            self.assertEqual(len(h.stub.written), 1, "重扫后应能导入新文件")

    def test_busy_candidate_times_out_and_rescans(self):
        import save_flows
        with TemporaryDirectory() as tmp:
            h = ManualPollHarness(tmp)
            h.open_dialog()
            growing = h.temp / "growing.kgsav"
            growing.write_text("a", encoding="utf-8")
            h.tick(1)                       # 记录候选（此刻大小 1）
            ctx = h.stub._manual_ctx
            self.assertIsNotNone(ctx["detecting_path"])
            # 假装它已经写了很久还在变：应重置重扫，而不是无限空转
            ctx["candidate_at"] = (
                time.time() - save_flows.MANUAL_CANDIDATE_TIMEOUT - 1)
            growing.write_text("ab", encoding="utf-8")
            h.tick(1)
            self.assertIsNone(h.stub._manual_ctx["detecting_path"],
                              "长时间不稳定的候选应被重置")
            self.assertTrue(any("msg.manual_candidate_busy" in m
                                for _t, m in h.stub.logs))

    def test_no_spurious_import_when_folder_empty(self):
        with TemporaryDirectory() as tmp:
            h = ManualPollHarness(tmp)
            h.open_dialog()
            h.tick(5)
            self.assertEqual(h.stub.written, [])


if __name__ == "__main__":
    unittest.main()
