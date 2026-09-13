"""HTML 前端的真实浏览器验证：用无头 Edge/Chrome 跑页面自检（?selftest=1）。

找不到浏览器时自动跳过。自检脚本只做只读或可回滚的操作（备注改回原值），
不会写任何存档文件。
"""

import json
import re
import shutil
import subprocess
import sys
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_webapp_api import WebHarness  # noqa: E402

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser():
    for path in BROWSERS:
        if Path(path).is_file():
            return path
    for name in ("msedge", "chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    return None


class TestBrowserSelftest(unittest.TestCase):
    browser = find_browser()

    def setUp(self):
        if not self.browser:
            self.skipTest("未找到 Edge/Chrome，跳过真实浏览器自检")
        self.tmp = TemporaryDirectory()
        self.h = WebHarness(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.h.close)

    def test_page_selftest_passes(self):
        # 自检需要一点真实时间（备注往返、事件轮询）
        proc = subprocess.run(
            [self.browser, "--headless=new", "--disable-gpu", "--no-first-run",
             "--virtual-time-budget=20000", "--dump-dom",
             self.h.url.rstrip("/") + "/?selftest=1"],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=180)
        dom = proc.stdout or ""
        self.assertIn('id="selftest"', dom,
                      f"页面没有输出自检结果；stderr={proc.stderr[:400]}")
        match = re.search(r'<pre id="selftest">(.*?)</pre>', dom, re.S)
        self.assertIsNotNone(match)
        report = match.group(1)
        self.assertNotIn("FAIL", report, "浏览器自检存在失败项:\n" + report)
        self.assertNotIn("ERROR", report, "浏览器自检异常:\n" + report)
        self.assertIn("SELFTEST OK", report, report)

    def test_page_serves_state_to_browser(self):
        """页面加载后应拿到真实数据（不依赖自检脚本）。"""
        proc = subprocess.run(
            [self.browser, "--headless=new", "--disable-gpu", "--no-first-run",
             "--virtual-time-budget=8000", "--dump-dom",
             self.h.url.rstrip("/") + "/"],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=120)
        dom = proc.stdout or ""
        self.assertIn("slot-rows", dom)
        self.assertEqual(dom.count("<tr"), 11, "应有 10 个存档位行 + 表头")
        self.assertIn("data-page=\"saves\"", dom)

    def test_api_reachable_from_python_client(self):
        with urllib.request.urlopen(self.h.url.rstrip("/") + "/api/state",
                                    timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["result"]["slots"]), 10)


if __name__ == "__main__":
    unittest.main()
