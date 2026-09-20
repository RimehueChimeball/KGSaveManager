"""配置存储（config_store.AppConfig）的测试。

只测"读进来是什么、写出去是什么"这类不需要界面的部分：
- 默认值；
- 新字段（启动位置 / 窗口状态）的往返与非法值处理；
- 已删除字段（home_slot）在旧配置文件里出现时不生效、也不再被写回。
"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config_store  # noqa: E402


class TestAppConfig(unittest.TestCase):
    def _load(self, payload):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "kgsm_config.json"
        path.write_text(json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8")
        return config_store.AppConfig(path), path

    def test_defaults(self):
        cfg, path = self._load({})
        self.assertEqual(cfg.launch_mode, "app")
        self.assertTrue(cfg.auto_resume, "自动续玩默认开")
        self.assertEqual(cfg.port, "")
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["launch_mode"], "app")
        self.assertTrue(saved["auto_resume"])

    def test_launch_settings_roundtrip(self):
        cfg, path = self._load({"launch_mode": "tab", "auto_resume": False})
        self.assertEqual(cfg.launch_mode, "tab")
        self.assertFalse(cfg.auto_resume)
        # 只有合法值才写得进配置
        cfg.update(launch_mode="nonsense")
        self.assertEqual(cfg.launch_mode, "tab")
        cfg.update(auto_resume=True)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["launch_mode"], "tab")
        self.assertTrue(saved["auto_resume"])

    def test_removed_window_state_is_ignored(self):
        """已删除的窗口状态（游戏窗口状态）不再被读回或写回。"""
        cfg, path = self._load({"window_state": "full"})
        self.assertFalse(hasattr(cfg, "window_state"))
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("window_state", saved)

    def test_removed_home_slot_is_ignored(self):
        """旧配置里的 home_slot（已删除的「默认存档位」）不再被读回或写回。"""
        cfg, path = self._load({"home_slot": 7, "game_dir": "D:/kg"})
        self.assertFalse(hasattr(cfg, "home_slot"))
        self.assertEqual(cfg.game_dir, str(Path("D:/kg")), "路径会规范化")
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("home_slot", saved)


if __name__ == "__main__":
    unittest.main()
