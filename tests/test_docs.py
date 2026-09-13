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
        for name in ("index.html", "app.js", "style.css", "selftest.js"):
            self.assertTrue((ASSETS / name).is_file(), f"缺少前端资源 {name}")

    def test_index_references_assets(self):
        html = (ASSETS / "index.html").read_text(encoding="utf-8")
        self.assertIn("/assets/app.js", html)
        self.assertIn("/assets/style.css", html)
        self.assertIn("selftest.js", html)

    def test_no_absolute_local_paths_in_assets(self):
        """前端资源里不应写死盘符路径（换机器就失效）。"""
        import re as _re
        for name in ("app.js", "style.css", "index.html", "selftest.js"):
            text = (ASSETS / name).read_text(encoding="utf-8")
            self.assertIsNone(_re.search(r"[A-Za-z]:\\\\", text),
                              f"{name} 里出现了写死的盘符路径")


if __name__ == "__main__":
    unittest.main()
