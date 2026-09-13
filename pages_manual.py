"""手动存档对话框（Tkinter 视图部分）。

逻辑全部在 `core.flows.SaveFlows`：本模块只负责画窗口、按要求周期性调用
`flows.poll_manual()`，并把「确定 / 关闭 / 复制路径」转成 core 调用。
HTML 前端将来会写一个等价的前端，core 不需要改动。
"""

import tkinter as tk
from tkinter import scrolledtext, ttk


class ManualSaveMixin:
    """「手动存档」按钮的对话框流程（视图层，无业务判断）。"""

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
        session = self.flows.start_manual(slot)
        win = tk.Toplevel(self.root)
        self._manual_win = win
        self._manual_ctx = {"session": session, "win": win}
        win.title(self.t("msg.manual_title"))
        win.transient(self.root)
        win.resizable(False, False)
        win.geometry("640x470")
        # 打开时不把焦点给输入框：焦点落在窗口本身；Esc 让输入框失去焦点
        win.grab_set()
        win.focus_set()
        win.bind("<Escape>", lambda e: win.focus_set())

        top = ttk.LabelFrame(win, text=self.t("msg.manual_tip"), padding="8")
        top.pack(fill=tk.X, padx=12, pady=(12, 6))
        row = ttk.Frame(top)
        row.pack(fill=tk.X)
        ttk.Label(row, text=str(self.temp_folder.resolve()),
                  foreground="#0a58ca").pack(side=tk.LEFT)
        ttk.Button(row, text=self.t("msg.btn_copy_path"),
                   command=self.flows.copy_temp_path).pack(side=tk.RIGHT)

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

    def _manual_confirm(self):
        """「确定」：交给 core 校验并写入粘贴的文本。"""
        ctx = getattr(self, "_manual_ctx", None)
        if not ctx:
            return
        text = self._manual_text.get("1.0", "end")
        if self.flows.submit_manual_text(ctx["session"], text):
            self._manual_close()
        elif ctx["session"].closed:
            self._manual_close()

    def _manual_close(self):
        ctx = getattr(self, "_manual_ctx", None)
        if ctx:
            self.flows.cancel_manual(ctx["session"])
        win = getattr(self, "_manual_win", None)
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        self._manual_win = None
        self._manual_ctx = None

    def _manual_poll(self):
        """周期性问 core：临时目录里是否已有稳定存档。"""
        ctx = getattr(self, "_manual_ctx", None)
        if not ctx:
            return
        win = ctx["win"]
        if not self._widget_alive(win):
            return
        state, content = self.flows.poll_manual(ctx["session"])
        if state == "detected":
            path = ctx["session"].path
            self.flows.finish_manual(ctx["session"], content, detected=True,
                                     source_path=str(path) if path else None)
            self._manual_close()
            return
        if state == "gone":
            self._manual_close()
            return
        win.after(700, self._manual_poll)
