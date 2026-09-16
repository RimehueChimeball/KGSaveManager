"""文档一致性测试：离线指南锚点、版本号、README 与前端资源引用。"""

import re
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.app import APP_VERSION  # noqa: E402

GUIDE = ROOT / "docs" / "guide_en.html"
ASSETS = ROOT / "webapp" / "assets"


class TestGuide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = GUIDE.read_text(encoding="utf-8")
        cls.nav = set(re.findall(r'href="#([a-z0-9-]+)"', cls.html))
        cls.anchors = set(re.findall(r'id="([a-z0-9-]+)"', cls.html))

    def test_nav_links_resolve(self):
        missing = sorted(self.nav - self.anchors)
        self.assertEqual(missing, [], f"指南导航指向了不存在的锚点: {missing}")

    def test_version_is_current(self):
        self.assertIn(f"Version: {APP_VERSION}", self.html)

    def test_mentions_both_frontends(self):
        self.assertIn("KGSaveManager.py", self.html)
        self.assertIn("KGSaveManagerLite.py", self.html)


class TestReadme(unittest.TestCase):
    def test_readme_files_exist(self):
        self.assertTrue((ROOT / "README.md").is_file())
        self.assertTrue((ROOT / "README_zh.md").is_file())

    def test_readme_mentions_both_entries(self):
        for name in ("README.md", "README_zh.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("KGSaveManager.py", text)
            self.assertIn("KGSaveManagerLite.py", text)

    def test_readme_lists_current_modules(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for marker in ("core/", "webapp/", "ui_tk.py", "tests/"):
            self.assertIn(marker, text, f"README 缺少 {marker}")


class TestFrontendAssets(unittest.TestCase):
    def test_assets_exist(self):
        for name in ("index.html", "app.js", "style.css", "selftest.js",
                     "favicon.ico", "icon-192.png", "manifest.webmanifest"):
            self.assertTrue((ASSETS / name).is_file(), f"缺少前端资源 {name}")

    def test_favicon_is_valid_ico(self):
        raw = (ASSETS / "favicon.ico").read_bytes()
        self.assertTrue(raw.startswith(b"\x00\x00\x01\x00"), "不是合法 ICO")
        count = int.from_bytes(raw[4:6], "little")
        self.assertGreaterEqual(count, 2, "ICO 至少应含两个尺寸")

    def test_icon_sources(self):
        """程序图标：exe 用 assets 下的 ico，网页用同一份 ico + 转换出的 PNG。

        转换脚本留在仓库里（纯标准库），换图标后重跑即可。
        """
        ico = ROOT / "assets" / "KGSaveManager.ico"
        self.assertTrue(ico.is_file(), "缺少程序图标 assets/KGSaveManager.ico")
        self.assertEqual(ico.read_bytes()[:4], b"\x00\x00\x01\x00",
                         "assets 下的图标不是合法 ICO")
        self.assertEqual((ASSETS / "favicon.ico").read_bytes(), ico.read_bytes(),
                         "网页 favicon 应与程序图标一致")
        converter = ROOT / "tools" / "ico_to_png.py"
        self.assertTrue(converter.is_file(), "缺少 ICO→PNG 转换脚本")
        text = converter.read_text(encoding="utf-8")
        self.assertIn("zlib", text)
        self.assertNotIn("PIL", text)

    def test_ico_converter_roundtrip(self):
        """转换脚本能真的把仓库里的图标转成 PNG。"""
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "icon.png"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "ico_to_png.py"),
                 str(ROOT / "assets" / "KGSaveManager.ico"), str(out), "64"],
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(out.is_file())
            raw = out.read_bytes()
        self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", raw[16:24]), (64, 64))

    def test_manifest_matches_app_name(self):
        import json
        manifest = json.loads((ASSETS / "manifest.webmanifest").read_text(
            encoding="utf-8"))
        self.assertEqual(manifest["short_name"], "KGSaveManager")
        self.assertEqual(manifest["display"], "standalone")
        self.assertTrue(manifest["icons"])

    def test_index_references_assets(self):
        html = (ASSETS / "index.html").read_text(encoding="utf-8")
        for marker in ("/assets/app.js", "/assets/style.css",
                       "/assets/favicon.ico", "/assets/manifest.webmanifest",
                       "selftest.js"):
            self.assertIn(marker, html)

    def test_no_absolute_local_paths_in_assets(self):
        """前端资源里不应写死盘符路径（换机器就失效）。"""
        import re as _re
        for name in ("app.js", "style.css", "index.html", "selftest.js"):
            text = (ASSETS / name).read_text(encoding="utf-8")
            self.assertIsNone(_re.search(r"[A-Za-z]:\\\\", text),
                              f"{name} 里出现了写死的盘符路径")


if __name__ == "__main__":
    unittest.main()
