"""core.flows 测试：自动存档/读档、手动存档、事件处理（零 GUI、零真实桥）。"""

import json
import queue
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.flows import (ManualSaveSession, SaveFlows, clean_temp_folder,  # noqa: E402
                        snapshot_dir)
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
        self.temp = Path(tmp) / "kgsm_temp"
        self.temp.mkdir(parents=True, exist_ok=True)
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
            temp_folder=self.temp, max_save_size=1024 * 1024,
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


class TestManualSave(unittest.TestCase):
    def _session(self, h, slot=0):
        return h.flows.start_manual(slot)

    def test_waiting_when_nothing_changes(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            self.assertEqual(h.flows.poll_manual(session), ("waiting", None))

    def test_detects_new_stable_file(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            (h.temp / "export.kgsav").write_text(SAVE_TEXT, encoding="utf-8")
            # 第一次轮询记录候选文件，第二次大小稳定后判定完成
            self.assertEqual(h.flows.poll_manual(session), ("waiting", None))
            state, content = h.flows.poll_manual(session)
            self.assertEqual(state, "detected")
            self.assertEqual(content, SAVE_TEXT)

    def test_detects_same_name_overwrite(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            old = h.temp / "export.kgsav"
            old.write_text("OLD", encoding="utf-8")
            session = self._session(h)
            time.sleep(0.01)
            old.write_text(SAVE_TEXT, encoding="utf-8")
            self.assertEqual(h.flows.poll_manual(session), ("waiting", None))
            state, content = h.flows.poll_manual(session)
            self.assertEqual(state, "detected")
            self.assertEqual(content, SAVE_TEXT)

    def test_waits_while_file_grows(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            f = h.temp / "big.kgsav"
            f.write_text("A", encoding="utf-8")
            h.flows.poll_manual(session)          # 记录候选
            f.write_text("AB", encoding="utf-8")  # 仍在写入
            self.assertEqual(h.flows.poll_manual(session), ("waiting", None))
            self.assertEqual(h.flows.poll_manual(session)[0], "detected")

    def test_finish_writes_removes_temp_and_notifies(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            src = h.temp / "export.kgsav"
            src.write_text(SAVE_TEXT, encoding="utf-8")
            self.assertTrue(h.flows.finish_manual(session, SAVE_TEXT,
                                                  detected=True,
                                                  source_path=str(src)))
            self.assertTrue((h.library / "存档1_1.kgsav").is_file())
            self.assertFalse(src.exists())
            self.assertTrue(h.messages("notify"))
            self.assertTrue(session.closed)

    def test_submit_text_empty_and_oversize(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            self.assertFalse(h.flows.submit_manual_text(session, "   "))
            self.assertEqual(h.messages("warn")[0][2], "msg.paste_empty")
            h.flows.max_save_size = 8
            self.assertFalse(h.flows.submit_manual_text(session, "x" * 20))
            self.assertEqual(h.messages("fail")[0][2],
                             "err.file_too_large|size=20")
            self.assertFalse((h.library / "存档1_1.kgsav").exists())

    def test_submit_text_invalid_requires_confirmation(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, confirm=False)
            session = self._session(h)
            self.assertFalse(h.flows.submit_manual_text(session, "不是存档"))
            self.assertFalse((h.library / "存档1_1.kgsav").exists())
            self.assertFalse(session.closed)

    def test_submit_text_valid_writes(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            self.assertTrue(h.flows.submit_manual_text(session, SAVE_TEXT))
            self.assertTrue((h.library / "存档1_1.kgsav").is_file())
            self.assertTrue(session.closed)

    def test_cancel_marks_session_closed(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            h.flows.cancel_manual(session)
            self.assertEqual(h.flows.poll_manual(session), ("gone", None))

    # ---- 候选文件规则（先导出再点手动存档 / 半成品 / 卡死） ----
    def test_pre_existing_file_becomes_candidate(self):
        """开窗时目录里已有文件也应导入（旧逻辑只看增量，会一直等待）。"""
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            (h.temp / "export.kgsav").write_text(SAVE_TEXT, encoding="utf-8")
            session = self._session(h)
            self.assertEqual(h.flows.poll_manual(session), ("waiting", None))
            self.assertEqual(session.path.name, "export.kgsav")
            self.assertTrue(any("msg.manual_using_existing" in m
                                for m in h.logs()))
            state, content = h.flows.poll_manual(session)
            self.assertEqual(state, "detected")
            self.assertEqual(content, SAVE_TEXT)

    def test_partial_download_is_ignored(self):
        """浏览器未下载完的半成品不应当作存档导入。"""
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            (h.temp / "save.kgsav.crdownload").write_text("half",
                                                          encoding="utf-8")
            self.assertEqual(h.flows.poll_manual(session), ("waiting", None))
            self.assertIsNone(session.path)
            (h.temp / "save.kgsav").write_text(SAVE_TEXT, encoding="utf-8")
            self.assertEqual(h.flows.poll_manual(session), ("waiting", None))
            self.assertEqual(session.path.name, "save.kgsav")

    def test_candidate_gone_resets_scan(self):
        """候选被改名/删除后重置重扫，而不是卡死在旧路径上。"""
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            f = h.temp / "export.kgsav"
            f.write_text(SAVE_TEXT, encoding="utf-8")
            h.flows.poll_manual(session)          # 记录候选
            f.unlink()
            self.assertEqual(h.flows.poll_manual(session), ("waiting", None))
            self.assertIsNone(session.path, "候选消失后应重置")
            self.assertTrue(any("msg.manual_candidate_gone" in m
                                for m in h.logs()))
            (h.temp / "retry.kgsav").write_text(SAVE_TEXT, encoding="utf-8")
            h.flows.poll_manual(session)
            self.assertEqual(h.flows.poll_manual(session)[0], "detected")

    def test_stuck_candidate_resets_after_timeout(self):
        """文件长时间写不完：放弃该候选，重新扫描。"""
        with TemporaryDirectory() as tmp:
            import core.flows as flows_mod
            h = Harness(tmp)
            old = flows_mod.MANUAL_CANDIDATE_TIMEOUT
            flows_mod.MANUAL_CANDIDATE_TIMEOUT = 0.0
            try:
                session = self._session(h)
                f = h.temp / "stuck.kgsav"
                f.write_text("A", encoding="utf-8")
                h.flows.poll_manual(session)      # 记录候选
                f.write_text("AB", encoding="utf-8")
                self.assertEqual(h.flows.poll_manual(session), ("waiting", None))
                self.assertIsNone(session.path, "超时后应放弃候选")
                self.assertTrue(any("msg.manual_candidate_busy" in m
                                    for m in h.logs()))
            finally:
                flows_mod.MANUAL_CANDIDATE_TIMEOUT = old

    # ---- 载荷与备份 ----
    def test_only_line_endings_are_trimmed(self):
        """粘贴文本只裁行尾换行：UTF-16 存档的尾部空格是载荷本身。"""
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            self.assertTrue(h.flows.submit_manual_text(session,
                                                       "PAYLOAD  \r\n"))
            self.assertEqual(
                (h.library / "存档1_1.kgsav").read_text(encoding="utf-8"),
                "PAYLOAD  ", "只裁行尾换行，空格要保留")

    def test_overwrite_backs_up_existing_save(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            self.assertTrue(h.flows.finish_manual(session, "FIRST",
                                                  detected=False))
            self.assertEqual(
                (h.library / "存档1_1.kgsav").read_text(encoding="utf-8"),
                "FIRST")
            session2 = self._session(h)
            self.assertTrue(h.flows.finish_manual(session2, "SECOND",
                                                  detected=False))
            baks = list(h.backups.glob("*.bak"))
            self.assertEqual(len(baks), 1, "覆盖前应留一份备份")
            self.assertEqual(baks[0].read_text(encoding="utf-8"), "FIRST")
            self.assertTrue(any("msg.slot_backup" in m for m in h.logs()))

    def test_no_backup_when_slot_empty(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            session = self._session(h)
            self.assertTrue(h.flows.finish_manual(session, "ONLY",
                                                  detected=False))
            self.assertEqual(list(h.backups.glob("*.bak")), [],
                             "新槽位没有原文件，不应产生备份")

    def test_copy_temp_path(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.flows.copy_temp_path()
            self.assertEqual(h.messages("clipboard")[0][2], str(h.temp.resolve()))
            self.assertTrue(any("msg.path_copied" in m for m in h.logs()))


class TestCheckLibrary(unittest.TestCase):
    def test_reports_all_sections(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            (h.library / "好_1.kgsav").write_text("DATA", encoding="utf-8")
            (h.library / "空_2.kgsav").write_text("", encoding="utf-8")
            (h.library / "乱名.kgsav").write_text("X", encoding="utf-8")
            (h.temp / "残留.kgsav").write_text("X", encoding="utf-8")
            h.flows.check_library()
            logs = "\n".join(h.logs())
            self.assertIn("msg.check_start", logs)
            self.assertIn("msg.lib_abnormal", logs)
            self.assertIn("msg.item|f=乱名.kgsav", logs)
            self.assertIn("msg.lib_empty", logs)
            self.assertIn("msg.temp_files", logs)
            self.assertIn("msg.check_tail", logs)

    def test_clean_library(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.flows.check_library()
            logs = "\n".join(h.logs())
            self.assertIn("msg.lib_clean", logs)
            self.assertIn("msg.temp_clean", logs)


class TestHelpers(unittest.TestCase):
    def test_snapshot_reports_files(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.kgsav"
            p.write_text("x", encoding="utf-8")
            snap = snapshot_dir(tmp)
            self.assertEqual(snap["a.kgsav"][1], 1)

    def test_snapshot_missing_folder(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(snapshot_dir(Path(tmp) / "nope"), {})

    def test_clean_temp_folder_removes_only_old(self):
        import os
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            old = folder / "old.kgsav"
            fresh = folder / "fresh.kgsav"
            old.write_text("x", encoding="utf-8")
            fresh.write_text("y", encoding="utf-8")
            past = time.time() - 10 * 86400
            os.utime(old, (past, past))
            logger = FakeLogger()
            removed = clean_temp_folder(folder, 7 * 86400, logger)
            self.assertEqual(removed, 1)
            self.assertFalse(old.exists())
            self.assertTrue(fresh.exists())
            self.assertEqual(logger.records[0][0], "INFO")


class TestSessionModel(unittest.TestCase):
    def test_session_snapshot_is_taken_at_start(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "exists.kgsav").write_text("x", encoding="utf-8")
            session = ManualSaveSession(0, folder)
            self.assertIn("exists.kgsav", session.snapshot)
            self.assertFalse(session.closed)


if __name__ == "__main__":
    unittest.main()
