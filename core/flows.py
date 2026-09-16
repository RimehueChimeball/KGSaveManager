"""自动存档 / 自动读档 / 手动存档流程与后台事件处理。

本模块不 import 任何 GUI 工具包：所有提示、询问、日志、刷新请求都走
`UiPort`，后台线程只把结果放进 `events` 队列，由前端在 UI 线程取出后
调用 `handle_event()`。

事件契约（前端轮询队列时使用）：
- `("auto_save_data", slot, text)`：自动存档取到存档文本，请写入槽位
- `("auto_save_fail", slot)`：自动存档超时/失败
- `("auto_load_result", slot, result)`：自动读档下发结果，result 为
  True（页面确认）/ False（页面报错或发送失败）/ None（已发送未确认）
"""

import os
import threading
import time
from datetime import datetime
from pathlib import Path

import savecodec

# 浏览器/下载器还没写完的文件：不当候选，避免导入半成品
PARTIAL_SUFFIXES = (".crdownload", ".part", ".partial", ".download",
                    ".tmp", ".filepart", ".opdownload")
# 候选文件长期无法稳定（仍在写入）时，重置重扫，避免无意义空转
MANUAL_CANDIDATE_TIMEOUT = 120.0


def snapshot_dir(folder):
    """目录快照 `{文件名: (mtime_ns, 大小)}`。

    用内容快照而不是“文件名集合”做对比：游戏导出若覆盖同名文件
    （上次导入后残留、或导出名固定），集合差为空会漏检。
    """
    snap = {}
    try:
        with os.scandir(folder) as it:
            for entry in it:
                try:
                    if not entry.is_file():
                        continue
                    st = entry.stat()
                except OSError:
                    continue
                snap[entry.name] = (st.st_mtime_ns, st.st_size)
    except OSError:
        return snap
    return snap


def clean_temp_folder(folder, keep_seconds, logger=None):
    """删除临时目录中超过保留期的文件，返回删除数量。"""
    cutoff = time.time() - keep_seconds
    removed = 0
    try:
        entries = list(Path(folder).iterdir())
    except OSError:
        return 0
    for p in entries:
        try:
            if not p.is_file() or p.stat().st_mtime >= cutoff:
                continue
            p.unlink()
            removed += 1
        except OSError:
            continue
    if removed and logger is not None:
        logger.info(f"清理临时文件 {removed} 个（保留 {keep_seconds // 86400} 天内）")
    return removed


class ManualSaveSession:
    """一次手动存档的会话状态（前端负责周期性调用 `poll_manual`）。"""

    def __init__(self, slot, temp_folder):
        self.slot = slot
        self.temp_folder = Path(temp_folder)
        self.snapshot = snapshot_dir(self.temp_folder)
        self.path = None
        self.last_size = -1
        self.last_mtime = -1
        self.candidate_at = time.time()
        self.scanned_existing = False
        self.closed = False


class SaveFlows:
    """存档流程。依赖：槽位存储、配置、界面端口、事件队列、运行日志。"""

    def __init__(self, *, ui, slots, cfg, t, events, app_name, temp_folder,
                 max_save_size, get_bridge, is_server_running, logger=None,
                 backup_dir=None, reconnect_timeout=6.0):
        self.ui = ui
        self.slots = slots
        self.cfg = cfg
        self.t = t
        self.events = events
        self.app_name = app_name
        self.temp_folder = Path(temp_folder)
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

    # ---------------- 手动存档 ----------------
    def start_manual(self, slot):
        """开始一次手动存档会话（前端随后周期性调用 `poll_manual`）。"""
        return ManualSaveSession(slot, self.temp_folder)

    def poll_manual(self, session):
        """检查临时目录。

        候选规则：
        - 忽略浏览器/下载器留下的半成品（.crdownload/.part/.tmp…）；
        - 优先"开窗后新增或被覆盖"的文件；开窗时目录里已有的文件也会被当作
          候选（支持"先导出、再点手动存档"的顺序），并在日志里说明；
        - 候选文件消失（被改名/删除）时重置并重新扫描，不会卡死；
        - 候选长时间无法稳定（仍在写入）时重置重扫，避免一直空转。

        :return: ("waiting", None) 继续等 / ("detected", 文本) 已检测到稳定文件
                 / ("gone", None) 会话作废或读取失败（前端关闭对话框）
        """
        if session.closed:
            return ("gone", None)
        if session.path is None:
            candidate = self._pick_manual_candidate(session)
            if candidate is not None:
                name, meta = candidate
                session.path = session.temp_folder / name
                session.last_size = meta[1]
                session.last_mtime = meta[0]
                session.candidate_at = time.time()
            return ("waiting", None)

        try:
            st = session.path.stat()
            size, mtime = st.st_size, st.st_mtime_ns
        except OSError:
            # 文件被改名或删除：重置候选并重新扫描（旧逻辑会在这里卡死）
            self.log(self.t("msg.manual_candidate_gone",
                            name=session.path.name), self.t("tag.save"))
            self._reset_manual_candidate(session)
            return ("waiting", None)
        if size != session.last_size or mtime != session.last_mtime or size <= 0:
            if (time.time() - session.candidate_at
                    > MANUAL_CANDIDATE_TIMEOUT):
                self.log(self.t("msg.manual_candidate_busy",
                                name=session.path.name), self.t("tag.save"))
                self._reset_manual_candidate(session)
                return ("waiting", None)
            session.last_size = size
            session.last_mtime = mtime
            return ("waiting", None)
        try:
            content = session.path.read_text(encoding="utf-8",
                                             errors="replace")
        except OSError as e:
            self.log(self.t("msg.read_fail", e=e), self.t("tag.error"))
            return ("gone", None)
        return ("detected", content)

    def _pick_manual_candidate(self, session):
        """挑一个候选文件，返回 (文件名, (mtime_ns, size)) 或 None。"""
        now = snapshot_dir(session.temp_folder)
        changed = [name for name, meta in now.items()
                   if session.snapshot.get(name) != meta
                   and not self._is_partial_name(name)]
        if changed:
            name = max(changed, key=lambda f: now[f][0])
            return name, now[name]

        # 开窗时夹子里已有文件：只认最新那个，且要在日志里说清楚
        if not session.scanned_existing:
            session.scanned_existing = True
            existing = [name for name, meta in now.items()
                        if not self._is_partial_name(name) and meta[1] > 0]
            if existing:
                name = max(existing, key=lambda f: now[f][0])
                self.log(self.t("msg.manual_using_existing", name=name),
                         self.t("tag.save"))
                return name, now[name]
        return None

    @staticmethod
    def _is_partial_name(name):
        """浏览器/下载器未完成的文件（不应当作存档导入）。"""
        low = name.lower()
        return any(low.endswith(suffix) for suffix in PARTIAL_SUFFIXES)

    @staticmethod
    def _reset_manual_candidate(session):
        session.path = None
        session.last_size = -1
        session.last_mtime = -1
        session.candidate_at = time.time()

    @staticmethod
    def _tidy_payload(text):
        """只裁掉行尾换行；保留其它空白（可能是存档载荷的一部分）。

        UTF-16 存档的尾部空格是载荷本身，整体 strip() 会破坏它
        （详见 savecodec.validate 的格式判定）。
        """
        return (text or "").rstrip("\r\n")

    def submit_manual_text(self, session, text):
        """手动对话框「确定」：校验粘贴文本后写入。"""
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
        return self.finish_manual(session, content, detected=False)

    def finish_manual(self, session, content, detected, source_path=None):
        """统一收尾：写入槽位 → 删除临时原文 → 记录日志 →（检测到时）提示。"""
        slot = session.slot
        content = self._tidy_payload(content)
        ok, _ = savecodec.validate(content)
        if not ok and detected:
            if not self.ui.confirm(self.t("msg.paste_invalid_file"),
                                   self.app_name):
                self.log(self.t("msg.invalid_skip"), self.t("tag.save"))
                session.closed = True
                return False

        self._backup_slot_file(slot)
        dest, err = self.slots.write(slot, content, self.max_save_size)
        session.closed = True
        if dest is None:
            if err is not None:
                self.log(self.t(err[0], **err[1]), self.t("tag.save"))
                self._log_error(f"写入存档失败: slot={slot} {err[0]}")
            return False
        self.log(self.t("msg.saved_to", dest=dest.name), self.t("tag.done"))
        if source_path:
            self._remove_temp_file(source_path)
        self.ui.slots_changed()
        if detected:
            self.ui.notify(
                self.t("msg.manual_detected_saved",
                       slot=self.slots.label(slot)), self.app_name)
        return True

    def cancel_manual(self, session):
        if session is not None:
            session.closed = True

    def _remove_temp_file(self, path):
        """导入成功后删除临时文件夹里的原文，避免下次同名覆盖漏检。"""
        try:
            name = os.path.basename(path)
            os.remove(path)
        except OSError:
            return
        self.log(self.t("msg.temp_cleaned", name=name), self.t("tag.save"))

    def copy_temp_path(self):
        """复制临时目录路径到剪贴板。"""
        self.ui.set_clipboard(str(self.temp_folder.resolve()))
        self.log(self.t("msg.path_copied", path=self.temp_folder),
                 self.t("tag.save"))

    # ---------------- 存档库检查 ----------------
    def check_library(self):
        """检查异常文件并写入日志（合规 = 文件名可解析为 名字_槽位号.kgsav）。"""
        self.log(self.t("msg.check_start"), self.t("tag.check"))
        result = self.slots.check()
        try:
            temp_files = sorted(os.listdir(self.temp_folder))
        except OSError:
            temp_files = []

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

        if temp_files:
            self.log(self.t("msg.temp_files"), self.t("tag.check"))
            for f in temp_files:
                self.log(self.t("msg.item", f=f), self.t("tag.check"))
        else:
            self.log(self.t("msg.temp_clean"), self.t("tag.check"))

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
