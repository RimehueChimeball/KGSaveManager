"""核心层与界面之间的端口协议。

core 只调用这里定义的方法；具体前端负责实现（Tkinter 见 `ui_tk.TkUiPort`，
pywebview/HTML 前端将来另接一个实现，测试里用 `NullUiPort` 或自定义替身）。
新增界面能力时先在这里加方法，再在两个前端补实现。
"""


class UiPort:
    """界面端口（抽象）。所有方法都不应阻塞过久。"""

    # ---------- 对话框 ----------
    def confirm(self, message, title=""):
        """询问是/否；用户同意返回 True。"""
        raise NotImplementedError

    def ask_text(self, title, prompt, initial=""):
        """请求输入一行文本；取消返回 None。"""
        raise NotImplementedError

    def notify(self, message, title=""):
        """普通提示（信息）。"""
        raise NotImplementedError

    def warn(self, message, title=""):
        """警告提示。"""
        raise NotImplementedError

    def fail(self, message, title=""):
        """错误提示。"""
        raise NotImplementedError

    # ---------- 日志与刷新 ----------
    def log(self, message, tag=""):
        """写入「存档管理」页日志。"""
        raise NotImplementedError

    def web_log(self, message, tag=""):
        """写入「启动游戏」页日志。"""
        raise NotImplementedError

    def slots_changed(self):
        """存档库/备注变化：请前端刷新槽位显示。"""
        raise NotImplementedError

    # ---------- 宿主能力 ----------
    def pump(self):
        """等待期间让界面保持响应（无 GUI 前端为空实现）。"""
        raise NotImplementedError

    def set_clipboard(self, text):
        """写入系统剪贴板；成功返回 True。"""
        raise NotImplementedError

    def ask_directory(self, title, initial=""):
        """选择目录；取消返回 None。"""
        raise NotImplementedError

    def ask_file(self, title, initial="", filetypes=None):
        """选择文件；取消返回 None。"""
        raise NotImplementedError


class NullUiPort(UiPort):
    """无界面实现：确认类问题按 `confirm_default` 回答，其余记账后丢弃。

    `messages` 保留全部交互记录，便于测试断言“有没有弹过提示”。
    """

    def __init__(self, confirm_default=False):
        self.confirm_default = confirm_default
        self.messages = []
        self.logs = []

    # ---------- 对话框 ----------
    def confirm(self, message, title=""):
        self.messages.append(("confirm", title, message))
        return self.confirm_default

    def ask_text(self, title, prompt, initial=""):
        self.messages.append(("ask_text", title, prompt))
        return None

    def notify(self, message, title=""):
        self.messages.append(("notify", title, message))

    def warn(self, message, title=""):
        self.messages.append(("warn", title, message))

    def fail(self, message, title=""):
        self.messages.append(("fail", title, message))

    # ---------- 日志与刷新 ----------
    def log(self, message, tag=""):
        self.logs.append((tag, message))

    def web_log(self, message, tag=""):
        self.logs.append(("web:" + tag, message))

    def slots_changed(self):
        self.logs.append(("slots_changed", ""))

    # ---------- 宿主能力 ----------
    def pump(self):
        return None

    def set_clipboard(self, text):
        self.messages.append(("clipboard", "", text))
        return True

    def ask_directory(self, title, initial=""):
        self.messages.append(("ask_directory", title, initial))
        return None

    def ask_file(self, title, initial="", filetypes=None):
        self.messages.append(("ask_file", title, initial))
        return None
