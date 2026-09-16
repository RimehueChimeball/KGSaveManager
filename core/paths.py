"""程序目录与数据目录的统一解析（源码运行与 PyInstaller 冻结都适用）。

备份/迁移只需移动 `kgsm_data/` 一个目录。
"""

import sys
from pathlib import Path

ICON_FILE = "KGSaveManager.ico"


class AppPaths:
    """一次运行用到的全部路径。"""

    def __init__(self, base_dir=None):
        self.base = Path(base_dir) if base_dir else default_base_dir()
        # 资源目录：冻结后 datas（docs/图标）随包放在 _MEIPASS 下
        self.resources = Path(getattr(sys, "_MEIPASS", self.base))
        self.data = self.base / "kgsm_data"
        self.saves = self.data / "kittens_saves"
        self.temp = self.data / "kgsm_temp"
        self.backups = self.data / "backups"
        self.logs = self.data / "kgsm_log"
        self.config = self.data / "kgsm_config.json"
        self.i18n = self.base / "i18n"
        self.docs = self.base / "docs"
        self.assets = self.base / "webapp" / "assets"
        self.icon = self._find_icon()

    def _find_icon(self):
        """窗口图标文件（找不到返回 None，调用方自行跳过）。

        冻结后 icon 随 datas 放在 `_MEIPASS`；源码运行时在程序目录或 assets/。
        """
        for folder in (self.resources, self.base, self.base / "assets"):
            candidate = Path(folder) / ICON_FILE
            if candidate.is_file():
                return candidate
        return None

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
