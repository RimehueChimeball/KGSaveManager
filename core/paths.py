"""程序目录与数据目录的统一解析（源码运行与 PyInstaller 冻结都适用）。

备份/迁移只需移动 `kgsm_data/` 一个目录。
"""

import sys
from pathlib import Path


class AppPaths:
    """一次运行用到的全部路径。"""

    def __init__(self, base_dir=None):
        self.base = Path(base_dir) if base_dir else default_base_dir()
        self.data = self.base / "kgsm_data"
        self.saves = self.data / "kittens_saves"
        self.temp = self.data / "kgsm_temp"
        self.backups = self.data / "backups"
        self.logs = self.data / "kgsm_log"
        self.config = self.data / "kgsm_config.json"
        self.i18n = self.base / "i18n"
        self.docs = self.base / "docs"
        self.assets = self.base / "webapp" / "assets"

    def ensure_dirs(self):
        for folder in (self.data, self.saves, self.temp, self.backups):
            folder.mkdir(parents=True, exist_ok=True)

    def as_dict(self):
        return {
            "base": str(self.base),
            "data": str(self.data),
            "saves": str(self.saves),
            "temp": str(self.temp),
            "backups": str(self.backups),
            "logs": str(self.logs),
            "config": str(self.config),
        }


def default_base_dir():
    """程序目录：冻结后是 exe 所在目录，源码运行是仓库目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
