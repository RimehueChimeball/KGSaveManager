"""core.slots 测试：槽位识别、显示名、读写、改名、异常检查（不启动 GUI）。"""

import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.slots import SlotStore, parse_filename  # noqa: E402

SLOTS = 10


def make_store(library, slot_count=SLOTS):
    """用 key 本身当翻译结果的替身 t（断言时好读）。"""
    def t(key, **kw):
        return key + (str(kw) if kw else "")
    return SlotStore(library, t, slot_count)


class TestParseFilename(unittest.TestCase):
    def test_valid_names(self):
        self.assertEqual(parse_filename("钢铁_1.kgsav", SLOTS), (0, "钢铁"))
        self.assertEqual(parse_filename("Save10.kgsav_x_10.kgsav", SLOTS)[0], 9)
        self.assertEqual(parse_filename("a_b_3.kgsav", SLOTS), (2, "a_b"))

    def test_rejects_bad_names(self):
        for name in ("存档.kgsav", "存档_0.kgsav", "存档_11.kgsav",
                     "存档_x.kgsav", "_3.kgsav", "存档_3.txt", "存档3.kgsav"):
            self.assertIsNone(parse_filename(name, SLOTS), name)


class TestScan(unittest.TestCase):
    def test_empty_library(self):
        with TemporaryDirectory() as tmp:
            store = make_store(tmp)
            self.assertEqual(len(store.info), SLOTS)
            self.assertFalse(any(i['exists'] for i in store.info))

    def test_missing_library_is_tolerated(self):
        with TemporaryDirectory() as tmp:
            store = make_store(Path(tmp) / "nope")
            self.assertFalse(any(i['exists'] for i in store.info))

    def test_slot_detection_and_name(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            (lib / "钢铁_3.kgsav").write_text("DATA", encoding="utf-8")
            store = make_store(lib)
            self.assertTrue(store.exists(2))
            self.assertFalse(store.exists(0))
            self.assertEqual(store.name(2), "钢铁")
            self.assertEqual(store.name(0), "")
            self.assertEqual(store.path(2).name, "钢铁_3.kgsav")
            self.assertIsNone(store.path(0))

    def test_newest_file_wins(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            old = lib / "旧名_1.kgsav"
            old.write_text("OLD", encoding="utf-8")
            time.sleep(0.01)
            new = lib / "新名_1.kgsav"
            new.write_text("NEW", encoding="utf-8")
            store = make_store(lib)
            self.assertEqual(store.name(0), "新名")

    def test_ignores_subdirectories_and_other_files(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            (lib / "sub_1.kgsav").mkdir()
            (lib / "readme.txt").write_text("x", encoding="utf-8")
            store = make_store(lib)
            self.assertFalse(any(i['exists'] for i in store.info))


class TestLabels(unittest.TestCase):
    def test_label_and_default_base(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            (lib / "钢铁_1.kgsav").write_text("D", encoding="utf-8")
            store = make_store(lib)

            def t(key, **kw):
                table = {"sv.slot_prefix": "存档", "ui.empty_short": "（空）"}
                return table.get(key, key)

            store.t = t
            self.assertEqual(store.label(0), "存档01.钢铁")
            self.assertEqual(store.label(1), "存档02.（空）")
            self.assertEqual(store.default_base(0), "存档1")
            self.assertEqual(store.base_for_write(0), "钢铁")
            self.assertEqual(store.base_for_write(1), "存档2")


class TestReadWrite(unittest.TestCase):
    def test_write_and_refresh(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            store = make_store(lib)
            dest, err = store.write(2, "  SAVEDATA  ", 1024)
            self.assertIsNone(err)
            self.assertEqual(dest.name, "存档3_3.kgsav")
            self.assertEqual(dest.read_text(encoding="utf-8"), "SAVEDATA")
            self.assertTrue(store.exists(2))
            self.assertEqual(sorted(p.name for p in lib.iterdir()),
                             ["存档3_3.kgsav"])

    def test_write_overwrites_without_leaving_tmp(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            store = make_store(lib)
            store.write(0, "FIRST", 1024)
            dest, err = store.write(0, "SECOND", 1024)
            self.assertIsNone(err)
            self.assertEqual(dest.read_text(encoding="utf-8"), "SECOND")
            self.assertEqual(len(list(lib.iterdir())), 1)

    def test_write_empty_returns_nothing(self):
        with TemporaryDirectory() as tmp:
            store = make_store(tmp)
            self.assertEqual(store.write(0, "   ", 1024), (None, None))

    def test_write_too_large_reports_key(self):
        with TemporaryDirectory() as tmp:
            store = make_store(tmp, )
            dest, err = store.write(0, "x" * 10, 8)
            self.assertIsNone(dest)
            self.assertEqual(err[0], "err.file_too_large")
            self.assertEqual(err[1], {"size": 10})

    def test_read_validates_size(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            empty = lib / "空_1.kgsav"
            empty.write_text("", encoding="utf-8")
            store = make_store(lib)
            with self.assertRaises(ValueError):
                store.read(empty, 1024)
            big = lib / "大_2.kgsav"
            big.write_text("x" * 20, encoding="utf-8")
            with self.assertRaises(ValueError):
                store.read(big, 8)
            ok = lib / "好_3.kgsav"
            ok.write_text("DATA", encoding="utf-8")
            self.assertEqual(store.read(ok, 1024), "DATA")


class TestRename(unittest.TestCase):
    def test_rename_success(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            (lib / "旧名_2.kgsav").write_text("DATA", encoding="utf-8")
            store = make_store(lib)
            path, err = store.rename(1, "新名")
            self.assertIsNone(err)
            self.assertEqual(path.name, "新名_2.kgsav")
            self.assertFalse((lib / "旧名_2.kgsav").exists())
            self.assertEqual(store.name(1), "新名")

    def test_rename_rejects_invalid(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            (lib / "旧名_2.kgsav").write_text("D", encoding="utf-8")
            store = make_store(lib)
            for bad in ("", "   ", "a/b", "a\\b", "a:b", "x" * 41):
                path, err = store.rename(1, bad)
                self.assertIsNone(path, bad)
                self.assertEqual(err, "err.name_invalid")
            self.assertTrue((lib / "旧名_2.kgsav").exists())

    def test_rename_reports_existing_target(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            (lib / "旧名_2.kgsav").write_text("A", encoding="utf-8")
            store = make_store(lib)
            # 快照之后才出现的同名目标文件（更贴近真实：用户手动放进去的）
            (lib / "占用_2.kgsav").write_text("B", encoding="utf-8")
            path, err = store.rename(1, "占用")
            self.assertIsNone(path)
            self.assertTrue(err.startswith("err.name_file_exists"))

    def test_rename_uses_newest_file_of_slot(self):
        """同一槽位有新旧两个文件时，改名作用于最新的那个。"""
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            (lib / "旧名_2.kgsav").write_text("A", encoding="utf-8")
            time.sleep(0.01)
            (lib / "新名_2.kgsav").write_text("B", encoding="utf-8")
            store = make_store(lib)
            path, err = store.rename(1, "改名")
            self.assertIsNone(err)
            self.assertEqual(path.name, "改名_2.kgsav")
            self.assertTrue((lib / "旧名_2.kgsav").exists(),
                            "不应动到同槽位的旧文件")

    def test_rename_without_file(self):
        with TemporaryDirectory() as tmp:
            store = make_store(tmp)
            path, err = store.rename(0, "新名")
            self.assertIsNone(path)
            self.assertEqual(err, "err.rename_need_file")

    def test_rename_same_name_is_noop(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            (lib / "同名_1.kgsav").write_text("D", encoding="utf-8")
            store = make_store(lib)
            path, err = store.rename(0, "同名")
            self.assertIsNone(err)
            self.assertEqual(path.name, "同名_1.kgsav")


class TestCheck(unittest.TestCase):
    def test_check_reports_invalid_and_empty(self):
        with TemporaryDirectory() as tmp:
            lib = Path(tmp)
            (lib / "好_1.kgsav").write_text("DATA", encoding="utf-8")
            (lib / "空_2.kgsav").write_text("", encoding="utf-8")
            (lib / "乱名.kgsav").write_text("X", encoding="utf-8")
            (lib / "笔记.txt").write_text("X", encoding="utf-8")
            store = make_store(lib)
            result = store.check()
            self.assertEqual(result['invalid'], ["乱名.kgsav", "笔记.txt"])
            self.assertEqual(result['empty'], ["空_2.kgsav"])


if __name__ == "__main__":
    unittest.main()
