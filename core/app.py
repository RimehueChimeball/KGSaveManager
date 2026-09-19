"""应用核心：把配置、日志、槽位、存档流程、服务/桥、下载、编辑器组装起来。

两个前端（主版本 HTML 界面 `KGSaveManager.py`、Lite 版 Tkinter 界面 `KGSaveManagerLite.py`）
都只创建一次 `AppCore`，然后把界面端口 `UiPort` 传进来；core 内部不含任何
GUI 代码，也不需要知道自己被哪个前端驱动。
"""

import queue

from config_store import AppConfig
from i18n import Translator, load_external_translations
from kgsm_logging import AppLogger

from .download import DownloadController
from .editor import EditorController
from .flows import SaveFlows
from .paths import AppPaths
from .server import ServerController
from .slots import SlotStore

APP_NAME = "KittensGame Save Manager"
APP_VERSION = "v1.3.0"
SLOT_COUNT = 10
MAX_NOTE_LEN = 200
MAX_SAVE_SIZE = 64 * 1024 * 1024          # 单个存档最大体积（字节）


class AppCore:
    """共享逻辑层的门面。前端拿它做事，不直接碰内部模块。"""

    def __init__(self, ui, *, base_dir=None, app_name=APP_NAME,
                 app_version=APP_VERSION, slot_count=SLOT_COUNT,
                 max_save_size=MAX_SAVE_SIZE):
        self.ui = ui
        self.app_name = app_name
        self.app_version = app_version
        self.slot_count = slot_count
        self.max_save_size = max_save_size
        self.paths = AppPaths(base_dir)
        self.paths.ensure_dirs()

        self.cfg = AppConfig(self.paths.config)
        load_external_translations(self.paths.i18n)
        self.tr = Translator(self.cfg.language)

        self.logger = AppLogger(
            self.paths.logs, app_version,
            extra_header=[f"游戏目录: {self.cfg.game_dir or '(未设置)'}",
                          f"语言: {self.cfg.language}",
                          f"配置: {self.paths.config}",
                          f"日志目录: {self.paths.logs}"])

        self.events = queue.Queue()
        self.slots = SlotStore(self.paths.saves, self.t, slot_count)
        self.server = ServerController(ui=ui, cfg=self.cfg, t=self.t,
                                       events=self.events, logger=self.logger)
        self.flows = SaveFlows(
            ui=ui, slots=self.slots, cfg=self.cfg, t=self.t,
            events=self.events, app_name=app_name,
            max_save_size=max_save_size,
            get_bridge=lambda: self.server.bridge,
            is_server_running=lambda: self.server.running,
            backup_dir=self.paths.backups,
            logger=self.logger)
        self.download = DownloadController(
            ui=ui, cfg=self.cfg, t=self.t, events=self.events,
            base_dir=self.paths.base, logger=self.logger)
        self.editor = EditorController(
            ui=ui, slots=self.slots, t=self.t, cfg=self.cfg,
            backup_dir=self.paths.backups, save_library=self.paths.saves,
            max_save_size=max_save_size,
            get_bridge=lambda: self.server.bridge,
            is_server_running=lambda: self.server.running,
            ensure_bridge_client=self.flows.ensure_bridge_client,
            events=self.events,
            logger=self.logger)

    # ---------------- 通用 ----------------
    def t(self, key, **kw):
        return self.tr.t(key, **kw)

    def set_language(self, code):
        """切换语言（配置 + 翻译表）；界面重建由前端负责。"""
        self.cfg.update(language=code)
        self.tr.lang = code

    # ---------------- 事件 ----------------
    def dispatch(self, item):
        """处理一条后台事件；core 已完全消化返回 True（前端无需再渲染）。"""
        if self.flows.handle_event(item):
            return True
        self.editor.sync_event(item)
        self.download.sync_event(item)
        return False

    # ---------------- 生命周期 ----------------
    def status(self):
        return {
            "app_name": self.app_name,
            "version": self.app_version,
            "language": self.cfg.language,
            "paths": self.paths.as_dict(),
            "server": self.server.status(),
            "slots": self.slots.info,
        }

    def shutdown(self):
        self.server.stop()
        try:
            self.logger.action("EXIT", "程序退出")
        finally:
            self.logger.close()
