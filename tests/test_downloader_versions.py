"""downloader.list_versions 回归测试：默认分支不能瞎猜。

背景（用户报告的真实故障）：GitHub API 未登录时限流（每 IP 每小时 60 次），
拿不到 default_branch 时代码硬猜 "main"，而作者原版仓库只有 master 分支
→ 四个下载源全部 404；社区版恰好两个分支都有，所以看不出问题。
"""

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import downloader  # noqa: E402


class TestDetectDefaultBranch(unittest.TestCase):
    def setUp(self):
        self.orig_json = downloader._http_json
        self.orig_exists = downloader.branch_exists
        self.orig_cache = dict(downloader._LIST_CACHE)
        downloader._LIST_CACHE.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        downloader._http_json = self.orig_json
        downloader.branch_exists = self.orig_exists
        downloader._LIST_CACHE.clear()
        downloader._LIST_CACHE.update(self.orig_cache)

    def test_uses_api_when_available(self):
        downloader._http_json = lambda url, timeout=20: (
            {"default_branch": "master"} if "releases" not in url else [])
        branch, source = downloader.detect_default_branch("o", "r")
        self.assertEqual((branch, source), ("master", "api"))

    def test_probes_master_when_api_rate_limited(self):
        def boom(url, timeout=20):
            raise OSError("HTTP Error 403: rate limit exceeded")

        downloader._http_json = boom
        # 作者原版：只有 master 存在
        downloader.branch_exists = lambda owner, repo, branch, timeout=8: \
            branch == "master"
        branch, source = downloader.detect_default_branch("o", "r")
        self.assertEqual((branch, source), ("master", "probe"))

    def test_probes_main_when_only_main_exists(self):
        def boom(url, timeout=20):
            raise OSError("offline")

        downloader._http_json = boom
        downloader.branch_exists = lambda owner, repo, branch, timeout=8: \
            branch == "main"
        branch, source = downloader.detect_default_branch("o", "r")
        self.assertEqual((branch, source), ("main", "probe"))

    def test_falls_back_to_master_when_nothing_probes(self):
        def boom(url, timeout=20):
            raise OSError("offline")

        downloader._http_json = boom
        downloader.branch_exists = lambda *a, **k: False
        branch, source = downloader.detect_default_branch("o", "r")
        self.assertEqual((branch, source), ("master", "fallback"))


class TestListVersions(unittest.TestCase):
    def setUp(self):
        self.orig_json = downloader._http_json
        self.orig_exists = downloader.branch_exists
        self.orig_cache = dict(downloader._LIST_CACHE)
        downloader._LIST_CACHE.clear()
        self.calls = []
        self.addCleanup(self._restore)

    def _restore(self):
        downloader._http_json = self.orig_json
        downloader.branch_exists = self.orig_exists
        downloader._LIST_CACHE.clear()
        downloader._LIST_CACHE.update(self.orig_cache)

    def _rate_limited(self):
        def fake(url, timeout=20):
            self.calls.append(url)
            raise OSError("HTTP Error 403: rate limit exceeded")
        downloader._http_json = fake

    def _working_api(self, default="master", releases=None):
        def fake(url, timeout=20):
            self.calls.append(url)
            if "releases" in url:
                return releases or []
            return {"default_branch": default}
        downloader._http_json = fake

    def test_author_repo_lists_master_not_main(self):
        """作者原版只有 master：限流时也必须给出 master。"""
        self._rate_limited()
        downloader.branch_exists = lambda owner, repo, branch, timeout=8: \
            branch == "master"
        notes = []
        items = downloader.list_versions("nuclear-unicorn", "kittensgame",
                                        notes=notes)
        self.assertEqual(items[0], ("branch", "master", "refs/heads/master"))
        self.assertTrue(notes, "限流时应给出一行诊断提示")
        self.assertIn("限流", notes[0])

    def test_community_repo_still_ok(self):
        self._rate_limited()
        downloader.branch_exists = lambda owner, repo, branch, timeout=8: True
        items = downloader.list_versions("kitten-science", "kittensgame")
        self.assertEqual(items[0][1], "master")

    def test_releases_are_appended_when_api_works(self):
        self._working_api(releases=[{"tag_name": "v1.6.1"},
                                    {"tag_name": "v1.5.0"}])
        items = downloader.list_versions("o", "r", refresh=True)
        self.assertEqual(items[1:], [("tag", "v1.6.1", "refs/tags/v1.6.1"),
                                     ("tag", "v1.5.0", "refs/tags/v1.5.0")])

    def test_cache_avoids_repeated_api_calls(self):
        """同一仓库在缓存期内不再请求 API（减少被限流的概率）。"""
        self._working_api()
        downloader.list_versions("o", "r", refresh=True)
        first = len(self.calls)
        downloader.list_versions("o", "r")
        self.assertEqual(len(self.calls), first, "缓存期内不应再次请求")

    def test_refresh_flag_bypasses_cache(self):
        self._working_api()
        downloader.list_versions("o", "r")
        before = len(self.calls)
        downloader.list_versions("o", "r", refresh=True)
        self.assertGreater(len(self.calls), before, "强制刷新应重新请求")

    def test_cache_expiry(self):
        self._working_api()
        downloader.list_versions("o", "r")
        key = ("o", "r")
        stamp, items, source = downloader._LIST_CACHE[key]
        downloader._LIST_CACHE[key] = (
            stamp - downloader.LIST_CACHE_SECONDS - 1, items, source)
        before = len(self.calls)
        downloader.list_versions("o", "r")
        self.assertGreater(len(self.calls), before, "过期后应重新请求")

    def test_note_tells_cache_use(self):
        self._working_api()
        downloader.list_versions("o", "r")
        notes = []
        downloader.list_versions("o", "r", notes=notes)
        self.assertTrue(notes and "缓存" in notes[0], notes)


class TestBranchExists(unittest.TestCase):
    def test_uses_head_request(self):
        seen = {}

        class FakeResp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            seen["method"] = req.get_method()
            seen["url"] = req.full_url
            return FakeResp()

        orig = downloader.urllib.request.urlopen
        downloader.urllib.request.urlopen = fake_urlopen
        try:
            ok = downloader.branch_exists("nuclear-unicorn", "kittensgame",
                                          "master")
        finally:
            downloader.urllib.request.urlopen = orig
        self.assertTrue(ok)
        self.assertEqual(seen["method"], "HEAD")
        self.assertTrue(seen["url"].endswith(
            "/archive/refs/heads/master.zip"))


if __name__ == "__main__":
    unittest.main()
