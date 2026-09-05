"""
i18n：KGSaveManager 中/英界面翻译模块。

- 语言代码固定英文：zh / en
- 首次无配置文件时由 detect_system_language() 探测系统语言，
  非中文默认 en，中文默认 zh
"""

LANG_ZH = "zh"
LANG_EN = "en"


def detect_system_language():
    """探测系统 UI 语言；中文系统返回 zh，否则返回 en。"""
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        if (lang_id & 0x3FF) == 0x04:      # LANG_CHINESE 主语言
            return LANG_ZH
        return LANG_EN
    except Exception:
        try:
            import locale
            lc = (locale.getdefaultlocale() or ("", ""))[0] or ""
            if lc.lower().startswith("zh"):
                return LANG_ZH
        except Exception:
            pass
        return LANG_EN


# ---------------- 中文字符串 ----------------
_ZH = {
    # 标签页
    "tab.kgsm": "KGSM",
    "tab.game": "启动游戏",
    "tab.saves": "存档管理",
    "tab.settings": "配置",

    # 通用
    "ui.empty_short": "（空）",
    "ui.browse": "浏览...",
    "ui.auto_port": "留空 = 自动选择空闲端口",

    # ---- KGSM 页 ----
    "kgsm.heading": "KittensGame 存档管理器",
    "kgsm.dir_none": "游戏目录：未设置",
    "kgsm.dir_set": "游戏目录：{dir}",
    "kgsm.quick_title": "快速启动游戏",
    "kgsm.quick_desc": "以游戏目录为根启动本地服务，并在浏览器中打开游戏。",
    "kgsm.copy_title": "复制存档并启动游戏",
    "kgsm.copy_desc": "先把存档复制到剪贴板，再启动服务打开游戏，"
                      "进入游戏后直接粘贴 (Ctrl+V) 导入。",
    "kgsm.mode_recent": "最近存档",
    "kgsm.mode_slot": "指定存档",
    "kgsm.cur_prefix": "当前将复制：",
    "kgsm.btn_run": "运行",
    "kgsm.first_use_q": "第一次使用？",
    "kgsm.btn_config": "配置程序",
    "kgsm.download_1": "下载游戏 · Kittens Game（kitten-science）",
    "kgsm.download_2": "下载游戏 · Kittens Game（nuclear-unicorn）",

    # ---- 启动游戏页 ----
    "la.title": "本地 Web 服务（仅本机 127.0.0.1 可访问）",
    "la.dir": "服务目录",
    "la.port": "端口",
    "la.hint": "把下载的游戏文件解压进游戏目录后即可启动；服务只在本机监听。",
    "la.log_title": "服务日志",
    "la.ready": "就绪：设置目录与端口后点击「启动并打开浏览器」。",
    "la.btn_start": "启动并打开浏览器",
    "la.btn_stop": "停止服务",

    # ---- 存档管理页 ----
    "sv.title_slots": "存档位",
    "sv.title_log": "输出日志",
    "sv.btn_save": "存档",
    "sv.btn_load": "读档",
    "sv.btn_cancel": "取消存档",
    "sv.btn_check": "检查异常文件",
    "sv.help": (
        "操作说明\n\n"
        "【存档】\n"
        "1. 选中一个存档位\n"
        "2. 点击「存档」\n"
        "3. 在游戏导出对话框中粘贴路径并保存\n\n"
        "【读档】\n"
        "1. 选中一个存档位\n"
        "2. 点击「读档」\n"
        "3. 在游戏导入中粘贴 (Ctrl+V)\n\n"
        "【备注】\n"
        "在右侧输入框填写，自动保存到本地。\n\n"
        "【检查异常文件】\n"
        "查看不合规文件。\n"
    ),

    # ---- 配置页 ----
    "st.lang": "Language",
    "st.lang_zh": "中文",
    "st.lang_en": "English",
    "st.browser": "浏览器",
    "st.browser_default": "使用系统默认",
    "st.game_dir": "游戏目录（Web 服务根目录）",
    "st.port": "固定端口",
    "st.port_auto": "留空 = 自动",
    "st.home_slot": "首页指定存档",
    "st.about": "关于",
    "st.hint": "所有修改自动保存到：{path}",

    # ---- 提示与错误 ----
    "err.launch_fail": "启动失败",
    "err.port_invalid": "端口必须是 1-65535 之间的数字，或留空自动选择。",
    "err.no_dir": "服务目录为空。请先在「配置」页设置游戏目录。",
    "err.dir_missing": "目录不存在：{dir}",
    "err.no_save": "所选存档为空，无法复制。",
    "err.no_saves": "存档库中还没有可用存档。",
    "dlg.save_new": "对 {slot} 进行存档操作？",
    "dlg.save_overwrite": "对 {slot} 进行存档操作？将覆盖现有存档。",
    "dlg.no_file": "{slot} 没有存档文件。",
    "dlg.copied_ok": "已复制 {slot} 的存档到剪贴板，可以导入到游戏中了。",
}

# ---------------- 英文字符串 ----------------
_EN = {
    # Tabs
    "tab.kgsm": "KGSM",
    "tab.game": "Launch Game",
    "tab.saves": "Save Management",
    "tab.settings": "Settings",

    # Common
    "ui.empty_short": "(empty)",
    "ui.browse": "Browse...",
    "ui.auto_port": "Empty = auto pick a free port",

    # ---- KGSM page ----
    "kgsm.heading": "KittensGame Save Manager",
    "kgsm.dir_none": "Game directory: not set",
    "kgsm.dir_set": "Game directory: {dir}",
    "kgsm.quick_title": "Quick Launch Game",
    "kgsm.quick_desc": "Start the local server rooted at the game directory "
                       "and open the game in your browser.",
    "kgsm.copy_title": "Copy Save & Launch Game",
    "kgsm.copy_desc": "Copy the save to the clipboard first, then start the "
                      "server and open the game. Paste (Ctrl+V) inside the "
                      "game to import.",
    "kgsm.mode_recent": "Latest Save",
    "kgsm.mode_slot": "Selected Save",
    "kgsm.cur_prefix": "Will copy: ",
    "kgsm.btn_run": "Run",
    "kgsm.first_use_q": "First time here?",
    "kgsm.btn_config": "Configure",
    "kgsm.download_1": "Download Game · Kittens Game (kitten-science)",
    "kgsm.download_2": "Download Game · Kittens Game (nuclear-unicorn)",

    # ---- Launch Game page ----
    "la.title": "Local Web Server (bound to 127.0.0.1 only)",
    "la.dir": "Server Directory",
    "la.port": "Port",
    "la.hint": "Unzip the downloaded game files into the game directory, "
               "then launch. The server only listens on this machine.",
    "la.log_title": "Server Log",
    "la.ready": "Ready: set the directory & port, then click "
                "\u201cLaunch & Open Browser\u201d.",
    "la.btn_start": "Launch & Open Browser",
    "la.btn_stop": "Stop Server",

    # ---- Save Management page ----
    "sv.title_slots": "Save Slots",
    "sv.title_log": "Output Log",
    "sv.btn_save": "Save",
    "sv.btn_load": "Load",
    "sv.btn_cancel": "Cancel Saving",
    "sv.btn_check": "Check Abnormal Files",
    "sv.help": (
        "Help\n\n"
        "[Save]\n"
        "1. Select a slot\n"
        "2. Click \u201cSave\u201d\n"
        "3. Paste the path into the game's Export dialog\n\n"
        "[Load]\n"
        "1. Select a slot\n"
        "2. Click \u201cLoad\u201d\n"
        "3. Paste (Ctrl+V) into the game's Import\n\n"
        "[Notes]\n"
        "Type in the entry boxes; saved automatically.\n\n"
        "[Check Abnormal Files]\n"
        "Inspect files not managed by this program.\n"
    ),

    # ---- Settings page ----
    "st.lang": "Language",
    "st.lang_zh": "中文",
    "st.lang_en": "English",
    "st.browser": "Browser",
    "st.browser_default": "Use system default",
    "st.game_dir": "Game Directory (web server root)",
    "st.port": "Fixed Port",
    "st.port_auto": "Empty = auto",
    "st.home_slot": "Home Save Slot",
    "st.about": "About",
    "st.hint": "All changes are saved automatically to: {path}",

    # ---- Prompts & errors ----
    "err.launch_fail": "Launch Failed",
    "err.port_invalid": "Port must be a number from 1 to 65535, "
                        "or left empty for auto.",
    "err.no_dir": "Server directory is empty. Set the game directory "
                  "in Settings first.",
    "err.dir_missing": "Directory does not exist: {dir}",
    "err.no_save": "The selected save is empty, nothing to copy.",
    "err.no_saves": "There are no saves available yet.",
    "dlg.save_new": "Save to {slot}?",
    "dlg.save_overwrite": "Save to {slot}? The existing save will be "
                          "overwritten.",
    "dlg.no_file": "{slot} has no save file.",
    "dlg.copied_ok": "The {slot} save was copied to the clipboard; "
                     "you can import it into the game now.",
}

STRINGS = {LANG_ZH: _ZH, LANG_EN: _EN}


class Translator:
    """界面文案翻译器。"""

    def __init__(self, lang=LANG_ZH):
        self.lang = lang if lang in STRINGS else LANG_ZH

    def t(self, key, **kwargs):
        table = STRINGS.get(self.lang, _ZH)
        text = table.get(key, _ZH.get(key, key))
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text
