"""Tkinter 前端对 `core.ui_port.UiPort` 的实现。

把 core 的界面请求（对话框、日志、刷新、剪贴板、等待期间的事件泵）
映射到主窗口的控件上。core 只认端口，因此换成 pywebview/HTML 前端时
只需另写一个实现。
"""

from tkinter import filedialog, messagebox, simpledialog

from core.ui_port import UiPort


class TkUiPort(UiPort):
    """基于 Tkinter 的界面端口实现（持有主窗口应用实例）。"""

    def __init__(self, app):
        self.app = app

    # ---------- 对话框 ----------
    def confirm(self, message, title=""):
        return bool(messagebox.askyesno(title or self.app.app_name,
                                        message, parent=self.app.root))

    def ask_text(self, title, prompt, initial=""):
        return simpledialog.askstring(title, prompt, initialvalue=initial,
                                      parent=self.app.root)

    def notify(self, message, title=""):
        messagebox.showinfo(title or self.app.app_name, message,
                            parent=self.app.root)

    def warn(self, message, title=""):
        messagebox.showwarning(title or self.app.app_name, message,
                               parent=self.app.root)

    def fail(self, message, title=""):
        messagebox.showerror(title or self.app.app_name, message,
                             parent=self.app.root)

    # ---------- 日志与刷新 ----------
    def log(self, message, tag=""):
        self.app.log(message, tag)

    def web_log(self, message, tag=""):
        self.app.web_log(message, tag)

    def slots_changed(self):
        self.app.update_slots_display()

    # ---------- 宿主能力 ----------
    def pump(self):
        """等待期间让界面保持响应（处理一次待办事件）。"""
        try:
            self.app.root.update()
        except Exception:
            pass

    def set_clipboard(self, text):
        """写入剪贴板；失败时提示并返回 False。"""
        try:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(text)
            self.app.root.update()
            return True
        except Exception as e:
            self.app.log(self.app.t("msg.clipboard_fail", e=e),
                         self.app.t("tag.error"))
            messagebox.showerror(self.app.t("dlg.clipboard_title"), str(e),
                                 parent=self.app.root)
            return False

    def ask_directory(self, title, initial=""):
        return filedialog.askdirectory(title=title, initialdir=initial,
                                       parent=self.app.root) or None

    def ask_file(self, title, initial="", filetypes=None):
        return filedialog.askopenfilename(
            title=title, initialdir=initial,
            filetypes=filetypes or [("所有文件", "*.*")],
            parent=self.app.root) or None
