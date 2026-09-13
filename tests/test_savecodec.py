"""savecodec 编解码往返与校验测试。"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import savecodec  # noqa: E402


SAMPLE = {
    "saveVersion": 2,
    "resources": {"catnip": {"value": 1234.5, "maxValue": 5000}},
    "buildings": [{"name": "hut", "val": 3}, {"name": "field", "val": 7}],
    "中文键": "中文值",
}


class TestSaveCodec(unittest.TestCase):
    def test_base64_roundtrip(self):
        text = json.dumps(SAMPLE, ensure_ascii=False)
        blob = savecodec.compress_base64(text)
        self.assertNotEqual(blob, text)
        self.assertEqual(savecodec.decompress_base64(blob), text)

    def test_roundtrip_on_large_repetitive_payload(self):
        text = json.dumps(
            {"k%d" % i: ("x" * (i % 17)) + str(i * 977) for i in range(400)},
            ensure_ascii=False)
        self.assertEqual(
            savecodec.decompress_base64(savecodec.compress_base64(text)), text)

    def test_roundtrip_on_empty_string(self):
        blob = savecodec.compress_base64("")
        self.assertEqual(savecodec.decompress_base64(blob), "")

    def test_roundtrip_on_unicode_and_control_chars(self):
        text = json.dumps({"s": "🐱\t\n\"quote\"\\slash 中文"}, ensure_ascii=False)
        blob = savecodec.compress_base64(text)
        self.assertEqual(savecodec.decompress_base64(blob), text)

    def test_validate_kinds(self):
        payload = json.dumps(SAMPLE, ensure_ascii=False)
        self.assertEqual(savecodec.validate(payload), (True, "json"))
        self.assertEqual(savecodec.validate(savecodec.compress_base64(payload)),
                         (True, "base64"))

    def test_validate_rejects_garbage(self):
        self.assertEqual(savecodec.validate(""), (False, None))
        self.assertEqual(savecodec.validate("   "), (False, None))
        self.assertEqual(savecodec.validate("not a save at all"), (False, None))
        # 能解压但不是 JSON 对象的内容同样视为不合法
        self.assertEqual(savecodec.validate(
            savecodec.compress_base64("plain text")), (False, None))

    def test_decompress_rejects_broken_input(self):
        self.assertIsNone(savecodec.decompress_base64(""))
        self.assertIsNone(savecodec.decompress_utf16(""))


if __name__ == "__main__":
    unittest.main()
