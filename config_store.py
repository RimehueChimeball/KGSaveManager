"""
配置存储：kgsm_data/kgsm_config.json

字段（全部在「配置」页修改并自动保存）：
- language : zh | en（无配置文件时按系统语言探测）
- game_dir : 游戏目录（同时是 Web 服务根目录），默认空
- port     : 固定端口字符串，空 = 自动选择
- home_slot: 首页指定存档位索引（0-based），默认 0
- notes    : {str(i): 备注文本}，向后兼容旧版纯备注结构
"""

import json
import threading
from pathlib import Path

from i18n import LANG_ZH, detect_system_language

SLOT_COUNT = 6  # 与主程序一致；独立常驻避免循环导入


class AppConfig:
    def __init__(self, path):
        self.path = Path(path)
        self.language = LANG_ZH
        self.game_dir = ""
        self.port = ""
        self.home_slot = 0
        self.notes = {}
        self._lock = threading.Lock()
        self._loaded_from_disk = False
        self._load()

    # ---------------- 读写 ----------------
    def _load(self):
        data = {}
        try:
            if self.path.exists():
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
            if legacy:
                self._loaded_from_disk = True

        # 统一落盘：首启写入（含探测语言）；旧结构/缺字段时自动迁移为新结构
        self.save()

    def save(self):
        """原子写入（先写临时文件再替换）。"""
        payload = {
            "language": self.language,
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
