"""downloader 纯逻辑测试（不访问网络）。"""

import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import downloader  # noqa: E402


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


class TestMirrors(unittest.TestCase):
    def test_mirror_value_matches_key_domain(self):
        """镜像键名必须就是它自己的域名（防止旧域名错配）。"""
        for name, prefix in downloader.MIRRORS.items():
            if not prefix:
                self.assertEqual(name, "github.com")
                continue
            self.assertTrue(prefix.endswith("/"),
                            f"{name} 的前缀必须以 / 结尾")
            self.assertIn(name, prefix, f"{name} 与其域名不匹配: {prefix}")

    def test_make_url(self):
        full = "https://github.com/a/b/archive/refs/heads/master.zip"
        self.assertEqual(downloader.make_url("", full), full)
        self.assertEqual(downloader.make_url("https://ghfast.top/", full),
                         "https://ghfast.top/" + full)

    def test_zip_url(self):
        self.assertEqual(
            downloader.zip_url("nuclear-unicorn", "kittensgame",
                               "refs/heads/master"),
            "https://github.com/nuclear-unicorn/kittensgame/archive/"
            "refs/heads/master.zip")


class TestFlattenExtract(unittest.TestCase):
    def test_flattens_single_top_level_dir(self):
        with TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "game.zip"
            target = Path(tmp) / "out"
            target.mkdir()
            make_zip(zpath, {
                "kittensgame-master/index.html": "<html>",
                "kittensgame-master/js/game.js": "// js",
                "kittensgame-master/css/style.css": "body{}",
            })
            downloader._flatten_extract(str(zpath), str(target))
            self.assertTrue((target / "index.html").is_file())
            self.assertTrue((target / "js" / "game.js").is_file())
            self.assertTrue((target / "css" / "style.css").is_file())
            self.assertFalse((target / "kittensgame-master").exists())

    def test_keeps_structure_without_single_top_dir(self):
        with TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "multi.zip"
            target = Path(tmp) / "out"
            target.mkdir()
            make_zip(zpath, {"a/index.html": "1", "b/other.txt": "2"})
            downloader._flatten_extract(str(zpath), str(target))
            self.assertTrue((target / "a" / "index.html").is_file())
            self.assertTrue((target / "b" / "other.txt").is_file())

    def test_keeps_flat_zip_untouched(self):
        with TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "flat.zip"
            target = Path(tmp) / "out"
            target.mkdir()
            make_zip(zpath, {"index.html": "1", "game.js": "2"})
            downloader._flatten_extract(str(zpath), str(target))
            self.assertTrue((target / "index.html").is_file())
            self.assertTrue((target / "game.js").is_file())

    def test_empty_zip_raises(self):
        with TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "empty.zip"
            target = Path(tmp) / "out"
            target.mkdir()
            with zipfile.ZipFile(zpath, "w"):
                pass
            with self.assertRaises(downloader.DownloadError):
                downloader._flatten_extract(str(zpath), str(target))


class TestInstallGame(unittest.TestCase):
    def test_install_from_local_zip_payload(self):
        """用本地 zip 冒充下载结果，验证解压+摊平+index.html 校验+清临时目录。"""
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "KittensGame"
            target.mkdir()
            zpath = Path(tmp) / "src.zip"
            make_zip(zpath, {
                "kittensgame-master/index.html": "<html>",
                "kittensgame-master/js/game.js": "// js",
            })

            orig = downloader.download_to

            def fake_download(url, dest_path, progress=None, cancel=None,
                              timeout=60):
                Path(dest_path).write_bytes(zpath.read_bytes())

            downloader.download_to = fake_download
            try:
                out = downloader.install_game(
                    "author", "github.com", "refs/heads/master", str(target))
            finally:
                downloader.download_to = orig
            self.assertEqual(Path(out), target)
            self.assertTrue((target / "index.html").is_file())
            self.assertFalse((target / ".temp").exists())

    def test_install_without_index_html_raises(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "KittensGame"
            target.mkdir()
            zpath = Path(tmp) / "src.zip"
            make_zip(zpath, {"kittensgame-master/readme.txt": "x"})

            orig = downloader.download_to

            def fake_download(url, dest_path, progress=None, cancel=None,
                              timeout=60):
                Path(dest_path).write_bytes(zpath.read_bytes())

            downloader.download_to = fake_download
            try:
                with self.assertRaises(downloader.DownloadError):
                    downloader.install_game(
                        "author", "github.com", "refs/heads/master",
                        str(target))
            finally:
                downloader.download_to = orig


class TestListVersionsParsing(unittest.TestCase):
    def test_list_versions_without_network_fails_soft(self):
        """网络不可用时也必须返回默认分支一项，不抛异常。"""
        orig = downloader._http_json

        def boom(*a, **kw):
            raise OSError("offline")

        downloader._http_json = boom
        try:
            items = downloader.list_versions("nuclear-unicorn", "kittensgame")
        finally:
            downloader._http_json = orig
        self.assertEqual(len(items), 1)
        kind, label, ref = items[0]
        self.assertEqual(kind, "branch")
        self.assertEqual(ref, f"refs/heads/{label}")


if __name__ == "__main__":
    unittest.main()
