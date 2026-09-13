"""i18n 完整性测试：中英对齐、无失效键、占位符一致。"""

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import i18n  # noqa: E402

# 通过变量/拼接使用的键（无法用正则静态识别）
DYNAMIC_KEYS = {
    "tab.kgsm", "tab.game", "tab.saves", "tab.editor", "tab.download",
    "tab.settings",
    "kgsm.step_doc", "kgsm.step_dl", "kgsm.step_cfg", "kgsm.step_run",
    "msg.paste_invalid_file",
}
# 允许存在但当前不由代码直接引用的键（保留给外部/未来用）
ALLOWED_UNUSED = set()

PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def py_files():
    """参与扫描的源码：仓库根目录与 core/ 逻辑层（翻译键在两处都会用到）。"""
    return sorted(list(ROOT.glob("*.py")) + list(ROOT.glob("core/*.py")))


def repo_text():
    return "\n".join(p.read_text(encoding="utf-8") for p in py_files())


class TestI18nTables(unittest.TestCase):
    def test_languages_aligned(self):
        self.assertEqual(sorted(i18n._ZH), sorted(i18n._EN),
                         "中英键集合不一致")

    def test_placeholders_match(self):
        for key, zh in i18n._ZH.items():
            en = i18n._EN[key]
            self.assertEqual(sorted(set(PLACEHOLDER.findall(zh))),
                             sorted(set(PLACEHOLDER.findall(en))),
                             f"{key} 的中英占位符不一致")

    def test_no_unused_keys(self):
        text = repo_text()
        used = set(re.findall(r'\.t\(\s*["\']([^"\']+)["\']', text))
        used |= DYNAMIC_KEYS
        unused = sorted(set(i18n._ZH) - used - ALLOWED_UNUSED)
        self.assertEqual(unused, [], f"存在无引用的翻译键: {unused}")

    def test_all_referenced_keys_defined(self):
        text = repo_text()
        used = set(re.findall(r'\.t\(\s*["\']([^"\']+)["\']', text))
        used |= DYNAMIC_KEYS
        missing = sorted(used - set(i18n._ZH))
        self.assertEqual(missing, [], f"代码引用了缺失的翻译键: {missing}")

    def test_keys_are_prefixed(self):
        for key in i18n._ZH:
            self.assertRegex(key, r"^[a-z]+\.[a-z0-9_]+$",
                             f"键名不符合 <前缀>.<名字> 约定: {key}")

    def test_translator_falls_back_to_key(self):
        tr = i18n.Translator("en")
        self.assertEqual(tr.t("no.such.key"), "no.such.key")


class TestI18nSources(unittest.TestCase):
    def test_zh_en_dicts_are_module_level_literals(self):
        """防止把翻译表写成无法被本测试解析的形式。"""
        tree = ast.parse((ROOT / "i18n.py").read_text(encoding="utf-8"))
        names = set()
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
        self.assertIn("_ZH", names)
        self.assertIn("_EN", names)


if __name__ == "__main__":
    unittest.main()
