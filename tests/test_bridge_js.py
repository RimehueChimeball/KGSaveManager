"""注入脚本（web_bridge.bridge_js）行为测试：用 node 跑假浏览器环境。

验证审计里指出的两个时序问题：
1. `<div id="game">` 造成的命名访问假象不得被当成游戏引擎；
2. 引擎在页面 boot 完成后才出现时，hello 要补发、request_save 要等待引擎。

node 不可用时自动跳过。
"""

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web_bridge import bridge_js  # noqa: E402

HARNESS = Path(__file__).resolve().parent / "js" / "bridge_harness.js"


class TestBridgeJs(unittest.TestCase):
    node = shutil.which("node")

    def setUp(self):
        if not self.node:
            self.skipTest("未找到 node")

    def _run(self, save_wait_ms=500, hello_timeout_ms=3000):
        script = bridge_js("ws://127.0.0.1:9/kgsm",
                           save_wait_ms=save_wait_ms,
                           hello_timeout_ms=hello_timeout_ms)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bridge.js"
            path.write_text(script, encoding="utf-8")
            proc = subprocess.run(
                [self.node, str(HARNESS), str(path), str(save_wait_ms),
                 str(hello_timeout_ms)],
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=120)
        return proc

    def test_bridge_js_scenarios(self):
        proc = self._run()
        self.assertTrue(proc.stdout, f"harness 无输出: {proc.stderr}")
        result = json.loads(proc.stdout)
        if proc.returncode != 0:
            self.fail("harness 断言失败:\n" + "\n".join(result["failures"]))
        self.assertTrue(result["ok"])
        self.assertEqual(result["failures"], [])

    def test_defaults_are_interpolated(self):
        """参数插值后 url 与等待参数都应写进脚本。"""
        script = bridge_js("ws://127.0.0.1:1234/kgsm")
        self.assertIn("ws://127.0.0.1:1234/kgsm", script)
        self.assertIn("SAVE_WAIT=5000", script)
        self.assertIn("HELLO_TIMEOUT=120000", script)

    def test_custom_wait_is_interpolated(self):
        script = bridge_js("ws://127.0.0.1:1/", save_wait_ms=1234,
                           hello_timeout_ms=5678)
        self.assertIn("SAVE_WAIT=1234", script)
        self.assertIn("HELLO_TIMEOUT=5678", script)


if __name__ == "__main__":
    unittest.main()
