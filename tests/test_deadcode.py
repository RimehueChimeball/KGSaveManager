"""死代码防护测试：未使用的导入、无人引用的函数/方法。

这是审计里「遗留死代码」一类的回归网：新增功能若留下没有调用方的
函数或导入，测试会直接失败。
"""

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 有意保留的覆写点/框架钩子（由基类或框架按名字调用）
ALLOWED_UNCALLED = {
    "log_message",      # BaseHTTPRequestHandler 覆写：用于屏蔽默认日志
    "_open",            # AppLogger 内部在 __init__ 里调用（同名系统函数干扰）
}


def py_files():
    """参与检查的源码：仓库根目录与 core/ 逻辑层（不含 tests/ 自身）。"""
    return sorted(list(ROOT.glob("*.py")) + list(ROOT.glob("core/*.py")))


def strip_imports(tree, src):
    lines = src.splitlines()
    kill = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                kill.add(ln)
    return "\n".join(l for i, l in enumerate(lines, 1) if i not in kill)


class TestNoDeadCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = py_files()
        cls.all_text = "\n".join(p.read_text(encoding="utf-8")
                                 for p in cls.files)

    def test_no_unused_imports(self):
        problems = []
        for path in self.files:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            body = strip_imports(tree, src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname or alias.name.split(".")[0]
                        if not re.search(r"\b%s\b" % re.escape(name), body):
                            problems.append(f"{path.name}:{node.lineno}: {name}")
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        name = alias.asname or alias.name
                        if name == "*":
                            continue
                        if not re.search(r"\b%s\b" % re.escape(name), body):
                            problems.append(f"{path.name}:{node.lineno}: {name}")
        self.assertEqual(problems, [], "存在未使用的导入: " + ", ".join(problems))

    def test_no_uncalled_functions(self):
        problems = []
        for path in self.files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            definitions = []
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                    definitions.append((node.name, node.lineno))
                    if isinstance(node, ast.ClassDef):
                        for sub in node.body:
                            if isinstance(sub, (ast.FunctionDef,
                                                ast.AsyncFunctionDef)):
                                definitions.append((sub.name, sub.lineno))
            for name, lineno in definitions:
                if name.startswith("__") and name.endswith("__"):
                    continue
                if name in ALLOWED_UNCALLED:
                    continue
                if len(re.findall(r"\b%s\b" % re.escape(name),
                                  self.all_text)) <= 1:
                    problems.append(f"{path.name}:{lineno}: {name}")
        self.assertEqual(problems, [],
                         "存在没有任何调用方的函数/方法: " + ", ".join(problems))


if __name__ == "__main__":
    unittest.main()
