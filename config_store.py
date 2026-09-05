"""
配置存储：kgsm_data/kgsm_config.json

字段（全部在「配置」页修改并自动保存）：
- language : zh | en（无配置文件时按系统语言探测）
- browser  : 浏览器 exe 路径；首次初始化配置时自动检测系统默认浏览器写入；
             空串 = 使用系统默认。游戏启动与超链接都使用此浏览器。
- game_dir : 游戏目录（同时是 Web 服务根目录），默认空
- port     : 固定端口字符串，空 = 自动选择
- home_slot: 首页指定存档位索引（0-based），默认 0
- notes    : {str(i): 备注文本}，向后兼容旧版纯备注结构
"""

import json
import os
import sys
import threading
from pathlib import Path

from i18n import LANG_ZH, detect_system_language

SLOT_COUNT = 6  # 与主程序一致；独立常驻避免循环导入

# 常见浏览器候选（用于检测失败时的回退与启动兜底）
_BROWSER_CANDIDATES = [
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
    r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
]


def _expand(path):
    return os.path.expandvars(os.path.expanduser(path))


def detect_browser_path():
    """自动检测系统默认浏览器的 exe 路径；检测不到返回空串。

    检测顺序：注册表 .html 用户关联(ProgId) → 常见浏览器候选。
    """
    if sys.platform == "win32":
        try:
            import winreg
            progid = None
            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion"
                    r"\Explorer\FileExts\.html\UserChoice") as key:
                progid, _ = winreg.QueryValueEx(key, "ProgId")
            if progid:
                cmd = None
                try:
                    with winreg.OpenKey(
                            winreg.HKEY_CLASSES_ROOT,
                            progid + r"\shell\open\command") as key:
                        cmd, _ = winreg.QueryValueEx(key, None)
                except OSError:
                    try:
                        with winreg.OpenKey(
                                winreg.HKEY_CLASSES_ROOT, progid) as key:
                            cur, _ = winreg.QueryValueEx(key, "CurVer")
                        with winreg.OpenKey(
                                winreg.HKEY_CLASSES_ROOT,
                                cur + r"\shell\open\command") as key:
                            cmd, _ = winreg.QueryValueEx(key, None)
                    except OSError:
                        pass
                exe = _exe_from_command(cmd or "")
                if exe and os.path.isfile(exe):
                    return exe
        except Exception:
            pass

    # 回退：常见浏览器候选，取第一个存在的
    for cand in _BROWSER_CANDIDATES:
        path = _expand(cand)
        if os.path.isfile(path):
            return path
    return ""


def _exe_from_command(command):
    """从注册表命令串中解析出可执行文件路径，如 '"C:\\x\\chrome.exe" -a %1'。"""
    try:
        import shlex
        parts = shlex.split(command, posix=False)
    except Exception:
        parts = command.replace('"', "").split()
    for part in parts:
        exe = _expand(part.strip('"'))
        if exe.lower().endswith(".exe") and os.path.isfile(exe):
            return exe
    return ""


class AppConfig:
    def __init__(self, path):
        self.path = Path(path)
        self.language = LANG_ZH
        self.browser = ""
        self.game_dir = ""
        self.port = ""
        self.home_slot = 0
        self.notes = {}
        self._lock = threading.Lock()
        self._load()

    # ---------------- 读写 ----------------
    def _load(self):
        data = {}
        existed = self.path.exists()
        try:
            if existed:
                raw = self.path.read_text(encoding="utf-8")
                if raw.strip():
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        data = parsed
        except Exception as e:
            print(f"[config] 读取配置失败（将使用默认值）: {e}")

        # 语言：未配置时按系统语言探测
        lang = data.get("language")
        if isinstance(lang, str) and lang in ("zh", "en"):
            self.language = lang
        else:
            self.language = detect_system_language()

        # 浏览器：初始化配置（首次创建文件）时自动检测写入
        browser = data.get("browser", "")
        if isinstance(browser, str):
            self.browser = browser.strip()
        if not existed:
            self.browser = detect_browser_path()

        self.game_dir = str(data.get("game_dir", "") or "").strip()
        port = data.get("port", "")
        self.port = str(port).strip() if port not in (None, "") else ""

        try:
            self.home_slot = int(data.get("home_slot", 0))
        except (TypeError, ValueError):
            self.home_slot = 0
        self.home_slot = max(0, min(SLOT_COUNT - 1, self.home_slot))

        # 备注：优先取 notes 字段；旧文件（纯 {i: text}）自动迁移
        notes = data.get("notes")
        if isinstance(notes, dict):
            self.notes = notes
        else:
            legacy = {str(k): v for k, v in data.items() if str(k).isdigit()}
            self.notes = legacy

        # 统一落盘：首启写入（含探测语言/浏览器）；旧结构缺字段时自动迁移
        self.save()

    def save(self):
        """原子写入（先写临时文件再替换）。"""
        payload = {
            "language": self.language,
            "browser": self.browser,
            "game_dir": self.game_dir,
            "port": self.port,
            "home_slot": self.home_slot,
            "notes": self.notes,
        }
        tmp = self.path.with_suffix(".json.tmp")
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                tmp.replace(self.path)
            except Exception as e:
                print(f"[config] 保存配置失败: {e}")

    # ---------------- 备注便捷方法 ----------------
    def get_note(self, index):
        return str(self.notes.get(str(index), ""))[:200]

    def set_note(self, index, text):
        key = str(index)
        text = str(text)[:200]
        if self.notes.get(key, "") != text:
            self.notes[key] = text
            self.save()

    def update(self, **kwargs):
        """批量更新合法字段并保存。"""
        changed = False
        if "language" in kwargs and kwargs["language"] in ("zh", "en"):
            if self.language != kwargs["language"]:
                self.language = kwargs["language"]
                changed = True
        if "browser" in kwargs:
            v = str(kwargs["browser"] or "").strip()
            if self.browser != v:
                self.browser = v
                changed = True
        if "game_dir" in kwargs:
            v = str(kwargs["game_dir"] or "").strip()
            if self.game_dir != v:
                self.game_dir = v
                changed = True
        if "port" in kwargs:
            v = str(kwargs["port"] or "").strip()
            if self.port != v:
                self.port = v
                changed = True
        if "home_slot" in kwargs:
            try:
                v = max(0, min(SLOT_COUNT - 1, int(kwargs["home_slot"])))
            except (TypeError, ValueError):
                v = self.home_slot
            if self.home_slot != v:
                self.home_slot = v
                changed = True
        if changed:
            self.save()
