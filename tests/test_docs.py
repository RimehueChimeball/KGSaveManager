"""文档一致性测试：离线指南锚点、版本号、README 与前端资源引用。"""

import re
import struct
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.app import APP_VERSION  # noqa: E402

GUIDE = ROOT / "docs" / "guide_en.html"
GUIDE_ZH = ROOT / "docs" / "guide_zh.html"
CHANGELOG = ROOT / "CHANGELOG.md"
CHANGELOG_ZH = ROOT / "CHANGELOG_zh.md"
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
        self.assertIn("KGSaveManagerTk.py", self.html)

    def test_chinese_guide_mirrors_structure(self):
        """中文指南必须存在，锚点与英文版一一对应，且带上当前版本号。"""
        self.assertTrue(GUIDE_ZH.is_file(), "缺少中文指南 docs/guide_zh.html")
        zh = GUIDE_ZH.read_text(encoding="utf-8")
        self.assertIn(f"版本：{APP_VERSION}", zh)
        zh_nav = set(re.findall(r'href="#([a-z0-9-]+)"', zh))
        zh_anchors = set(re.findall(r'id="([a-z0-9-]+)"', zh))
        self.assertEqual(sorted(zh_nav - zh_anchors), [],
                         "中文指南导航指向了不存在的锚点")
        self.assertEqual(sorted(zh_anchors - self.anchors), [],
                         "中文指南出现了英文版没有的锚点（结构不对应）")
        self.assertEqual(sorted(self.anchors - zh_anchors), [],
                         "中文指南缺少英文版里的锚点（结构不对应）")
        self.assertIn("KGSaveManager.py", zh)
        self.assertIn("KGSaveManagerTk.py", zh)

    def test_chinese_changelog_exists(self):
        self.assertTrue(CHANGELOG_ZH.is_file(), "缺少中文更新日志 CHANGELOG_zh.md")
        zh = CHANGELOG_ZH.read_text(encoding="utf-8")
        en = CHANGELOG.read_text(encoding="utf-8")
        # 两份文件的版本段必须一一对应（任一方向缺少都算错）
        self.assertEqual(re.findall(r"^## (v[0-9.]+)", en, re.M),
                         re.findall(r"^## (v[0-9.]+)", zh, re.M),
                         "中英更新日志的版本段不一致")

    def test_changelog_covers_every_released_version(self):
        """已发布的版本都要有自己的段落，且按版本号降序排列。

        v1.2.3 / v1.2.4 发布时只在 release/1.2.x 分支上写了段落，main 的更新
        日志里只有一句「移植了这两个版本的修复」，读更新日志的人根本看不到
        这两个版本。现在用测试把这件事钉住。
        """
        en = CHANGELOG.read_text(encoding="utf-8")
        versions = re.findall(r"^## (v[0-9.]+)", en, re.M)
        self.assertIn(APP_VERSION, versions, "缺少当前版本的段落")
        for released in ("v1.2.3", "v1.2.4"):
            self.assertIn(released, versions, f"更新日志缺少已发布的 {released}")
        keys = [tuple(int(p) for p in v.lstrip("v").split("."))
                for v in versions]
        self.assertEqual(keys, sorted(keys, reverse=True),
                         "版本段没有按降序排列（新段落插错位置）")

    def test_open_doc_targets_exist(self):
        """程序里“离线文档/更新日志”入口指向的文件必须存在。"""
        self.assertTrue(GUIDE.is_file())
        self.assertTrue(GUIDE_ZH.is_file())
        self.assertTrue(CHANGELOG.is_file())
        self.assertTrue(CHANGELOG_ZH.is_file())

    def test_docs_and_assets_resolve_inside_bundle(self):
        """冻结（PyInstaller）后 docs 与 webapp/assets 在 _MEIPASS 下，不是 exe 旁边。

        打包出来的主版本曾经因为这条路径指向 exe 目录而整个页面 404：
        assets 随 datas 打进 `_MEIPASS/webapp/assets`，而 AppPaths 用的是 base。
        """
        import sys
        from core.paths import AppPaths
        with TemporaryDirectory() as tmp:
            meipass = Path(tmp) / "bundle"
            (meipass / "docs").mkdir(parents=True)
            (meipass / "webapp" / "assets").mkdir(parents=True)
            exe_dir = Path(tmp) / "app"
            exe_dir.mkdir()
            original = getattr(sys, "_MEIPASS", None)
            sys._MEIPASS = str(meipass)
            try:
                paths = AppPaths(exe_dir)
                self.assertEqual(paths.assets, meipass / "webapp" / "assets")
                self.assertEqual(paths.docs, meipass / "docs")
                self.assertTrue(paths.assets.is_dir())
                # 数据目录仍然在 exe 旁边（便携）
                self.assertEqual(paths.data, exe_dir / "kgsm_data")
            finally:
                if original is None:
                    del sys._MEIPASS
                else:
                    sys._MEIPASS = original

    def test_localized_doc_follows_language(self):
        """按语言挑文档：zh 取中文版，其余取英文版；外部 i18n/ 同名文件优先。"""
        from core.paths import AppPaths
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "docs").mkdir()
            (base / "docs" / "guide_zh.html").write_text("zh", encoding="utf-8")
            (base / "docs" / "guide_en.html").write_text("en", encoding="utf-8")
            (base / "docs" / "guide_fr.html").write_text("fr", encoding="utf-8")
            (base / "CHANGELOG.md").write_text("en", encoding="utf-8")
            paths = AppPaths(base)
            self.assertEqual(paths.localized_doc("guide", "zh").name,
                             "guide_zh.html")
            self.assertEqual(paths.localized_doc("guide", "en").name,
                             "guide_en.html")
            # 未知语言退回英文版（不会挑到 fr）
            self.assertEqual(paths.localized_doc("guide", "fr").name,
                             "guide_en.html")
            self.assertEqual(paths.localized_doc("changelog", "zh").name,
                             "CHANGELOG.md", "只有英文版时退回英文版")
            self.assertIsNone(paths.localized_doc("nope", "zh"))
            # 外部 i18n/ 里的同名文件优先
            (base / "i18n").mkdir()
            (base / "i18n" / "guide_zh.html").write_text("custom",
                                                         encoding="utf-8")
            (base / "i18n" / "CHANGELOG_zh.md").write_text("custom",
                                                           encoding="utf-8")
            self.assertEqual(paths.localized_doc("guide", "zh"),
                             base / "i18n" / "guide_zh.html")
            self.assertEqual(paths.localized_doc("changelog", "zh"),
                             base / "i18n" / "CHANGELOG_zh.md")

    def test_repo_docs_resolve_by_language(self):
        from core.paths import AppPaths
        paths = AppPaths(ROOT)
        self.assertEqual(paths.localized_doc("guide", "zh").name,
                         "guide_zh.html")
        self.assertEqual(paths.localized_doc("guide", "en").name,
                         "guide_en.html")
        self.assertEqual(paths.localized_doc("changelog", "zh").name,
                         "CHANGELOG_zh.md")
        self.assertEqual(paths.localized_doc("changelog", "en").name,
                         "CHANGELOG.md")


class TestReadme(unittest.TestCase):
    def test_readme_files_exist(self):
        self.assertTrue((ROOT / "README.md").is_file())
        self.assertTrue((ROOT / "README_zh.md").is_file())

    def test_readme_mentions_both_entries(self):
        for name in ("README.md", "README_zh.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("KGSaveManager.py", text)
            self.assertIn("KGSaveManagerTk.py", text)

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
