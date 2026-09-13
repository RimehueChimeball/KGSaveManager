"""save_flows 纯逻辑测试：临时目录快照检测与槽位写入（不启动 GUI）。"""

import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from save_flows import SaveFlowMixin  # noqa: E402


class _Stub(SaveFlowMixin):
    """只提供 save_flows 需要的属性的最小替身。"""

    def __init__(self, temp_folder, save_library, max_save_size=1024 * 1024):
        self.temp_folder = Path(temp_folder)
        self.save_library = Path(save_library)
        self.max_save_size = max_save_size
        self.logs = []
        self.errors = []
        self.display_updates = 0
        self.slot_names = {}

    # --- 依赖桩 ---
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
        self.display_updates += 1


class TestTempSnapshot(unittest.TestCase):
    def test_snapshot_reports_files(self):
        with TemporaryDirectory() as tmp:
            stub = _Stub(tmp, tmp)
            p = Path(tmp) / "a.kgsav"
            p.write_text("x", encoding="utf-8")
            snap = stub._temp_snapshot()
            self.assertIn("a.kgsav", snap)
            mtime_ns, size = snap["a.kgsav"]
            self.assertEqual(size, 1)
            self.assertGreater(mtime_ns, 0)

    def test_overwrite_same_name_is_detected(self):
        """同名覆盖（旧逻辑的盲区）必须能被识别为变化。"""
        with TemporaryDirectory() as tmp:
            stub = _Stub(tmp, tmp)
            p = Path(tmp) / "export.kgsav"
            p.write_text("old", encoding="utf-8")
            before = stub._temp_snapshot()

            time.sleep(0.01)
            p.write_text("new-and-longer-content", encoding="utf-8")
            after = stub._temp_snapshot()

            changed = [n for n, meta in after.items()
                       if before.get(n) != meta]
            self.assertEqual(changed, ["export.kgsav"],
                             "同名覆盖应被检测为新变化")

    def test_untouched_file_is_not_a_change(self):
        with TemporaryDirectory() as tmp:
            stub = _Stub(tmp, tmp)
            (Path(tmp) / "keep.kgsav").write_text("same", encoding="utf-8")
            before = stub._temp_snapshot()
            after = stub._temp_snapshot()
            changed = [n for n, meta in after.items()
                       if before.get(n) != meta]
            self.assertEqual(changed, [])

    def test_subdirectories_are_ignored(self):
        with TemporaryDirectory() as tmp:
            stub = _Stub(tmp, tmp)
            (Path(tmp) / "sub").mkdir()
            self.assertEqual(stub._temp_snapshot(), {})

    def test_missing_folder_returns_empty(self):
        with TemporaryDirectory() as tmp:
            stub = _Stub(Path(tmp) / "nope", tmp)
            self.assertEqual(stub._temp_snapshot(), {})


class TestRemoveTempFile(unittest.TestCase):
    def test_removes_and_logs(self):
        with TemporaryDirectory() as tmp:
            stub = _Stub(tmp, tmp)
            p = Path(tmp) / "taken.kgsav"
            p.write_text("data", encoding="utf-8")
            stub._remove_temp_file(str(p))
            self.assertFalse(p.exists())
            self.assertTrue(any("taken.kgsav" in m for _, m in stub.logs))

    def test_missing_file_is_ignored(self):
        with TemporaryDirectory() as tmp:
            stub = _Stub(tmp, tmp)
            stub._remove_temp_file(str(Path(tmp) / "absent.kgsav"))
            self.assertEqual(stub.logs, [])


class TestWriteSaveToSlot(unittest.TestCase):
    def test_writes_atomically_and_refreshes_display(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp) / "kittens_saves"
            lib.mkdir()
            stub = _Stub(tmp, lib)
            dest = stub._write_save_to_slot(2, "  SAVEDATA  ")
            self.assertEqual(dest.name, "Save03_3.kgsav")
            self.assertEqual(dest.read_text(encoding="utf-8"), "SAVEDATA")
            self.assertEqual(stub.display_updates, 1)
            self.assertEqual(
                sorted(p.name for p in lib.iterdir()), ["Save03_3.kgsav"],
                "不应留下临时文件")

    def test_uses_existing_slot_name(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp) / "kittens_saves"
            lib.mkdir()
            stub = _Stub(tmp, lib)
            stub.slot_names[0] = "钢铁"
            dest = stub._write_save_to_slot(0, "X")
            self.assertEqual(dest.name, "钢铁_1.kgsav")

    def test_rejects_empty_and_oversized(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp) / "kittens_saves"
            lib.mkdir()
            stub = _Stub(tmp, lib, max_save_size=8)
            self.assertIsNone(stub._write_save_to_slot(0, "   "))
            self.assertIsNone(stub._write_save_to_slot(0, "x" * 9))
            self.assertEqual(list(lib.iterdir()), [])

    def test_overwrite_is_replaced_not_appended(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp) / "kittens_saves"
            lib.mkdir()
            stub = _Stub(tmp, lib)
            stub._write_save_to_slot(0, "FIRST")
            stub._write_save_to_slot(0, "SECOND")
            files = list(lib.iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_text(encoding="utf-8"), "SECOND")


if __name__ == "__main__":
    unittest.main()
