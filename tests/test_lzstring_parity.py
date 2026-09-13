"""与游戏自带 lib/lz-string.js 的编解码一致性测试（用 node 跑 JS 侧）。

- 找不到 node 或找不到 lz-string.js 时自动跳过；
- 可用环境变量 KGSM_LZ_STRING 指定 lz-string.js 路径，否则按常见位置查找。

这一层是“存档能不能真的被游戏读回”的关键验证：Python 压缩结果必须与
lz-string 的 compressToBase64 完全一致，解压结果也必须一致。
"""

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import savecodec  # noqa: E402

CANDIDATE_GAME_DIRS = [
    Path(os.environ.get("KGSM_GAME_DIR", "")),
    Path(r"D:\Work Directory\Deepseek\project\KGSaveManager\KittensGame"),
    Path(r"D:\Portable Program\KittensGame\v1.6.1.6r3"),
    Path(r"D:\Portable Program\KittensGame\v1.5.0.1r3"),
]

PAYLOADS = [
    json.dumps({"saveVersion": 2, "resources": {"catnip": {"value": 1.5}}},
               ensure_ascii=False),
    json.dumps({"中文键": "中文值", "nested": {"a": [1, 2, 3]}},
               ensure_ascii=False),
    json.dumps({"kitten": "🐱 emoji 存档", "tab": "\t\n\"q\""},
               ensure_ascii=False),
    "x" * 500,
    json.dumps({("k%d" % i): ("y" * (i % 13)) for i in range(200)},
               ensure_ascii=False),
]

JS_DRIVER = """
const fs = require('fs');
const lzPath = process.argv[2];
const payloads = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const src = fs.readFileSync(lzPath, 'utf8');
const sandbox = {module: {exports: {}}, exports: {}};
const fn = new Function('module', 'exports', 'window', src + ';'
  + 'return (typeof LZString!=="undefined"?LZString:'
  + '(module.exports&&(module.exports.LZString||module.exports)));');
const LZ = fn(sandbox.module, sandbox.exports, sandbox);
const out = payloads.map(function (p) {
  const c = LZ.compressToBase64(p);
  return {compressed: c, decompressed: LZ.decompressFromBase64(c)};
});
process.stdout.write(JSON.stringify(out));
"""


def find_lz_string():
    env = os.environ.get("KGSM_LZ_STRING")
    if env and Path(env).is_file():
        return Path(env)
    for base in CANDIDATE_GAME_DIRS:
        if not base or not str(base):
            continue
        candidate = base / "lib" / "lz-string.js"
        if candidate.is_file():
            return candidate
    return None


class TestLzStringParity(unittest.TestCase):
    node = shutil.which("node")
    lz_string = find_lz_string()

    def setUp(self):
        if not self.node:
            self.skipTest("未找到 node")
        if not self.lz_string:
            self.skipTest("未找到 lz-string.js（可用 KGSM_LZ_STRING 指定）")

    def _run_js(self, payloads):
        with TemporaryDirectory() as tmp:
            driver = Path(tmp) / "driver.js"
            data = Path(tmp) / "payloads.json"
            driver.write_text(JS_DRIVER, encoding="utf-8")
            data.write_text(json.dumps(payloads), encoding="utf-8")
            proc = subprocess.run(
                [self.node, str(driver), str(self.lz_string), str(data)],
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=60)
            if proc.returncode != 0 or not proc.stdout:
                self.fail(f"node 执行失败: {proc.stderr.strip()}")
            return json.loads(proc.stdout)

    def test_compress_matches_lz_string(self):
        js = self._run_js(PAYLOADS)
        for payload, item in zip(PAYLOADS, js):
            mine = savecodec.compress_base64(payload)
            self.assertEqual(mine, item["compressed"],
                             f"压缩结果与 lz-string 不一致: {payload[:40]!r}")

    def test_decompress_matches_lz_string(self):
        js = self._run_js(PAYLOADS)
        for payload, item in zip(PAYLOADS, js):
            self.assertEqual(savecodec.decompress_base64(item["compressed"]),
                             payload)
            self.assertEqual(item["decompressed"], payload)

    def test_validate_accepts_real_compressor_output(self):
        js = self._run_js(PAYLOADS[:3])
        for item in js:
            ok, kind = savecodec.validate(item["compressed"])
            if item["compressed"].lstrip().startswith("{"):
                continue
            self.assertTrue(ok, "游戏压缩出的存档应通过校验")
            self.assertEqual(kind, "base64")


if __name__ == "__main__":
    unittest.main()
