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
    "kgsm.guide_title": "新手引导",
    "kgsm.step_doc": "阅读离线文档 · 快速开始",
    "kgsm.link_doc": "离线文档",
    "kgsm.step_dl": "下载游戏",
    "kgsm.step_cfg": "配置程序",
    "kgsm.step_run": "启动游戏",
    "kgsm.guide_hint": "提示：也可用左侧按钮或顶部标签页随时切换页面。按 1→4 完成设置后即可开始游戏。",

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
    "sv.col_time": "时间",
    "sv.col_note": "备注",
    "sv.slot_prefix": "存档",
    "sv.btn_load": "复制存档",
    "sv.btn_rename": "改名",
    "sv.btn_refresh": "刷新",
    "sv.btn_check": "检查异常文件",
    "sv.help": (
        "操作说明\n\n"
        "【自动存档】\n"
        "用 KGSM 启动游戏（页面已连接）后，点「自动存档」\n"
        "即可把游戏当前存档直接写入选中槽位。\n\n"
        "【手动导入】\n"
        "点「浏览选择存档文件」选游戏导出的存档文件，\n"
        "或把存档文本粘贴到输入框后点「确定」。\n\n"
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
    "st.home_slot": "默认存档位",
    "st.about": "关于",
    "st.browser_eff": "当前系统默认浏览器",
    "st.browser_auto": "未检测到（将使用系统关联打开）",
    "st.hint": "所有修改自动保存到：{path}",

    # ---- 眉题（等宽大写，参考设计里的 editorial 标记） ----
    "eb.kgsm": "KGSM · 开始使用",
    "eb.game": "LAUNCH · 启动游戏",
    "eb.saves": "SAVES · 存档管理",
    "eb.editor": "EDITOR · 修改存档",
    "eb.download": "DOWNLOAD · 下载游戏",
    "eb.settings": "SETTINGS · 配置",

    # ---- 存档（自动/手动） ----
    "sv.btn_auto_save": "自动存档",
    "sv.btn_manual_save": "手动导入",
    "msg.auto_no_conn": "自动存档需要先用 KGSM 启动游戏（需要本地服务与存档桥）。",
    "msg.auto_no_page": "游戏页面尚未连接，请确认已在浏览器打开游戏后重试。",
    "msg.auto_overwrite": "自动存档到 {slot}？将覆盖现有存档。",
    "msg.auto_saved": "已自动存档: {dest}",
    "msg.auto_timeout": "自动存档超时：游戏页面没有响应。",
    "msg.manual_title": "手动导入存档",
    "msg.manual_tip": "手动导入",
    "msg.manual_pick": "浏览选择存档文件…",
    "msg.manual_pick_title": "选择要导入的存档文件",
    "msg.manual_hint": "点左侧按钮选择游戏导出的存档文件；也可以把存档文本直接粘贴到下面的输入框，再点「确定」。",
    "msg.manual_library_hint": "存档属于哪个槽位由文件名决定（名字_槽位号.kgsav）。如需调整，可在文件管理器中打开存档库文件夹 {path} 手动改名，然后点界面上的「刷新」按钮刷新存档列表。",
    "msg.library_folder": "存档库文件夹:",
    "msg.manual_imported": "已把 {name} 导入到 {slot}。",
    "msg.filetype_save": "存档文件",
    "msg.filetype_all": "所有文件",
    "msg.btn_ok": "确定",
    "msg.btn_close": "关闭",
    "msg.btn_copy_path": "复制路径",
    "msg.path_copied": "已复制路径到剪贴板: {path}",
    "msg.paste_empty": "请先粘贴存档内容，或点「浏览选择存档文件」选一个文件。",
    "msg.saved_to": "已写入存档: {dest}",
    "msg.invalid_ask": "存档可能/疑似不合法，仍要保存吗？",

    # ---- 自动读档 / 存档编辑 ----
    "sv.btn_auto_load": "自动读档",
    "msg.auto_load_ask": "自动读档将覆盖游戏当前进度并载入 {slot} 的存档，确认？",
    "msg.auto_load_sent": "已发送存档到游戏，页面将自动刷新载入。",
    "msg.auto_load_fail": "发送到游戏失败（页面未连接）。",
    "tab.editor": "修改存档",
    "ed.mode_file": "存档槽位（文件）",
    "ed.mode_live": "运行中的游戏（实时）",
    "ed.slot": "槽位",
    "ed.source": "数据源",
    "ed.col_key": "键",
    "ed.col_value": "值",
    "ed.btn_open": "打开",
    "ed.btn_write": "写入",
    "ed.view_tree": "视图",
    "ed.view_source": "源码",
    "ed.no_slot": "请先选择一个有存档的槽位。",
    "ed.no_bridge": "实时模式需要游戏由 KGSM 启动并已连接。",
    "ed.loaded": "已载入存档: {name}",
    "ed.pulled": "已拉取游戏当前存档。",
    "ed.pulling": "正在向游戏页面请求当前存档……",
    "ed.parse_err": "源码不是合法 JSON：{err}",
    "ed.saved": "已保存到 {dest}",
    "ed.backup": "已备份原存档: {path}",
    "ed.sent": "已发送到游戏，页面将刷新载入。",
    "ed.value_title": "修改数值",
    "ed.value_prompt": "输入新值（自动识别 JSON 类型，无法解析则存为字符串）：",

    # ---- 下载游戏 ----
    "tab.download": "下载游戏",
    "dl.repo": "来源仓库（GitHub）",
    "dl.repo_author": "作者原版 · nuclear-unicorn/kittensgame",
    "dl.repo_community": "社区版 · kitten-science/kittensgame",
    "dl.version": "版本",
    "dl.refresh_versions": "刷新版本列表",
    "dl.mirror": "下载源",
    "dl.dir": "存放目录",
    "dl.dir_default_tip": "默认：程序目录\\KittensGame",
    "dl.set_service_dir": "下载完成后，把该目录设为服务目录（游戏目录）",
    "dl.keep_temp": "下载完成后删除临时下载文件",
    "dl.btn_download": "开始下载",
    "dl.btn_test": "测试连通性",
    "dl.testing": "正在测试各下载源…",
    "dl.log": "下载日志",
    "dl.version_fail": "获取版本列表失败：{e}",
    "dl.version_pick": "请选择一个版本。",
    "dl.dir_missing": "存放目录为空或不合法：{dir}",
    "dl.dir_has_content": "目标目录已存在且非空：{dir}\n继续将清空其中内容，确定继续吗？",
    "dl.unzip": "正在解压…",
    "dl.done": "下载完成，游戏目录：{dir}",
    "dl.service_set": "已把该目录设置为服务目录（游戏目录）。",
    "dl.fail": "下载失败：{e}",
    "dl.cancel": "已取消下载。",

    # ---- 日志/标签与消息（输出内容） ----
    "tag.cancel": "取消存档",
    "tag.save": "执行存档",
    "tag.done": "完成存档",
    "tag.load": "读档操作",
    "tag.check": "检查异常",
    "tag.rename": "改名",
    "tag.refresh": "刷新",
    "tag.error": "错误",
    "tag.timeout": "超时",
    "tag.start": "启动",
    "tag.stop": "停止",
    "tag.server": "服务",
    "tag.browser": "打开浏览器",
    "tag.download": "下载",
    "tag.bridge": "桥",
    "msg.clipboard_fail": "写入剪贴板失败: {e}",
    "msg.server_stopped": "服务已停止。",
    "msg.server_restart": "检测到运行中的服务，重启以应用当前设置",
    "msg.server_fail": "启动失败: {e}",
    "msg.server_started": "服务已启动: {url}",
    "msg.server_dir": "服务目录: {dir}",
    "msg.server_local": "仅监听 127.0.0.1，只有本机可以访问。",
    "msg.browser_opened": "已在浏览器新窗口打开（{how}）。",
    "msg.browser_fail": "打开浏览器失败，请手动访问: {url}",
    "msg.app_start": "程序启动",
    "msg.library_path": "存档库: {path}",
    "msg.file_renamed": "存档文件已改名: {old} → {new}",
    "msg.refreshed": "已刷新存档库。",
    "msg.user_cancel": "用户取消存档操作",
    "msg.save_start": "开始对 {slot} 进行存档操作",
    "msg.process_fail": "处理存档失败: {e}",
    "msg.crash_hint": "详细信息已写入运行日志: {path}",
    "msg.port_auto_saved": "本次使用自动分配的端口: {port}（已记为固定端口）",
    "msg.port_busy_fallback": "固定端口 {port} 已被占用，本次改用自动分配的端口",
    "msg.slot_backup": "覆盖前已备份原存档: {path}",
    "msg.backup_fail": "备份原存档失败: {e}",
    "msg.auto_load_sending": "正在把 {slot} 发送到游戏页面，等待确认……",
    "msg.auto_load_unconfirmed": "存档已发送，但游戏页面未确认写入结果；请确认游戏内是否已载入。",
    "msg.read_fail": "读取存档失败: {e}",
    "msg.copied_save": "已将 {slot} 的存档内容复制到剪贴板",
    "msg.load_hint": "请打开游戏，点击 Options → Import，粘贴 (Ctrl+V) 并确认。",
    "msg.check_start": "开始检查异常文件...",
    "msg.lib_abnormal": "【存档库】发现以下不合规文件（程序不会处理）：",
    "msg.lib_clean": "【存档库】没有不合规文件。",
    "msg.lib_empty": "【存档库】以下存档文件内容为空：",
    "msg.check_tail": "这些文件不会被程序管理，请自行判断是否转移或删除。",
    "msg.item": "  - {f}",
    "err.file_empty": "存档文件为空",
    "err.file_too_large": "存档文件过大（{size} 字节）",
    "dlg.clipboard_title": "剪贴板错误",
    "err.save_fail": "存档失败",
    "err.load_fail": "读档失败",

    # ---- 提示与错误 ----
    "err.launch_fail": "启动失败",
    "err.port_invalid": "端口必须是 1-65535 之间的数字，或留空自动选择。",
    "err.no_dir": "服务目录为空。请先在「配置」页设置游戏目录。",
    "err.dir_missing": "目录不存在：{dir}",
    "dlg.rename_title": "槽位改名",
    "dlg.rename_prompt": "输入槽位新名字（同时用于存档文件名，如 名字_1.kgsav）：",
    "err.name_invalid": "名字不能为空，且不能包含 \\ / : * ? \" < > | 等字符。",
    "err.rename_need_file": "该槽位还没有存档文件，请先「存档」一次后再改名。",
    "err.name_file_exists": "目标存档文件已存在，改名中止：{file}",
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
    "kgsm.guide_title": "Getting Started",
    "kgsm.step_doc": "Read the offline guide · Quick start",
    "kgsm.link_doc": "Offline guide",
    "kgsm.step_dl": "Download the game",
    "kgsm.step_cfg": "Configure",
    "kgsm.step_run": "Launch the game",
    "kgsm.guide_hint": "Tip: use the left buttons or the top tabs to switch "
                       "pages anytime. Follow 1→4 to get started.",

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
    "sv.col_time": "Time",
    "sv.col_note": "Note",
    "sv.slot_prefix": "Save",
    "sv.btn_load": "Copy Save",
    "sv.btn_rename": "Rename",
    "sv.btn_refresh": "Refresh",
    "sv.btn_check": "Check Abnormal Files",
    "sv.help": (
        "Help\n\n"
        "[Auto Save]\n"
        "Launch the game via KGSM (page connected), then click "
        "\u201cAuto Save\u201d to write the game's current save directly "
        "into the selected slot.\n\n"
        "[Manual Import]\n"
        "Click \u201cBrowse for a save file\u201d to pick the save file exported "
        "by the game, or paste the save text and click OK.\n\n"
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
    "st.home_slot": "Default Save Slot",
    "st.about": "About",
    "st.browser_eff": "Current system default browser",
    "st.browser_auto": "not detected (will open via OS association)",
    "st.hint": "All changes are saved automatically to: {path}",

    # ---- Eyebrows (mono uppercase labels from the reference design) ----
    "eb.kgsm": "KGSM · Getting started",
    "eb.game": "LAUNCH · Game",
    "eb.saves": "SAVES · Save management",
    "eb.editor": "EDITOR · Save editor",
    "eb.download": "DOWNLOAD · Game files",
    "eb.settings": "SETTINGS · Configuration",

    # ---- Save (auto / manual) ----
    "sv.btn_auto_save": "Auto Save",
    "sv.btn_manual_save": "Manual Import",
    "msg.auto_no_conn": "Auto-save requires the game to be launched via "
                        "KGSM (local server and save bridge needed).",
    "msg.auto_no_page": "The game page is not connected yet. Open the game "
                        "in the browser and try again.",
    "msg.auto_overwrite": "Auto-save to {slot}? The existing save will be "
                          "overwritten.",
    "msg.auto_saved": "Auto-saved: {dest}",
    "msg.auto_timeout": "Auto-save timed out: no response from the game.",
    "msg.manual_title": "Import a Save",
    "msg.manual_tip": "Manual import",
    "msg.manual_pick": "Browse for a save file...",
    "msg.manual_pick_title": "Select the save file to import",
    "msg.manual_hint": "Use the button on the left to pick the save file "
                       "exported by the game, or paste the save text into the "
                       "box below and click OK.",
    "msg.manual_library_hint": "Which slot a save belongs to is decided by its "
                               "file name (name_slotnumber.kgsav). To change "
                               "it, open the save library folder {path} in your "
                               "file manager, rename the file, then press "
                               "Refresh in the interface.",
    "msg.library_folder": "Save library folder:",
    "msg.manual_imported": "Imported {name} into {slot}.",
    "msg.filetype_save": "Save files",
    "msg.filetype_all": "All files",
    "msg.btn_ok": "OK",
    "msg.btn_close": "Close",
    "msg.btn_copy_path": "Copy Path",
    "msg.path_copied": "Path copied to clipboard: {path}",
    "msg.paste_empty": "Paste the save text first, or use “Browse for a save "
                       "file” to pick one.",
    "msg.saved_to": "Save written: {dest}",
    "msg.invalid_ask": "The save may/might be invalid. Save anyway?",

    # ---- Auto load / save editor ----
    "sv.btn_auto_load": "Auto Load",
    "msg.auto_load_ask": "Auto-load will overwrite the current in-game "
                         "progress with the {slot} save. Continue?",
    "msg.auto_load_sent": "Save sent to the game; the page will reload to "
                          "load it.",
    "msg.auto_load_fail": "Failed to send to the game (page not connected).",
    "tab.editor": "Edit Save",
    "ed.mode_file": "Save slot (file)",
    "ed.mode_live": "Running game (live)",
    "ed.slot": "Slot",
    "ed.source": "Data Source",
    "ed.col_key": "Key",
    "ed.col_value": "Value",
    "ed.btn_open": "Open",
    "ed.btn_write": "Write",
    "ed.view_tree": "View",
    "ed.view_source": "Source",
    "ed.no_slot": "Select a slot that has a save file first.",
    "ed.no_bridge": "Live mode needs the game launched via KGSM and "
                    "connected.",
    "ed.loaded": "Save loaded: {name}",
    "ed.pulled": "Current game save pulled.",
    "ed.pulling": "Requesting the current save from the game page...",
    "ed.parse_err": "The source is not valid JSON: {err}",
    "ed.saved": "Saved to {dest}",
    "ed.backup": "Original save backed up: {path}",
    "ed.sent": "Sent to the game; the page will reload to load it.",
    "ed.value_title": "Edit Value",
    "ed.value_prompt": "Enter a new value (JSON type auto-detected; falls "
                       "back to a string if unparsable):",

    # ---- Download game ----
    "tab.download": "Download Game",
    "dl.repo": "Source repository (GitHub)",
    "dl.repo_author": "Author's original · nuclear-unicorn/kittensgame",
    "dl.repo_community": "Community fork · kitten-science/kittensgame",
    "dl.version": "Version",
    "dl.refresh_versions": "Refresh versions",
    "dl.mirror": "Download source",
    "dl.dir": "Destination folder",
    "dl.dir_default_tip": "Default: program folder\\KittensGame",
    "dl.set_service_dir": "After download, use this folder as the service "
                          "(game) directory",
    "dl.keep_temp": "Delete temporary download files after completion",
    "dl.btn_download": "Start Download",
    "dl.btn_test": "Test Connectivity",
    "dl.testing": "Testing each source…",
    "dl.log": "Download Log",
    "dl.version_fail": "Failed to list versions: {e}",
    "dl.version_pick": "Choose a version first.",
    "dl.dir_missing": "Destination folder is empty or invalid: {dir}",
    "dl.dir_has_content": "The destination already exists and is not empty: "
                          "{dir}\nContinuing will clear its contents. "
                          "Continue?",
    "dl.unzip": "Extracting…",
    "dl.done": "Download complete. Game folder: {dir}",
    "dl.service_set": "This folder has been set as the service (game) "
                      "directory.",
    "dl.fail": "Download failed: {e}",
    "dl.cancel": "Download cancelled.",

    # ---- Log tags & messages (output) ----
    "tag.cancel": "Cancel",
    "tag.save": "Saving",
    "tag.done": "Save Complete",
    "tag.load": "Loading",
    "tag.check": "Check",
    "tag.rename": "Rename",
    "tag.refresh": "Refresh",
    "tag.error": "Error",
    "tag.timeout": "Timeout",
    "tag.start": "Start",
    "tag.stop": "Stop",
    "tag.server": "Server",
    "tag.browser": "Browser",
    "tag.download": "Download",
    "tag.bridge": "Bridge",
    "msg.clipboard_fail": "Failed to write clipboard: {e}",
    "msg.server_stopped": "Server stopped.",
    "msg.server_restart": "A server is running; restarting to apply settings.",
    "msg.server_fail": "Failed to start: {e}",
    "msg.server_started": "Server started: {url}",
    "msg.server_dir": "Server directory: {dir}",
    "msg.server_local": "Listening on 127.0.0.1 only; "
                        "accessible only on this machine.",
    "msg.browser_opened": "Opened in a new browser window ({how}).",
    "msg.browser_fail": "Failed to open the browser; visit manually: {url}",
    "msg.app_start": "Application started",
    "msg.library_path": "Save library: {path}",
    "msg.file_renamed": "Save file renamed: {old} → {new}",
    "msg.refreshed": "Save library refreshed.",
    "msg.user_cancel": "Save operation cancelled by the user",
    "msg.save_start": "Saving to {slot}...",
    "msg.process_fail": "Failed to process the save: {e}",
    "msg.crash_hint": "Details were written to the run log: {path}",
    "msg.port_auto_saved": "Using an automatically assigned port for this run: "
                           "{port} (saved as the fixed port)",
    "msg.port_busy_fallback": "The fixed port {port} is already in use; using "
                              "an automatically assigned port for this run",
    "msg.slot_backup": "Existing save backed up before overwrite: {path}",
    "msg.backup_fail": "Failed to back up the existing save: {e}",
    "msg.auto_load_sending": "Sending {slot} to the game page, waiting for "
                             "confirmation...",
    "msg.auto_load_unconfirmed": "The save was sent, but the game page did not "
                                 "confirm the result; please check in the game "
                                 "whether it loaded.",
    "msg.read_fail": "Failed to read the save: {e}",
    "msg.copied_save": "{slot} save copied to the clipboard",
    "msg.load_hint": "Open the game, click Options → Import, paste (Ctrl+V) "
                     "and confirm.",
    "msg.check_start": "Checking for abnormal files...",
    "msg.lib_abnormal": "[Save library] abnormal files found "
                        "(not managed by the program):",
    "msg.lib_clean": "[Save library] no abnormal files.",
    "msg.lib_empty": "[Save library] the following save files are empty:",
    "msg.check_tail": "These files are not managed by the program; decide "
                      "whether to move or delete them.",
    "msg.item": "  - {f}",
    "err.file_empty": "The save file is empty",
    "err.file_too_large": "The save file is too large ({size} bytes)",
    "dlg.clipboard_title": "Clipboard Error",
    "err.save_fail": "Save Failed",
    "err.load_fail": "Load Failed",

    # ---- Prompts & errors ----
    "err.launch_fail": "Launch Failed",
    "err.port_invalid": "Port must be a number from 1 to 65535, "
                        "or left empty for auto.",
    "err.no_dir": "Server directory is empty. Set the game directory "
                  "in Settings first.",
    "err.dir_missing": "Directory does not exist: {dir}",
    "dlg.rename_title": "Rename Slot",
    "dlg.rename_prompt": "Enter the new slot name (also used in save "
                         "filenames, e.g. name_1.kgsav):",
    "err.name_invalid": "The name must not be empty and cannot contain "
                        "\\ / : * ? \" < > | characters.",
    "err.rename_need_file": "This slot has no save file yet. Save once "
                            "before renaming.",
    "err.name_file_exists": "Target save file already exists, rename "
                            "aborted: {file}",
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

    def table(self):
        """当前语言的整张表（含外部翻译覆盖）。HTML 前端一次取走自行查表。"""
        return dict(STRINGS.get(self.lang, _ZH))


# ---------------- 外部翻译加载（程序目录 i18n/ 下的 json / po） ----------------

def _lang_from_stem(stem):
    s = stem.lower()
    return LANG_ZH if s.startswith("zh") else LANG_EN


def load_external_translations(folder):
    """把程序目录 i18n/ 下的外部翻译合并进 STRINGS。

    - *.json：可为 {lang: {key: text}}（lang∈zh/en），或单语言
      {key: text}（语言按文件名前缀推断，zh_*→zh，其余→en）
    - *.po：解析 msgid/msgstr；语言同样按文件名前缀推断
    :return: 已加载的文件名列表
    """
    import json
    loaded = []
    if not folder:
        return loaded
    try:
        import os
        if not os.path.isdir(folder):
            return loaded
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            stem, ext = os.path.splitext(name)
            lang = _lang_from_stem(stem)
            try:
                if ext.lower() == ".json":
                    with open(path, encoding="utf-8-sig") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        if any(k in data for k in (LANG_ZH, LANG_EN)):
                            for lng, table in data.items():
                                if (lng in (LANG_ZH, LANG_EN)
                                        and isinstance(table, dict)):
                                    STRINGS[lng].update(table)
                        else:
                            STRINGS[lang].update(
                                {str(k): str(v) for k, v in data.items()})
                    loaded.append(name)
                elif ext.lower() == ".po":
                    with open(path, encoding="utf-8-sig") as f:
                        table = _parse_po(f.read())
                    if table:
                        STRINGS[lang].update(table)
                    loaded.append(name)
            except Exception:
                continue
    except OSError:
        pass
    return loaded


def _parse_po(text):
    """极简 po 解析：msgid/msgstr 文本块（忽略复数与上下文）。"""
    table = {}
    key = None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            i += 1
            continue
        if line.startswith("msgid "):
            key = _po_string(line[len("msgid "):])
            i += 1
            while i < len(lines) and lines[i].strip().startswith('"'):
                key += _po_string(lines[i].strip())
                i += 1
            continue
        if line.startswith("msgstr "):
            val = _po_string(line[len("msgstr "):])
            i += 1
            while i < len(lines) and lines[i].strip().startswith('"'):
                val += _po_string(lines[i].strip())
                i += 1
            if key is not None and val:
                table[key] = val
            key = None
            continue
        i += 1
    return table


def _po_string(tok):
    try:
        import ast
        return ast.literal_eval(tok)
    except Exception:
        return tok.strip().strip('"')
