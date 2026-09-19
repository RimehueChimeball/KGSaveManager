"""core.flows 测试：自动存档/读档、手动导入、事件处理（零 GUI、零真实桥）。"""

import json
import queue
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.flows import SaveFlows  # noqa: E402
from core.slots import SlotStore  # noqa: E402
from core.ui_port import NullUiPort  # noqa: E402

SLOTS = 10
SAVE_TEXT = json.dumps({"saveVersion": 2, "resources": {}}, ensure_ascii=False)


class FakeConfig:
    def __init__(self):
        self.home_slot = 0


class FakeBridge:
    """假页面桥：记录调用并返回预设结果。"""

    def __init__(self, save_text=None, has_client=True, apply_ok=True):
        self.save_text = save_text
        self.has_client = has_client
        self.apply_ok = apply_ok
        self.requested = 0
        self.applied = []

    def request_save(self, timeout=15):
        self.requested += 1
        return self.save_text

    def apply_save(self, blob, timeout=5.0):
        self.applied.append(blob)
        return self.apply_ok


class FakeLogger:
    def __init__(self):
        self.records = []

    def info(self, msg):
        self.records.append(("INFO", msg))

    def warn(self, msg):
        self.records.append(("WARN", msg))

    def error(self, msg):
        self.records.append(("ERROR", msg))


class Harness:
    """组装 core.flows + 替身，供各测试用例复用。"""

    def __init__(self, tmp, *, confirm=True, save_text=SAVE_TEXT,
                 has_client=True, server=True, apply_ok=True):
        self.library = Path(tmp) / "kittens_saves"
        self.library.mkdir(parents=True, exist_ok=True)
        self.backups = Path(tmp) / "backups"
        self.ui = NullUiPort(confirm_default=confirm)
        self.bridge = FakeBridge(save_text, has_client, apply_ok)
        self.server_running = server
        self.events = queue.Queue()
        self.logger = FakeLogger()

        def t(key, **kw):
            if kw:
                return key + "|" + ",".join(f"{k}={v}"
                                            for k, v in sorted(kw.items()))
            return key

        self.slots = SlotStore(self.library, t, SLOTS)
        self.flows = SaveFlows(
            ui=self.ui, slots=self.slots, cfg=FakeConfig(), t=t,
            events=self.events, app_name="APP",
            max_save_size=1024 * 1024,
            get_bridge=lambda: self.bridge,
            is_server_running=lambda: self.server_running,
            backup_dir=self.backups,
            logger=self.logger, reconnect_timeout=0.2)

    # ---- 便捷断言 ----
    def messages(self, kind):
        return [m for m in self.ui.messages if m[0] == kind]

    def logs(self):
        return [msg for _tag, msg in self.ui.logs]

    def drain(self, timeout=2.0):
        """取出一条事件（自动存档在后台线程里产生）。"""
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None


class TestAutoSave(unittest.TestCase):
    def test_requires_running_server(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, server=False)
            self.assertFalse(h.flows.auto_save(0))
            self.assertEqual(h.messages("warn")[0][2], "msg.auto_no_conn")

    def test_requires_page_connection(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, has_client=False)
            self.assertFalse(h.flows.auto_save(0))
            self.assertEqual(h.messages("warn")[0][2], "msg.auto_no_page")

    def test_declined_overwrite_cancels(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, confirm=False)
            h.slots.write(0, "OLD", 1024)
            self.assertFalse(h.flows.auto_save(0))
            self.assertEqual(h.bridge.requested, 0)
            self.assertIn("tag.cancel", [t for t, _ in h.ui.logs])

    def test_worker_emits_event_and_writes_slot(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertTrue(h.flows.auto_save(0))
            item = h.drain()
            self.assertIsNotNone(item, "后台线程未产出事件")
            self.assertEqual(item[0], "auto_save_data")
            self.assertEqual(item[1], 0)
            self.assertEqual(item[2], SAVE_TEXT)

            self.assertTrue(h.flows.handle_event(item))
            dest = h.library / "存档1_1.kgsav"
            self.assertTrue(dest.is_file())
            self.assertIn("msg.auto_saved|dest=存档1_1.kgsav", h.logs())
            self.assertIn("slots_changed", [t for t, _ in h.ui.logs])

    def test_overwrite_confirmed_uses_existing_name(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.slots.write(1, "OLD", 1024)
            h.slots.rename(1, "钢铁")
            self.assertTrue(h.flows.auto_save(1))
            h.flows.handle_event(h.drain())
            self.assertTrue((h.library / "钢铁_2.kgsav").is_file())
            self.assertFalse((h.library / "存档2_2.kgsav").exists())

    def test_timeout_event_is_logged(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, save_text=None)
            self.assertTrue(h.flows.auto_save(3))
            item = h.drain()
            self.assertEqual(item[0], "auto_save_fail")
            self.assertTrue(h.flows.handle_event(item))
            self.assertIn("msg.auto_timeout", h.logs())
            self.assertEqual(h.logger.records[-1][0], "WARN")

    def test_write_failure_is_logged(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.flows.max_save_size = 8
            item = ("auto_save_data", 0, "x" * 100)
            self.assertTrue(h.flows.handle_event(item))
            self.assertTrue(any(t == "tag.error" for t, _ in h.ui.logs))
            self.assertEqual(h.logger.records[-1][0], "ERROR")

    def test_unknown_event_is_not_handled(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertFalse(h.flows.handle_event(("server_log", "x")))


class TestAutoLoad(unittest.TestCase):
    def test_missing_save_warns(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertFalse(h.flows.auto_load(0))
            self.assertEqual(h.messages("warn")[0][2],
                             "dlg.no_file|slot=sv.slot_prefix01.ui.empty_short")

    def test_declined_confirmation_cancels(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, confirm=False)
            h.slots.write(0, SAVE_TEXT, 1024 * 1024)
            self.assertFalse(h.flows.auto_load(0))
            self.assertEqual(h.bridge.applied, [])

    def test_success_sends_to_page(self):
        """下发成功：立即返回 True（已开始），结果经事件回传后再提示。"""
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.slots.write(0, SAVE_TEXT, 1024 * 1024)
            self.assertTrue(h.flows.auto_load(0))
            self.assertTrue(any(m.startswith("msg.auto_load_sending")
                                for m in h.logs()))
            item = h.drain()
            self.assertEqual(item, ("auto_load_result", 0, True))
            self.assertTrue(h.flows.handle_event(item))
            self.assertEqual(h.bridge.applied, [SAVE_TEXT])
            self.assertIn("msg.auto_load_sent", h.logs())
            self.assertEqual(h.messages("notify")[0][2], "msg.auto_load_sent")

    def test_failure_reports_error(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, apply_ok=False)
            h.slots.write(0, SAVE_TEXT, 1024 * 1024)
            self.assertTrue(h.flows.auto_load(0))
            item = h.drain()
            self.assertEqual(item, ("auto_load_result", 0, False))
            self.assertTrue(h.flows.handle_event(item))
            self.assertEqual(h.messages("fail")[0][2], "msg.auto_load_fail")

    def test_unconfirmed_result_warns(self):
        """页面没确认：提示「已发送但未确认」，不谎报成功。"""
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, apply_ok=None)
            h.slots.write(0, SAVE_TEXT, 1024 * 1024)
            self.assertTrue(h.flows.auto_load(0))
            item = h.drain()
            self.assertEqual(item, ("auto_load_result", 0, None))
            self.assertTrue(h.flows.handle_event(item))
            self.assertIn("msg.auto_load_unconfirmed", h.logs())
            self.assertEqual(h.messages("warn")[0][2],
                             "msg.auto_load_unconfirmed")


class TestCopySave(unittest.TestCase):
    def test_missing_save_warns(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertFalse(h.flows.copy_save(0))
            self.assertEqual(h.messages("warn")[0][2],
                             "dlg.no_file|slot=sv.slot_prefix01.ui.empty_short")

    def test_success_copies_and_logs(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.slots.write(4, SAVE_TEXT, 1024 * 1024)
            self.assertTrue(h.flows.copy_save(4))
            self.assertEqual(h.messages("clipboard")[0][2], SAVE_TEXT)
            self.assertIn("msg.load_hint", h.logs())
            self.assertTrue(h.messages("notify"))


class TestManualImport(unittest.TestCase):
    """手动导入：选文件 / 粘贴文本 → 校验 → 写槽位（不再监控文件夹）。"""

    # ---- 选文件导入 ----
    def test_import_file_writes_slot_and_keeps_source(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            src = Path(tmp) / "我的导出.kgsav"
            src.write_text(SAVE_TEXT, encoding="utf-8")
            self.assertTrue(h.flows.import_file(0, src))
            self.assertEqual(
                (h.library / "存档1_1.kgsav").read_text(encoding="utf-8"),
                SAVE_TEXT)
            self.assertTrue(src.exists(), "不能删除用户自己选的文件")
            self.assertTrue(h.messages("notify"))
            self.assertEqual(h.messages("notify")[0][2],
                             "msg.manual_imported|name=我的导出.kgsav,"
                             "slot=sv.slot_prefix01.存档1")
            self.assertTrue(any(t == "slots_changed" for t, _ in h.ui.logs))

    def test_import_file_missing_path_reports(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertFalse(h.flows.import_file(0, Path(tmp) / "nope.kgsav"))
            self.assertEqual(h.messages("fail")[0][0], "fail")
            self.assertFalse((h.library / "存档1_1.kgsav").exists())

    def test_import_file_empty_reports(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            empty = Path(tmp) / "empty.kgsav"
            empty.write_text("", encoding="utf-8")
            self.assertFalse(h.flows.import_file(0, empty))
            self.assertEqual(h.messages("fail")[0][2], "err.file_empty")

    def test_import_file_too_large_reports(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            big = Path(tmp) / "big.kgsav"
            big.write_text("x" * 40, encoding="utf-8")
            h.flows.max_save_size = 8
            self.assertFalse(h.flows.import_file(0, big))
            self.assertTrue(h.messages("fail")[0][2].startswith(
                "err.file_too_large"))

    def test_import_file_reads_growing_file_without_waiting(self):
        """选文件是即时导入：不再等待文件“写稳定”（旧监控逻辑会一直等）。"""
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            src = Path(tmp) / "half.kgsav"
            src.write_text(SAVE_TEXT, encoding="utf-8")
            self.assertTrue(h.flows.import_file(3, src))
            self.assertTrue((h.library / "存档4_4.kgsav").is_file())

    def test_import_filetypes_for_dialog(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            types = h.flows.import_filetypes()
            self.assertEqual(types[0][0], "msg.filetype_save")
            self.assertIn(".kgsav", types[0][1])
            self.assertEqual(types[-1], ("msg.filetype_all", "*.*"))

    # ---- 粘贴文本导入 ----
    def test_import_text_empty_and_oversize(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertFalse(h.flows.import_text(0, "   "))
            self.assertEqual(h.messages("warn")[0][2], "msg.paste_empty")
            h.flows.max_save_size = 8
            self.assertFalse(h.flows.import_text(0, "x" * 20))
            self.assertEqual(h.messages("fail")[0][2],
                             "err.file_too_large|size=20")
            self.assertFalse((h.library / "存档1_1.kgsav").exists())

    def test_import_text_invalid_requires_confirmation(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, confirm=False)
            self.assertFalse(h.flows.import_text(0, "不是存档"))
            self.assertFalse((h.library / "存档1_1.kgsav").exists())
            self.assertEqual(h.messages("confirm")[0][2], "msg.invalid_ask")

    def test_import_text_valid_writes(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertTrue(h.flows.import_text(0, SAVE_TEXT))
            self.assertTrue((h.library / "存档1_1.kgsav").is_file())

    def test_import_text_only_line_endings_are_trimmed(self):
        """粘贴文本只裁行尾换行：UTF-16 存档的尾部空格是载荷本身。"""
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertTrue(h.flows.import_text(0, "PAYLOAD  \r\n"))
            self.assertEqual(
                (h.library / "存档1_1.kgsav").read_text(encoding="utf-8"),
                "PAYLOAD  ", "只裁行尾换行，空格要保留")

    # ---- 覆盖前备份 ----
    def test_overwrite_backs_up_existing_save(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertTrue(h.flows.import_text(0, "FIRST"))
            self.assertEqual(
                (h.library / "存档1_1.kgsav").read_text(encoding="utf-8"),
                "FIRST")
            self.assertTrue(h.flows.import_text(0, "SECOND"))
            baks = list(h.backups.glob("*.bak"))
            self.assertEqual(len(baks), 1, "覆盖前应留一份备份")
            self.assertEqual(baks[0].read_text(encoding="utf-8"), "FIRST")
            self.assertTrue(any("msg.slot_backup" in m for m in h.logs()))

    def test_no_backup_when_slot_empty(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertTrue(h.flows.import_text(0, "ONLY"))
            self.assertEqual(list(h.backups.glob("*.bak")), [],
                             "新槽位没有原文件，不应产生备份")

    # ---- 存档库路径（改名说明用） ----
    def test_copy_library_path(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.flows.copy_library_path()
            self.assertEqual(h.messages("clipboard")[0][2],
                             str(h.library.resolve()))
            self.assertTrue(any("msg.path_copied" in m for m in h.logs()))


class TestCheckLibrary(unittest.TestCase):
    def test_reports_all_sections(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            (h.library / "好_1.kgsav").write_text("DATA", encoding="utf-8")
            (h.library / "空_2.kgsav").write_text("", encoding="utf-8")
            (h.library / "乱名.kgsav").write_text("X", encoding="utf-8")
            h.flows.check_library()
            logs = "\n".join(h.logs())
            self.assertIn("msg.check_start", logs)
            self.assertIn("msg.lib_abnormal", logs)
            self.assertIn("msg.item|f=乱名.kgsav", logs)
            self.assertIn("msg.lib_empty", logs)
            self.assertIn("msg.check_tail", logs)

    def test_clean_library(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.flows.check_library()
            logs = "\n".join(h.logs())
            self.assertIn("msg.lib_clean", logs)


class TestExportDefaults(unittest.TestCase):
    def test_default_import_dir_is_downloads_or_library(self):
        """选文件对话框的默认位置：系统下载文件夹（存在时），否则存档库。"""
        from pathlib import Path as _P
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            chosen = h.flows.default_import_dir()
            downloads = _P.home() / "Downloads"
            if downloads.is_dir():
                self.assertEqual(chosen, downloads)
            else:
                self.assertEqual(chosen, h.library)

    def test_import_filetypes_for_dialog(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            types = h.flows.import_filetypes()
            self.assertEqual(types[0][0], "msg.filetype_save")
            self.assertIn(".kgsav", types[0][1])


if __name__ == "__main__":
    unittest.main()
