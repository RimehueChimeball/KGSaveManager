"""
save_flows：KGSaveManager 存档流程 Mixin（自动存档 / 自动读档 / 手动存档）。

从主类迁出（解耦）。依赖主类属性/方法：
self.t/self.log/self.cfg/self.lweb/self.bridge/self.event_queue/
self.selected_slot/self.slot_info/self.slot_label/self.slot_name/
self.slot_default_base/self.update_slots_display/self._read_save_file/
self._copy_to_clipboard/self._widget_alive/self.commit_notes/
self.app_name/self.save_library/self.temp_folder/self.max_save_size/
self.logger
"""

import os
import threading
import time
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

import savecodec

# 浏览器/下载器还没写完的文件：不当候选，避免导入半成品
PARTIAL_SUFFIXES = (".crdownload", ".part", ".partial", ".download",
                    ".tmp", ".filepart", ".opdownload")
# 候选文件长期无法稳定（仍在写入）时，重置重扫，避免无意义空转
MANUAL_CANDIDATE_TIMEOUT = 120.0


class SaveFlowMixin:
    """自动/手动存档流程（自动读档、手动对话框等）。"""

    # ---------------- 自动存档（通过存档桥直取游戏实时存档） ----------------
    def auto_save_action(self):
        """点「自动存档」：向已连接的游戏页请求当前存档并写入选中槽位。"""
        self.commit_notes()
        if not (self.lweb.running and self.bridge is not None):
            messagebox.showwarning(self.app_name, self.t("msg.auto_no_conn"))
            return
        if not self.bridge.has_client and not self._ensure_bridge_client(6.0):
            messagebox.showwarning(self.app_name, self.t("msg.auto_no_page"))
            return

        slot = self.selected_slot.get()
        if self.slot_info[slot].get('exists'):
            if not messagebox.askyesno(
                    self.app_name, self.t("msg.auto_overwrite",
                                          slot=self.slot_label(slot))):
                self.log(self.t("msg.user_cancel"), self.t("tag.cancel"))
                return
        self.log(self.t("msg.save_start", slot=self.slot_label(slot)),
                 self.t("tag.save"))
        threading.Thread(target=self._auto_save_worker, args=(slot,),
                         daemon=True).start()

    def _auto_save_worker(self, slot):
        try:
            data = self.bridge.request_save(timeout=20)
        except Exception:
            data = None
        if data:
            self.event_queue.put(("auto_save_data", slot, data))
        else:
            self.event_queue.put(("auto_save_fail", slot))

    # ---------------- 自动读档（KGSM 侧确认后提交给游戏） ----------------
    def auto_load_action(self):
        self.commit_notes()
        if not (self.lweb.running and self.bridge is not None):
            messagebox.showwarning(self.app_name, self.t("msg.auto_no_conn"))
            return
        if not self.bridge.has_client and not self._ensure_bridge_client(6.0):
            messagebox.showwarning(self.app_name, self.t("msg.auto_no_page"))
            return

        slot = self.selected_slot.get()
        if not self.slot_info[slot].get('exists'):
            messagebox.showwarning(self.app_name,
                                   self.t("dlg.no_file",
                                          slot=self.slot_label(slot)))
            return
        if not messagebox.askyesno(
                self.app_name,
                self.t("msg.auto_load_ask", slot=self.slot_label(slot))):
            self.log(self.t("msg.user_cancel"), self.t("tag.cancel"))
            return

        try:
            blob = self._read_save_file(self.slot_info[slot]['filename'])
        except Exception as e:
            self.log(self.t("msg.read_fail", e=e), self.t("tag.error"))
            messagebox.showerror(self.t("err.load_fail"), str(e))
            return

        # 下发与等待确认放到后台线程：页面确认最多要等几秒，不能冻结界面
        self.log(self.t("msg.auto_load_sending", slot=self.slot_label(slot)),
                 self.t("tag.load"))
        threading.Thread(target=self._auto_load_worker, args=(slot, blob),
                         daemon=True).start()

    def _auto_load_worker(self, slot, blob):
        try:
            result = self.bridge.apply_save(blob, timeout=8.0)
        except Exception:
            result = False
        self.event_queue.put(("auto_load_result", slot, result))

    # ---------------- 手动存档对话框 ----------------
    def manual_save_action(self):
        self.commit_notes()

        existing = getattr(self, "_manual_win", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass

        slot = self.selected_slot.get()
        win = tk.Toplevel(self.root)
        self._manual_win = win
        win.title(self.t("msg.manual_title"))
        win.transient(self.root)
        win.resizable(False, False)
        win.geometry("640x470")
        # 打开时不把焦点给输入框：焦点落在窗口本身；Esc 让输入框失去焦点
        win.grab_set()
        win.focus_set()
        win.bind("<Escape>", lambda e: win.focus_set())
        self._manual_ctx = {
            "slot": slot,
            "win": win,
            "closed": False,
            "before": self._temp_snapshot(),
            "detecting_path": None,
            "last_size": -1,
            "last_mtime": -1,
        }

        top = ttk.LabelFrame(win, text=self.t("msg.manual_tip"), padding="8")
        top.pack(fill=tk.X, padx=12, pady=(12, 6))
        row = ttk.Frame(top)
        row.pack(fill=tk.X)
        ttk.Label(row, text=str(self.temp_folder.resolve()),
                  foreground="#0a58ca").pack(side=tk.LEFT)
        ttk.Button(row, text=self.t("msg.btn_copy_path"),
                   command=self._manual_copy_path).pack(side=tk.RIGHT)

        ttk.Label(win, text=self.t("msg.manual_hint"), justify=tk.LEFT,
                  wraplength=600).pack(fill=tk.X, padx=14, pady=(2, 8))

        self._manual_text = scrolledtext.ScrolledText(
            win, wrap=tk.NONE, height=11, font=('Consolas', 10))
        self._manual_text.pack(fill=tk.BOTH, expand=True, padx=12)

        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=12, pady=8)
        ttk.Button(btns, text=self.t("msg.btn_close"),
                   command=self._manual_close).pack(side=tk.RIGHT)
        ttk.Button(btns, text=self.t("msg.btn_ok"),
                   command=self._manual_confirm).pack(side=tk.RIGHT,
                                                     padx=(0, 8))

        win.protocol("WM_DELETE_WINDOW", self._manual_close)
        win.after(700, self._manual_poll)

    def _manual_copy_path(self):
        self._copy_to_clipboard(str(self.temp_folder.resolve()))
        self.log(self.t("msg.path_copied", path=self.temp_folder),
                 self.t("tag.save"))

    def _manual_close(self):
        ctx = getattr(self, "_manual_ctx", None)
        if ctx:
            ctx["closed"] = True
        win = getattr(self, "_manual_win", None)
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        self._manual_win = None

    def _temp_snapshot(self):
        """临时文件夹快照 {文件名: (mtime_ns, size)}。

        用内容快照而不是“文件名集合”做对比：游戏导出若覆盖同名文件
        （上次导入后残留、或导出名固定），集合差为空会漏检。
        """
        snap = {}
        try:
            with os.scandir(self.temp_folder) as it:
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

    def _manual_poll(self):
        """轮询临时文件夹：候选文件写入稳定后保存并关闭窗口。

        候选规则：
        - 忽略浏览器/下载器留下的半成品（.crdownload/.part/.tmp…）；
        - 优先"开窗后新增或被覆盖"的文件；开窗时夹子里已有的文件也会被
          当作候选（支持"先导出、再点手动存档"的顺序），并在日志里说明；
        - 候选文件消失（被改名/删除）时重置并重新扫描，不会卡死；
        - 候选长时间无法稳定（仍在写入）时重置重扫，避免一直空转。
        """
        ctx = getattr(self, "_manual_ctx", None)
        if not ctx or ctx.get("closed"):
            return
        win = ctx["win"]
        if not self._widget_alive(win):
            return

        if ctx.get("detecting_path") is None:
            candidate = self._pick_manual_candidate(ctx)
            if candidate is not None:
                fname, meta = candidate
                ctx["detecting_path"] = os.path.join(self.temp_folder,
                                                     fname)
                ctx["last_size"] = meta[1]
                ctx["last_mtime"] = meta[0]
                ctx["candidate_at"] = time.time()
                win.after(500, self._manual_poll)
                return
        else:
            path = ctx["detecting_path"]
            try:
                st = os.stat(path)
                size, mtime = st.st_size, st.st_mtime_ns
            except OSError:
                # 文件被改名或删除：重置候选，重新扫描（旧逻辑会在这里卡死）
                self.log(self.t("msg.manual_candidate_gone",
                                name=os.path.basename(path)),
                         self.t("tag.save"))
                self._reset_manual_candidate(ctx)
                win.after(500, self._manual_poll)
                return
            if (size != ctx.get("last_size")
                    or mtime != ctx.get("last_mtime") or size <= 0):
                if time.time() - ctx.get("candidate_at", time.time()) > \
                        MANUAL_CANDIDATE_TIMEOUT:
                    self.log(self.t("msg.manual_candidate_busy",
                                    name=os.path.basename(path)),
                             self.t("tag.save"))
                    self._reset_manual_candidate(ctx)
                    win.after(700, self._manual_poll)
                    return
                ctx["last_size"] = size
                ctx["last_mtime"] = mtime
                win.after(500, self._manual_poll)
                return
            try:
                with open(path, "r", encoding="utf-8",
                          errors="replace") as f:
                    content = f.read()
            except Exception as e:
                self.log(self.t("msg.read_fail", e=e), self.t("tag.error"))
                ctx["closed"] = True
                win.destroy()
                return
            self._manual_finish(content, detected=True,
                                invalid_key="msg.paste_invalid_file",
                                source_path=path)
            return

        win.after(700, self._manual_poll)

    def _pick_manual_candidate(self, ctx):
        """挑一个候选文件，返回 (文件名, (mtime_ns, size)) 或 None。"""
        now = self._temp_snapshot()
        changed = [name for name, meta in now.items()
                   if ctx["before"].get(name) != meta
                   and not self._is_partial_name(name)]
        if changed:
            fname = max(changed, key=lambda f: now[f][0])
            return fname, now[fname]

        # 开窗时夹子里已有文件：只认最新那个，且要在日志里说清楚
        if not ctx.get("scanned_existing"):
            ctx["scanned_existing"] = True
            existing = [name for name, meta in now.items()
                        if not self._is_partial_name(name) and meta[1] > 0]
            if existing:
                fname = max(existing, key=lambda f: now[f][0])
                self.log(self.t("msg.manual_using_existing", name=fname),
                         self.t("tag.save"))
                return fname, now[fname]
        return None

    @staticmethod
    def _is_partial_name(name):
        """浏览器/下载器未完成的文件（不应当作存档导入）。"""
        low = name.lower()
        return any(low.endswith(suffix) for suffix in PARTIAL_SUFFIXES)

    @staticmethod
    def _reset_manual_candidate(ctx):
        ctx["detecting_path"] = None
        ctx["last_size"] = -1
        ctx["last_mtime"] = -1
        ctx["candidate_at"] = time.time()

    def _manual_confirm(self):
        """手动对话框「确定」：粘贴文本校验后写入。"""
        ctx = getattr(self, "_manual_ctx", None)
        if not ctx:
            return
        # 只去掉粘贴带来的行尾换行：UTF-16 存档的尾部空格是载荷本身，
        # 整体 strip() 会破坏它（详见 savecodec.validate 的格式判定）
        content = self._tidy_payload(self._manual_text.get("1.0", "end"))
        if not content.strip():
            messagebox.showwarning(self.app_name, self.t("msg.paste_empty"),
                                   parent=ctx["win"])
            return
        if len(content) > self.max_save_size:
            messagebox.showerror(
                self.t("err.save_fail"),
                self.t("err.file_too_large", size=len(content)),
                parent=ctx["win"])
            return
        ok, _ = savecodec.validate(content)
        if not ok:
            if not messagebox.askyesno(
                    self.app_name, self.t("msg.invalid_ask"),
                    parent=ctx["win"]):
                return
        self._manual_finish(content, detected=False, invalid_key=None)

    @staticmethod
    def _tidy_payload(text):
        """只裁掉行尾换行；保留其它空白（可能是存档载荷的一部分）。"""
        return (text or "").rstrip("\r\n")

    def _manual_finish(self, content, detected, invalid_key,
                       source_path=None):
        """统一收尾：写入槽位 → 删除临时原文 → 关闭窗口 →（检测到时）弹窗提示。"""
        ctx = getattr(self, "_manual_ctx", None)
        win = ctx["win"] if ctx else None
        slot = ctx["slot"] if ctx else self.selected_slot.get()

        ok, _ = savecodec.validate(content)
        if not ok and invalid_key:
            if win is None or not messagebox.askyesno(
                    self.app_name, self.t(invalid_key), parent=win):
                self.log(self.t("msg.invalid_skip"), self.t("tag.save"))
                if ctx:
                    ctx["closed"] = True
                if win is not None:
                    win.destroy()
                self._manual_win = None
                return

        dest = self._write_save_to_slot(slot, content)
        if ctx:
            ctx["closed"] = True
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        self._manual_win = None
        if dest is not None:
            self.log(self.t("msg.saved_to", dest=dest.name),
                     self.t("tag.done"))
            if source_path:
                self._remove_temp_file(source_path)
            if detected:
                messagebox.showinfo(
                    self.app_name,
                    self.t("msg.manual_detected_saved",
                           slot=self.slot_label(slot)))

    def _remove_temp_file(self, path):
        """导入成功后删除临时文件夹里的原文，避免下次同名覆盖漏检。"""
        try:
            name = os.path.basename(path)
            os.remove(path)
        except OSError:
            return
        self.log(self.t("msg.temp_cleaned", name=name), self.t("tag.save"))

    def _write_save_to_slot(self, slot, text):
        """把存档文本写入槽位文件（先写临时再原子覆盖）。

        覆盖前把原文件备份到 `kgsm_data/backups/`（与编辑器同一套命名），
        避免一次误操作把已有存档弄丢。
        """
        text = self._tidy_payload(text)
        if not text.strip():
            return None
        if len(text) > self.max_save_size:
            self.log(self.t("err.file_too_large", size=len(text)),
                     self.t("tag.error"))
            return None
        base = self.slot_name(slot) or self.slot_default_base(slot)
        dest = self.save_library / f"{base}_{slot + 1}.kgsav"
        tmp = self.save_library / f".{dest.name}.tmp"
        self._backup_slot_file(dest)
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(str(tmp), str(dest))
            self.update_slots_display()
            return dest
        except OSError as e:
            self.log(self.t("msg.process_fail", e=e), self.t("tag.save"))
            logger = getattr(self, "logger", None)
            if logger is not None:
                logger.error(f"写入存档失败 {dest.name}: {e}")
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return None

    def _backup_slot_file(self, dest):
        """覆盖槽位前备份原文件；原文件不存在或备份失败都不影响写入。"""
        backup_dir = getattr(self, "backup_dir", None)
        if backup_dir is None or not dest.is_file():
            return
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = Path(backup_dir) / f"{dest.name}.{stamp}.bak"
            bak.write_bytes(dest.read_bytes())
            self.log(self.t("msg.slot_backup", path=bak.name),
                     self.t("tag.save"))
        except OSError as e:
            self.log(self.t("msg.backup_fail", e=e), self.t("tag.error"))
