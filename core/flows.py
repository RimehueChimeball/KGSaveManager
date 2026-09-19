"""自动存档 / 自动读档 / 手动导入流程与后台事件处理。

本模块不 import 任何 GUI 工具包：所有提示、询问、日志、刷新请求都走
`UiPort`，后台线程只把结果放进 `events` 队列，由前端在 UI 线程取出后
调用 `handle_event()`。

手动导入由前端负责“选文件”（Tk 用系统文件对话框，HTML 用页面里的文件
选择器），core 只做读取、校验、写入，不监控任何文件夹。

事件契约（前端轮询队列时使用）：
- `("auto_save_data", slot, text)`：自动存档取到存档文本，请写入槽位
- `("auto_save_fail", slot)`：自动存档超时/失败
- `("auto_load_result", slot, result)`：自动读档下发结果，result 为
  True（页面确认）/ False（页面报错或发送失败）/ None（已发送未确认）
"""

import threading
import time
from datetime import datetime
from pathlib import Path

import savecodec


class SaveFlows:
    """存档流程。依赖：槽位存储、配置、界面端口、事件队列、运行日志。"""

    def __init__(self, *, ui, slots, cfg, t, events, app_name,
                 max_save_size, get_bridge, is_server_running, logger=None,
                 backup_dir=None, reconnect_timeout=6.0):
        self.ui = ui
        self.slots = slots
        self.cfg = cfg
        self.t = t
        self.events = events
        self.app_name = app_name
        self.max_save_size = max_save_size
        self.get_bridge = get_bridge
        self.is_server_running = is_server_running
        self.logger = logger
        self.backup_dir = Path(backup_dir) if backup_dir else None
        self.reconnect_timeout = reconnect_timeout

    # ---------------- 通用 ----------------
    def log(self, message, tag=""):
        self.ui.log(message, tag)

    def _log_error(self, message):
        if self.logger is not None:
            self.logger.error(message)

    def _log_warn(self, message):
        if self.logger is not None:
            self.logger.warn(message)

    def _has_client(self):
        bridge = self.get_bridge()
        return bool(bridge is not None and bridge.has_client)

    def _ready(self):
        return bool(self.is_server_running() and self.get_bridge() is not None)

    def ensure_bridge_client(self, timeout=6.0):
        """等待桥有可用连接（页面刷新后的重连期），期间保持界面响应。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._ready() and self._has_client():
                return True
            self.ui.pump()
            time.sleep(0.15)
        return self._ready() and self._has_client()

    # ---------------- 自动存档 ----------------
    def auto_save(self, slot):
        """向已连接的游戏页请求当前存档并写入选中槽位。"""
        if not self._ready():
            self.ui.warn(self.t("msg.auto_no_conn"), self.app_name)
            return False
        if not self._has_client() and not self.ensure_bridge_client(
                self.reconnect_timeout):
            self.ui.warn(self.t("msg.auto_no_page"), self.app_name)
            return False
        if self.slots.exists(slot):
            if not self.ui.confirm(
                    self.t("msg.auto_overwrite",
                           slot=self.slots.label(slot)), self.app_name):
                self.log(self.t("msg.user_cancel"), self.t("tag.cancel"))
                return False
        self.log(self.t("msg.save_start", slot=self.slots.label(slot)),
                 self.t("tag.save"))
        threading.Thread(target=self._auto_save_worker, args=(slot,),
                         daemon=True).start()
        return True

    def _auto_save_worker(self, slot):
        try:
            data = self.get_bridge().request_save(timeout=20)
        except Exception:
            data = None
        if data:
            self.events.put(("auto_save_data", slot, data))
        else:
            self.events.put(("auto_save_fail", slot))

    # ---------------- 自动读档 ----------------
    def auto_load(self, slot):
        """KGSM 侧确认一次后，把槽位存档下发给游戏页面。

        下发与等待页面确认放到后台线程：页面确认最多要等几秒，不能冻结界面。
        :return: True 表示已开始下发（结果经事件 `auto_load_result` 回传）
        """
        if not self._ready():
            self.ui.warn(self.t("msg.auto_no_conn"), self.app_name)
            return False
        if not self._has_client() and not self.ensure_bridge_client(
                self.reconnect_timeout):
            self.ui.warn(self.t("msg.auto_no_page"), self.app_name)
            return False
        if not self.slots.exists(slot):
            self.ui.warn(self.t("dlg.no_file", slot=self.slots.label(slot)),
                         self.app_name)
            return False
        if not self.ui.confirm(
                self.t("msg.auto_load_ask", slot=self.slots.label(slot)),
                self.app_name):
            self.log(self.t("msg.user_cancel"), self.t("tag.cancel"))
            return False
        try:
            blob = self.slots.read(self.slots.path(slot), self.max_save_size)
        except Exception as e:
            self.log(self.t("msg.read_fail", e=e), self.t("tag.error"))
            self.ui.fail(str(e), self.t("err.load_fail"))
            return False
        self.log(self.t("msg.auto_load_sending", slot=self.slots.label(slot)),
                 self.t("tag.load"))
        threading.Thread(target=self._auto_load_worker, args=(slot, blob),
                         daemon=True).start()
        return True

    def _auto_load_worker(self, slot, blob):
        try:
            result = self.get_bridge().apply_save(blob, timeout=8.0)
        except Exception:
            result = False
        self.events.put(("auto_load_result", slot, result))

    # ---------------- 复制存档 ----------------
    def copy_save(self, slot):
        """把槽位内容复制到剪贴板（用于游戏内导入）。"""
        if not self.slots.exists(slot):
            self.ui.warn(self.t("dlg.no_file", slot=self.slots.label(slot)),
                         self.app_name)
            return False
        try:
            content = self.slots.read(self.slots.path(slot), self.max_save_size)
        except Exception as e:
            self.log(self.t("msg.read_fail", e=e), self.t("tag.load"))
            self.ui.fail(str(e), self.t("err.load_fail"))
            return False
        if not self.ui.set_clipboard(content):
            return False
        self.log(self.t("msg.copied_save", slot=self.slots.label(slot)),
                 self.t("tag.load"))
        self.log(self.t("msg.load_hint"))
        self.ui.notify(self.t("dlg.copied_ok", slot=self.slots.label(slot)),
                       self.app_name)
        return True

    # ---------------- 手动导入 ----------------
    def import_filetypes(self):
        """文件对话框用的类型过滤器（前端传给系统对话框）。"""
        return [(self.t("msg.filetype_save"), "*.kgsav *.txt *.json *.save"),
                (self.t("msg.filetype_all"), "*.*")]

    def default_import_dir(self):
        """选文件对话框的默认打开位置：系统的下载文件夹，其次存档库。"""
        downloads = Path.home() / "Downloads"
        if downloads.is_dir():
            return downloads
        return self.slots.library

    def import_file(self, slot, path):
        """导入用户选定的存档文件。

        只读取该文件，不删除也不改名——它属于用户自己的下载目录。
        """
        p = Path(path)
        try:
            size = p.stat().st_size
            if size <= 0:
                raise ValueError(self.t("err.file_empty"))
            if size > self.max_save_size:
                raise ValueError(self.t("err.file_too_large", size=size))
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            self.log(self.t("msg.read_fail", e=e), self.t("tag.error"))
            self._log_error(f"读取存档文件失败: {p.name} {e}")
            self.ui.fail(str(e), self.t("err.load_fail"))
            return False
        except ValueError as e:
            self.ui.fail(str(e), self.t("err.load_fail"))
            return False
        return self.import_text(slot, content, source_name=p.name)

    def import_text(self, slot, text, source_name=None):
        """校验文本后写入槽位（「选择文件」与「粘贴文本」共用）。

        :param source_name: 选中文件的文件名（仅用于提示文案）
        :return: True 表示已写入槽位
        """
        content = self._tidy_payload(text)
        if not content.strip():
            self.ui.warn(self.t("msg.paste_empty"), self.app_name)
            return False
        if len(content) > self.max_save_size:
            self.ui.fail(self.t("err.file_too_large", size=len(content)),
                         self.t("err.save_fail"))
            return False
        ok, _ = savecodec.validate(content)
        if not ok and not self.ui.confirm(self.t("msg.invalid_ask"),
                                          self.app_name):
            return False

        self._backup_slot_file(slot)
        dest, err = self.slots.write(slot, content, self.max_save_size)
        if dest is None:
            if err is not None:
                self.log(self.t(err[0], **err[1]), self.t("tag.save"))
                self._log_error(f"写入存档失败: slot={slot} {err[0]}")
            return False
        self.log(self.t("msg.saved_to", dest=dest.name), self.t("tag.done"))
        if source_name:
            self.ui.notify(self.t("msg.manual_imported", name=source_name,
                                  slot=self.slots.label(slot)), self.app_name)
        else:
            self.ui.notify(self.t("msg.saved_to", dest=dest.name),
                           self.app_name)
        self.ui.slots_changed()
        return True

    @staticmethod
    def _tidy_payload(text):
        """只裁掉行尾换行；保留其它空白（可能是存档载荷的一部分）。

        UTF-16 存档的尾部空格是载荷本身，整体 strip() 会破坏它
        （详见 savecodec.validate 的格式判定）。
        """
        return (text or "").rstrip("\r\n")

    def copy_library_path(self):
        """复制存档库文件夹路径到剪贴板。"""
        library = self.slots.library
        self.ui.set_clipboard(str(library.resolve()))
        self.log(self.t("msg.path_copied", path=library), self.t("tag.save"))

    # ---------------- 存档库检查 ----------------
    def check_library(self):
        """检查异常文件并写入日志（合规 = 文件名可解析为 名字_槽位号.kgsav）。"""
        self.log(self.t("msg.check_start"), self.t("tag.check"))
        result = self.slots.check()

        self.log("=" * 50, self.t("tag.check"))
        if result['invalid']:
            self.log(self.t("msg.lib_abnormal"), self.t("tag.check"))
            for f in result['invalid']:
                self.log(self.t("msg.item", f=f), self.t("tag.check"))
        else:
            self.log(self.t("msg.lib_clean"), self.t("tag.check"))

        if result['empty']:
            self.log(self.t("msg.lib_empty"), self.t("tag.check"))
            for f in result['empty']:
                self.log(self.t("msg.item", f=f), self.t("tag.check"))

        self.log(self.t("msg.check_tail"), self.t("tag.check"))
        self.log("=" * 50, self.t("tag.check"))

    # ---------------- 后台事件 ----------------
    def handle_event(self, item):
        """处理本模块产生的事件；已处理返回 True。"""
        kind = item[0]
        if kind == "auto_save_data":
            slot, data = item[1], item[2]
            dest, err = self.slots.write(slot, data, self.max_save_size)
            if dest is not None:
                self.log(self.t("msg.auto_saved", dest=dest.name),
                         self.t("tag.done"))
                self.ui.slots_changed()
            elif err is not None:
                self.log(self.t(err[0], **err[1]), self.t("tag.error"))
                self._log_error(f"自动存档写入失败: slot={slot} {err[0]}")
            else:
                self._log_error(f"自动存档写入槽位失败: slot={slot}")
            return True
        if kind == "auto_save_fail":
            self.log(self.t("msg.auto_timeout"), self.t("tag.timeout"))
            self._log_warn("自动存档超时：页面未返回存档数据")
            return True
        if kind == "auto_load_result":
            slot, result = item[1], item[2]
            if result is True:
                self.log(self.t("msg.auto_load_sent"), self.t("tag.load"))
                self.ui.notify(self.t("msg.auto_load_sent"), self.app_name)
            elif result is None:
                self.log(self.t("msg.auto_load_unconfirmed"),
                         self.t("tag.timeout"))
                self._log_warn(f"自动读档未确认: slot={slot}")
                self.ui.warn(self.t("msg.auto_load_unconfirmed"), self.app_name)
            else:
                self.log(self.t("msg.auto_load_fail"), self.t("tag.error"))
                self._log_error(f"自动读档失败: slot={slot}")
                self.ui.fail(self.t("msg.auto_load_fail"),
                             self.t("err.load_fail"))
            return True
        return False

    # ---------------- 槽位备份 ----------------
    def _backup_slot_file(self, slot):
        """覆盖槽位前备份原文件；原文件不存在或备份失败都不影响写入。"""
        if self.backup_dir is None:
            return
        dest = self.slots.path(slot)
        if dest is None or not dest.is_file():
            return
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.backup_dir / f"{dest.name}.{stamp}.bak"
            bak.write_bytes(dest.read_bytes())
            self.log(self.t("msg.slot_backup", path=bak.name),
                     self.t("tag.save"))
        except OSError as e:
            self.log(self.t("msg.backup_fail", e=e), self.t("tag.error"))
