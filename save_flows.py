"""
save_flows：KGSaveManager 存档流程 Mixin（自动存档 / 自动读档 / 手动存档）。

从主类迁出（解耦）。依赖主类属性/方法：
self.t/self.log/self.cfg/self.lweb/self.bridge/self.event_queue/
self.selected_slot/self.slot_info/self.slot_label/self.slot_name/
self.slot_default_base/self.update_slots_display/self._refresh_kgm_save/
self._read_save_file/self._copy_to_clipboard/self._safe_mtime/
self._widget_alive/self.commit_notes/self.app_name/self.save_library/
self.temp_folder/self.max_save_size
"""

import os
import threading

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

import savecodec


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

        if self.bridge.apply_save(blob):
            self.log(self.t("msg.auto_load_sent"), self.t("tag.load"))
            messagebox.showinfo(self.app_name, self.t("msg.auto_load_sent"))
        else:
            self.log(self.t("msg.auto_load_fail"), self.t("tag.error"))
            messagebox.showerror(self.t("err.load_fail"),
                                 self.t("msg.auto_load_fail"))

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
            "before": set(os.listdir(self.temp_folder)),
            "detecting_path": None,
            "last_size": -1,
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

    def _manual_poll(self):
        """轮询临时文件夹：检测到新文件（写入稳定）即保存并关闭。"""
        ctx = getattr(self, "_manual_ctx", None)
        if not ctx or ctx.get("closed"):
            return
        win = ctx["win"]
        if not self._widget_alive(win):
            return

        if ctx.get("detecting_path") is None:
            try:
                now = set(os.listdir(self.temp_folder))
            except OSError:
                now = set()
            news = [f for f in (now - ctx["before"])
                    if os.path.isfile(os.path.join(self.temp_folder, f))]
            if news:
                fname = max(
                    news, key=lambda f: self._safe_mtime(
                        os.path.join(self.temp_folder, f)))
                path = os.path.join(self.temp_folder, fname)
                ctx["detecting_path"] = path
                try:
                    ctx["last_size"] = os.path.getsize(path)
                except OSError:
                    ctx["last_size"] = -1
                win.after(500, self._manual_poll)
                return
        else:
            path = ctx["detecting_path"]
            try:
                size = os.path.getsize(path)
            except OSError:
                size = -1
            if size != ctx.get("last_size") or size <= 0:
                ctx["last_size"] = size
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
                                invalid_key="msg.paste_invalid_file")
            return

        win.after(700, self._manual_poll)

    def _manual_confirm(self):
        """手动对话框「确定」：粘贴文本校验后写入。"""
        ctx = getattr(self, "_manual_ctx", None)
        if not ctx:
            return
        content = self._manual_text.get("1.0", "end").strip()
        if not content:
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

    def _manual_finish(self, content, detected, invalid_key):
        """统一收尾：写入槽位 → 关闭窗口 → （检测到时）弹窗提示。"""
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
            if detected:
                messagebox.showinfo(
                    self.app_name,
                    self.t("msg.manual_detected_saved",
                           slot=self.slot_label(slot)))

    def _write_save_to_slot(self, slot, text):
        """把存档文本写入槽位文件（先写临时再原子覆盖）。"""
        text = (text or "").strip()
        if not text:
            return None
        if len(text) > self.max_save_size:
            self.log(self.t("err.file_too_large", size=len(text)),
                     self.t("tag.error"))
            return None
        base = self.slot_name(slot) or self.slot_default_base(slot)
        dest = self.save_library / f"{base}_{slot + 1}.kgsav"
        tmp = self.save_library / f".{dest.name}.tmp"
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(str(tmp), str(dest))
            self.update_slots_display()
            self._refresh_kgm_save()
            return dest
        except OSError as e:
            self.log(self.t("msg.process_fail", e=e), self.t("tag.save"))
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return None
