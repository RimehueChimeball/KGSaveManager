"""手动导入存档对话框（Tkinter 视图部分）。

逻辑全部在 `core.flows.SaveFlows`：本模块只负责画窗口，把「选择文件 /
确定 / 复制路径 / 关闭」转成 core 调用。导入来源有两种：

- 用系统文件对话框选择游戏导出的存档文件（`flows.import_file`）；
- 直接把存档文本粘贴到输入框（`flows.import_text`）。

窗口里另外说明「存档库文件夹」的位置与改名规则：存档归属哪个槽位由文件名
`名字_槽位号.kgsav` 决定，用户可以在文件管理器里自己改名，然后刷新界面。
"""

import tkinter as tk
from tkinter import scrolledtext, ttk


class ManualSaveMixin:
    """「手动导入」按钮的对话框流程（视图层，无业务判断）。"""

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

        self._manual_slot = self.selected_slot.get()
        win = tk.Toplevel(self.root)
        self._manual_win = win
        win.title(self.t("msg.manual_title"))
        win.transient(self.root)
        win.resizable(False, False)
        win.geometry("660x560")
        # 打开时不把焦点给输入框：焦点落在窗口本身；Esc 让输入框失去焦点
        win.grab_set()
        win.focus_set()
        win.bind("<Escape>", lambda e: win.focus_set())

        library = str(self.slots.library.resolve())

        top = ttk.LabelFrame(win, text=self.t("msg.manual_tip"), padding="8")
        top.pack(fill=tk.X, padx=12, pady=(12, 6))

        row = ttk.Frame(top)
        row.pack(fill=tk.X)
        ttk.Label(row, text=self.t("msg.library_folder")).pack(side=tk.LEFT)
        ttk.Label(row, text=library, foreground="#0a58ca").pack(
            side=tk.LEFT, padx=(4, 0))
        ttk.Button(row, text=self.t("msg.btn_copy_path"),
                   command=self.flows.copy_library_path).pack(side=tk.RIGHT)

        pick = ttk.Frame(top)
        pick.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(pick, text=self.t("msg.manual_pick"),
                   command=self._manual_pick_file).pack(side=tk.LEFT)
        ttk.Label(pick, text=self.t("msg.manual_hint"), justify=tk.LEFT,
                  wraplength=430).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(win, text=self.t("msg.manual_library_hint", path=library),
                  justify=tk.LEFT, wraplength=620).pack(fill=tk.X, padx=14,
                                                        pady=(8, 6))

        self._manual_text = scrolledtext.ScrolledText(
            win, wrap=tk.NONE, height=10, font=('Consolas', 10))
        self._manual_text.pack(fill=tk.BOTH, expand=True, padx=12)

        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=12, pady=8)
        ttk.Button(btns, text=self.t("msg.btn_close"),
                   command=self._manual_close).pack(side=tk.RIGHT)
        ttk.Button(btns, text=self.t("msg.btn_ok"),
                   command=self._manual_confirm).pack(side=tk.RIGHT,
                                                      padx=(0, 8))

        win.protocol("WM_DELETE_WINDOW", self._manual_close)

    def _manual_slot_index(self):
        return getattr(self, "_manual_slot", self.selected_slot.get())

    def _manual_pick_file(self):
        """用系统文件对话框选存档文件并导入（不删除用户的原文件）。"""
        try:
            initial = str(self.flows.temp_folder)
        except Exception:
            initial = ""
        path = self.ui.ask_file(self.t("msg.manual_pick_title"), initial,
                                filetypes=self.flows.import_filetypes())
        if not path:
            return
        if self.flows.import_file(self._manual_slot_index(), path):
            self._manual_close()

    def _manual_confirm(self):
        """「确定」：交给 core 校验并写入粘贴的文本。"""
        text = self._manual_text.get("1.0", "end")
        if self.flows.import_text(self._manual_slot_index(), text):
            self._manual_close()

    def _manual_close(self):
        win = getattr(self, "_manual_win", None)
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        self._manual_win = None
