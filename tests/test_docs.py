"""文档一致性测试：离线指南锚点、版本号、README 与前端资源引用。"""

import re
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

    def test_icon_generator_exists(self):
        """图标可复现：生成脚本留在仓库里，且只用标准库。"""
        script = ROOT / "tools" / "make_favicon.py"
        self.assertTrue(script.is_file())
        text = script.read_text(encoding="utf-8")
        self.assertIn("zlib", text)
        self.assertNotIn("PIL", text)

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
