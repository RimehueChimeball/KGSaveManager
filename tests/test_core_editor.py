"""core.editor 测试：解码、树行、改值、写回（含备份）。"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import savecodec  # noqa: E402
from core.editor import (EditorController, decode_to_obj,  # noqa: E402
                         json_compact, json_pretty)
from core.slots import SlotStore  # noqa: E402
from core.ui_port import NullUiPort  # noqa: E402

SAVE = {"saveVersion": 2, "resources": {"catnip": {"value": 12.5}},
        "buildings": [{"name": "hut", "val": 3}, 7, "x"]}


class FakeBridge:
    def __init__(self, blob=None, has_client=True, apply_ok=True):
        self.blob = blob
        self.has_client = has_client
        self.apply_ok = apply_ok
        self.applied = []

    def request_save(self, timeout=15):
        return self.blob

    def apply_save(self, blob, timeout=5.0):
        self.applied.append(blob)
        return self.apply_ok


class Harness:
    def __init__(self, tmp, *, bridge=None, server=True):
        self.library = Path(tmp) / "saves"
        self.library.mkdir(parents=True, exist_ok=True)
        self.backups = Path(tmp) / "backups"
        self.ui = NullUiPort(confirm_default=True)
        self.bridge = bridge

        def t(key, **kw):
            return key + ("|" + ",".join(f"{k}={v}"
                                         for k, v in sorted(kw.items()))
                          if kw else "")

        self.slots = SlotStore(self.library, t, 10)
        self.editor = EditorController(
            ui=self.ui, slots=self.slots, t=t, cfg=None,
            backup_dir=self.backups, save_library=self.library,
            max_save_size=1024 * 1024,
            get_bridge=lambda: self.bridge,
            is_server_running=lambda: server,
            ensure_bridge_client=lambda timeout: bool(
                self.bridge and self.bridge.has_client))

    def write_slot(self, index, obj):
        blob = savecodec.compress_base64(
            json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
        self.slots.write(index, blob, 1024 * 1024)
        return blob

    def messages(self, kind):
        return [m for m in self.ui.messages if m[0] == kind]


class TestDecode(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(decode_to_obj(json.dumps(SAVE))["saveVersion"], 2)

    def test_lz_base64(self):
        blob = savecodec.compress_base64(json.dumps(SAVE))
        self.assertEqual(decode_to_obj(blob)["buildings"][0]["name"], "hut")

    def test_garbage_and_empty(self):
        for text in ("", "   ", "not a save", "{}x"):
            self.assertIsNone(decode_to_obj(text), text)

    def test_json_helpers(self):
        self.assertEqual(json_compact({"a": 1, "b": [2]}), '{"a":1,"b":[2]}')
        self.assertEqual(json_pretty({"a": 1}), '{\n  "a": 1\n}')


class TestOpen(unittest.TestCase):
    def test_open_file_creates_backup(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.write_slot(1, SAVE)
            self.assertTrue(h.editor.open_file(1))
            self.assertEqual(h.editor.slot, 1)
            self.assertEqual(h.editor.data["saveVersion"], 2)
            backups = list(h.backups.glob("*.bak"))
            self.assertEqual(len(backups), 1, "打开前应生成一份备份")
            self.assertTrue(any("ed.loaded" in m for _t, m in h.ui.logs))

    def test_open_missing_slot_warns(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertFalse(h.editor.open_file(0))
            self.assertEqual(h.messages("warn")[0][2], "ed.no_slot")

    def test_open_broken_file_reports(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            (h.library / "坏_1.kgsav").write_text("###", encoding="utf-8")
            h.slots.refresh()
            self.assertFalse(h.editor.open_file(0))
            self.assertTrue(h.messages("fail"))

    def test_open_live_requires_bridge(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, bridge=None)
            self.assertFalse(h.editor.open_live())
            self.assertEqual(h.messages("warn")[0][2], "ed.no_bridge")

    def test_open_live_pulls_from_page(self):
        blob = savecodec.compress_base64(json.dumps(SAVE))
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, bridge=FakeBridge(blob))
            self.assertTrue(h.editor.open_live())
            self.assertEqual(h.editor.slot, -1)
            self.assertIsNone(h.editor.path)
            self.assertTrue(any("ed.pulled" in m for _t, m in h.ui.logs))

    def test_open_live_without_client_fails(self):
        blob = savecodec.compress_base64(json.dumps(SAVE))
        with TemporaryDirectory() as tmp:
            h = Harness(tmp, bridge=FakeBridge(blob, has_client=False))
            self.assertFalse(h.editor.open_live())
            self.assertEqual(h.messages("warn")[0][2], "ed.no_bridge")


class TestTree(unittest.TestCase):
    def _opened(self, tmp):
        h = Harness(tmp)
        h.write_slot(0, SAVE)
        h.editor.open_file(0)
        return h

    def test_rows_shape(self):
        with TemporaryDirectory() as tmp:
            h = self._opened(tmp)
            rows = h.editor.tree_rows()
            self.assertEqual(rows[0]["kind"], "root")
            kinds = {r["kind"] for r in rows}
            self.assertIn("object", kinds)
            self.assertIn("leaf", kinds)
            # 数组元素标签带下标与首键
            labels = [r["label"] for r in rows]
            self.assertTrue(any(l.startswith("0 · name: hut") for l in labels))
            self.assertTrue(any(l.startswith("1 · 7") for l in labels))
            # 每条非根行都有父节点
            for row in rows[1:]:
                self.assertIsNotNone(row["parent"])
            ids = {r["id"] for r in rows}
            for row in rows[1:]:
                self.assertIn(row["parent"], ids)

    def test_empty_data_has_no_rows(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertEqual(h.editor.tree_rows(), [])

    def test_value_at_and_set_value(self):
        with TemporaryDirectory() as tmp:
            h = self._opened(tmp)
            self.assertEqual(h.editor.value_at(["resources", "catnip",
                                                "value"]), "12.5")
            self.assertTrue(h.editor.set_value(["resources", "catnip",
                                                "value"], "99"))
            self.assertEqual(h.editor.data["resources"]["catnip"]["value"], 99)
            # 不能解析为 JSON 时按字符串写入
            self.assertTrue(h.editor.set_value(["saveVersion"], "abc"))
            self.assertEqual(h.editor.data["saveVersion"], "abc")
            # JSON 字面量按类型写入
            self.assertTrue(h.editor.set_value(["buildings", 1], "true"))
            self.assertIs(h.editor.data["buildings"][1], True)

    def test_set_value_rejects_empty_path(self):
        with TemporaryDirectory() as tmp:
            h = self._opened(tmp)
            self.assertFalse(h.editor.set_value([], "1"))


class TestWrite(unittest.TestCase):
    def test_write_file_is_decodable_and_atomic(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.write_slot(3, {"a": 1})
            h.editor.open_file(3)
            h.editor.set_value(["a"], "5")
            self.assertTrue(h.editor.write())
            blob = h.slots.path(3).read_text(encoding="utf-8")
            self.assertEqual(decode_to_obj(blob)["a"], 5)
            self.assertEqual([p.name for p in h.library.iterdir() if
                              p.name.startswith(".")], [],
                             "不应残留临时文件")
            self.assertTrue(any(t == "slots_changed" for t, _ in h.ui.logs))
            self.assertTrue(any("ed.saved" in m for _t, m in h.ui.logs))

    def test_write_without_data_warns(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertFalse(h.editor.write())
            self.assertEqual(h.messages("warn")[0][2], "ed.no_slot")

    def test_source_text_and_apply(self):
        with TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.write_slot(0, {"a": 1})
            h.editor.open_file(0)
            text = h.editor.source_text()
            self.assertIn('"a": 1', text)
            h.editor.src_touched = True
            broken = h.editor.apply_source_text("{oops")
            self.assertFalse(broken)
            self.assertTrue(h.messages("fail"))
            self.assertTrue(h.editor.apply_source_text('{"a": 2}'))
            self.assertEqual(h.editor.data["a"], 2)

    def test_write_live_sends_to_page(self):
        with TemporaryDirectory() as tmp:
            bridge = FakeBridge(savecodec.compress_base64(
                json.dumps({"a": 1})))
            h = Harness(tmp, bridge=bridge)
            self.assertTrue(h.editor.open_live())
            self.assertTrue(h.editor.write())
            self.assertEqual(len(bridge.applied), 1)
            self.assertEqual(decode_to_obj(bridge.applied[0])["a"], 1)
            self.assertTrue(h.messages("notify"))

    def test_write_live_failure_when_no_client(self):
        with TemporaryDirectory() as tmp:
            bridge = FakeBridge(savecodec.compress_base64(
                json.dumps({"a": 1})), has_client=False)
            h = Harness(tmp, bridge=bridge)
            h.editor.data = {"a": 1}
            h.editor.slot = -1
            h.editor.path = None
            self.assertFalse(h.editor.write())
            self.assertEqual(h.messages("warn")[0][2], "ed.no_bridge")

    def test_write_live_failure_when_apply_rejected(self):
        with TemporaryDirectory() as tmp:
            bridge = FakeBridge(savecodec.compress_base64(
                json.dumps({"a": 1})), apply_ok=False)
            h = Harness(tmp, bridge=bridge)
            h.editor.data = {"a": 1}
            h.editor.slot = -1
            h.editor.path = None
            self.assertFalse(h.editor.write())
            self.assertTrue(any(t == "tag.error" for t, _ in h.ui.logs))


if __name__ == "__main__":
    unittest.main()
