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
    "kgsm.download": "下载游戏 · Kittens Game（GitHub）",

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
    "sv.slot_prefix": "存档",
    "sv.btn_save": "存档",
    "sv.btn_load": "复制存档",
    "sv.btn_cancel": "取消存档",
    "sv.btn_rename": "改名",
    "sv.btn_refresh": "刷新",
    "sv.btn_check": "检查异常文件",
    "sv.help": (
        "操作说明\n\n"
        "【自动存档】\n"
        "用 KGSM 启动游戏（页面已连接）后，点「自动存档」\n"
        "即可把游戏当前存档直接写入选中槽位。\n\n"
        "【手动存档】\n"
        "弹窗上部：把游戏导出的存档文件放入临时文件夹，\n"
        "检测到后自动保存并关闭；\n"
        "下部：粘贴存档文本后点「确定」。\n\n"
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
    "st.browser_eff": "当前系统默认浏览器",
    "st.browser_auto": "未检测到（将使用系统关联打开）",
    "st.hint": "所有修改自动保存到：{path}",

    # ---- 存档（自动/手动） ----
    "sv.btn_auto_save": "自动存档",
    "sv.btn_manual_save": "手动存档",
    "msg.auto_no_conn": "自动存档需要先用 KGSM 启动游戏（需要本地服务与存档桥）。",
    "msg.auto_no_page": "游戏页面尚未连接，请确认已在浏览器打开游戏后重试。",
    "msg.auto_overwrite": "自动存档到 {slot}？将覆盖现有存档。",
    "msg.auto_saved": "已自动存档: {dest}",
    "msg.auto_timeout": "自动存档超时：游戏页面没有响应。",
    "msg.manual_title": "手动存档",
    "msg.manual_tip": "把存档文件导入此文件夹",
    "msg.manual_hint": "上方：把游戏导出的存档文件放入临时文件夹，检测到存档后自动保存并关闭窗口。\n下方：也可以直接把存档文本粘贴进输入框，点「确定」保存；关闭窗口表示取消操作。",
    "msg.manual_detected": "检测到存档",
    "msg.manual_detected_saved": "检测到存档，已保存到 {slot}。",
    "msg.btn_ok": "确定",
    "msg.btn_close": "关闭",
    "msg.btn_copy_path": "复制路径",
    "msg.path_copied": "已复制路径到剪贴板: {path}",
    "msg.paste_empty": "请先粘贴存档内容，或把存档文件放入临时文件夹。",
    "msg.saved_to": "已写入存档: {dest}",
    "msg.invalid_ask": "存档可能/疑似不合法，仍要保存吗？",
    "msg.invalid_skip": "已取消写入（存档疑似不合法）。",
    "msg.paste_invalid_file": "放入的存档可能/疑似不合法，仍要保存吗？",

    # ---- 自动读档 / 存档编辑 ----
    "sv.btn_auto_load": "自动读档",
    "msg.auto_load_ask": "自动读档将覆盖游戏当前进度并载入 {slot} 的存档，确认？",
    "msg.auto_load_sent": "已发送存档到游戏，页面将自动刷新载入。",
    "msg.auto_load_fail": "发送到游戏失败（页面未连接）。",
    "tab.editor": "修改存档",
    "ed.mode_file": "存档槽位（文件）",
    "ed.mode_live": "运行中的游戏（实时）",
    "ed.slot": "槽位",
    "ed.btn_open": "打开",
    "ed.btn_write": "写入",
    "ed.view_tree": "视图",
    "ed.view_source": "源码",
    "ed.no_slot": "请先选择一个有存档的槽位。",
    "ed.no_bridge": "实时模式需要游戏由 KGSM 启动并已连接。",
    "ed.loaded": "已载入存档: {name}",
    "ed.pulled": "已拉取游戏当前存档。",
    "ed.parse_err": "源码不是合法 JSON：{err}",
    "ed.saved": "已保存到 {dest}",
    "ed.backup": "已备份原存档: {path}",
    "ed.sent": "已发送到游戏，页面将刷新载入。",
    "ed.value_title": "修改数值",
    "ed.value_prompt": "输入新值（自动识别 JSON 类型，无法解析则存为字符串）：",
    "ed.invalid_value": "请输入 JSON 可解析的数值，或留空取消。",

    # ---- 下载游戏 ----
    "tab.download": "下载游戏",
    "dl.repo": "来源仓库（GitHub）",
    "dl.repo_author": "作者原版 · nuclear-unicorn/kittensgame",
    "dl.repo_community": "社区版 · kitten-science/kittensgame",
    "dl.version": "版本",
    "dl.version_tip": "默认 main（最新）即可；只有想玩旧版才切换到下方列出的标签版本。",
    "dl.refresh_versions": "刷新版本列表",
    "dl.mirror": "下载源",
    "dl.mirror_tip": "github.com = 从 GitHub 官网直连下载；镜像站用于官网被墙/慢时加速，内容相同。",
    "dl.mirror_direct": "GitHub 直连",
    "dl.dir": "存放目录",
    "dl.dir_default_tip": "默认：程序目录\\KittensGame",
    "dl.set_service_dir": "下载完成后，把该目录设为服务目录（游戏目录）",
    "dl.btn_download": "开始下载",
    "dl.log": "下载日志",
    "dl.busy": "正在下载，请稍候…",
    "dl.version_fail": "获取版本列表失败：{e}",
    "dl.version_pick": "请选择一个版本。",
    "dl.dir_missing": "存放目录为空或不合法：{dir}",
    "dl.dir_has_content": "目标目录已存在且非空：{dir}\n继续将清空其中内容，确定继续吗？",
    "dl.downloading": "正在下载（{mb:.1f} MB）: {url}",
    "dl.downloaded": "下载完成：{file}（{mb:.1f} MB）",
    "dl.unzip": "正在解压…",
    "dl.no_index": "解压后未在目录根找到 index.html（{dir}）",
    "dl.done": "下载完成，游戏目录：{dir}",
    "dl.service_set": "已把该目录设置为服务目录（游戏目录）。",
    "dl.cleanup": "已清理临时文件。",
    "dl.fail": "下载失败：{e}",
    "dl.not_a_zip": "下载内容不是有效的 zip 包（可能版本不存在或镜像异常）。",
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
    "msg.temp_path": "临时文件夹: {path}",
    "msg.file_renamed": "存档文件已改名: {old} → {new}",
    "msg.refreshed": "已刷新存档库。",
    "msg.cancel_pending": "正在取消存档操作...",
    "msg.no_operation": "当前没有进行中的存档操作",
    "msg.busy": "已有存档操作进行中，请先取消或等待完成",
    "msg.user_cancel": "用户取消存档操作",
    "msg.save_start": "开始对 {slot} 进行存档操作",
    "msg.copied_path": "已复制路径到剪贴板: {path}",
    "msg.export_hint": "请在游戏中点击 Options → Export，粘贴此路径并保存为 .txt 文件。",
    "msg.save_success": "成功存档: {src} → {dest}（已覆盖写入）",
    "msg.process_fail": "处理存档失败: {e}",
    "msg.read_fail": "读取存档失败: {e}",
    "msg.copied_save": "已将 {slot} 的存档内容复制到剪贴板",
    "msg.load_hint": "请打开游戏，点击 Options → Import，粘贴 (Ctrl+V) 并确认。",
    "msg.import_hint": "游戏打开后点击 Options → Import，粘贴 (Ctrl+V) 即可导入。",
    "msg.check_start": "开始检查异常文件...",
    "msg.lib_abnormal": "【存档库】发现以下不合规文件（程序不会处理）：",
    "msg.lib_clean": "【存档库】没有不合规文件。",
    "msg.lib_empty": "【存档库】以下存档文件内容为空：",
    "msg.temp_files": "【临时文件夹】发现以下文件（程序不会处理）：",
    "msg.temp_clean": "【临时文件夹】为空。",
    "msg.check_tail": "这些文件不会被程序管理，请自行判断是否转移或删除。",
    "msg.item": "  - {f}",
    "msg.monitor_timeout": "存档超时：未在5分钟内检测到新文件，请确保已正确导出存档。",
    "msg.monitor_error": "监控出错: {e}",
    "err.file_empty": "存档文件为空",
    "err.file_too_large": "存档文件过大（{size} 字节）",
    "err.export_empty": "导出文件为空",
    "err.export_content_empty": "导出文件内容为空",
    "dlg.clipboard_title": "剪贴板错误",
    "err.save_fail": "存档失败",
    "err.load_fail": "读档失败",

    # ---- 提示与错误 ----
    "err.launch_fail": "启动失败",
    "err.port_invalid": "端口必须是 1-65535 之间的数字，或留空自动选择。",
    "err.no_dir": "服务目录为空。请先在「配置」页设置游戏目录。",
    "err.dir_missing": "目录不存在：{dir}",
    "err.no_save": "所选存档为空，无法复制。",
    "err.no_saves": "存档库中还没有可用存档。",
    "dlg.rename_title": "槽位改名",
    "dlg.rename_prompt": "输入槽位新名字（同时用于存档文件名，如 名字_1.kgsav）：",
    "err.name_invalid": "名字不能为空，且不能包含 \\ / : * ? \" < > | 等字符。",
    "err.rename_need_file": "该槽位还没有存档文件，请先「存档」一次后再改名。",
    "err.name_file_exists": "目标存档文件已存在，改名中止：{file}",
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
    "kgsm.download": "Download Game · Kittens Game (GitHub)",

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
    "sv.slot_prefix": "Save",
    "sv.btn_save": "Save",
    "sv.btn_load": "Copy Save",
    "sv.btn_cancel": "Cancel Saving",
    "sv.btn_rename": "Rename",
    "sv.btn_refresh": "Refresh",
    "sv.btn_check": "Check Abnormal Files",
    "sv.help": (
        "Help\n\n"
        "[Auto Save]\n"
        "Launch the game via KGSM (page connected), then click "
        "\u201cAuto Save\u201d to write the game's current save directly "
        "into the selected slot.\n\n"
        "[Manual Save]\n"
        "Top: drop the exported save file into the temp folder; it is saved "
        "automatically and the window closes when detected.\n"
        "Bottom: paste the save text and click OK.\n\n"
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
    "st.browser_eff": "Current system default browser",
    "st.browser_auto": "not detected (will open via OS association)",
    "st.hint": "All changes are saved automatically to: {path}",

    # ---- Save (auto / manual) ----
    "sv.btn_auto_save": "Auto Save",
    "sv.btn_manual_save": "Manual Save",
    "msg.auto_no_conn": "Auto-save requires the game to be launched via "
                        "KGSM (local server and save bridge needed).",
    "msg.auto_no_page": "The game page is not connected yet. Open the game "
                        "in the browser and try again.",
    "msg.auto_overwrite": "Auto-save to {slot}? The existing save will be "
                          "overwritten.",
    "msg.auto_saved": "Auto-saved: {dest}",
    "msg.auto_timeout": "Auto-save timed out: no response from the game.",
    "msg.manual_title": "Manual Save",
    "msg.manual_tip": "Import the save file into this folder",
    "msg.manual_hint": "Top: drop the exported save file into the temp "
                       "folder; once detected it will be saved and this "
                       "window closes.\nBottom: alternatively paste the save "
                       "text into the box and click OK; closing the window "
                       "cancels the operation.",
    "msg.manual_detected": "Save file detected",
    "msg.manual_detected_saved": "Save detected and stored to {slot}.",
    "msg.btn_ok": "OK",
    "msg.btn_close": "Close",
    "msg.btn_copy_path": "Copy Path",
    "msg.path_copied": "Path copied to clipboard: {path}",
    "msg.paste_empty": "Paste the save text first, or drop a save file into "
                       "the temp folder.",
    "msg.saved_to": "Save written: {dest}",
    "msg.invalid_ask": "The save may/might be invalid. Save anyway?",
    "msg.invalid_skip": "Write cancelled (the save looks invalid).",
    "msg.paste_invalid_file": "The dropped save may/might be invalid. "
                              "Save anyway?",

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
    "ed.btn_open": "Open",
    "ed.btn_write": "Write",
    "ed.view_tree": "View",
    "ed.view_source": "Source",
    "ed.no_slot": "Select a slot that has a save file first.",
    "ed.no_bridge": "Live mode needs the game launched via KGSM and "
                    "connected.",
    "ed.loaded": "Save loaded: {name}",
    "ed.pulled": "Current game save pulled.",
    "ed.parse_err": "The source is not valid JSON: {err}",
    "ed.saved": "Saved to {dest}",
    "ed.backup": "Original save backed up: {path}",
    "ed.sent": "Sent to the game; the page will reload to load it.",
    "ed.value_title": "Edit Value",
    "ed.value_prompt": "Enter a new value (JSON type auto-detected; falls "
                       "back to a string if unparsable):",
    "ed.invalid_value": "Enter a JSON-parsable value, or leave empty to "
                        "cancel.",

    # ---- Download game ----
    "tab.download": "Download Game",
    "dl.repo": "Source repository (GitHub)",
    "dl.repo_author": "Author's original · nuclear-unicorn/kittensgame",
    "dl.repo_community": "Community fork · kitten-science/kittensgame",
    "dl.version": "Version",
    "dl.version_tip": "main (latest) is fine for normal use; switch to a "
                      "tagged version only to play an older build.",
    "dl.refresh_versions": "Refresh versions",
    "dl.mirror": "Download source",
    "dl.mirror_tip": "github.com downloads directly from GitHub. Mirrors "
                     "help when GitHub is blocked or slow; content is the "
                     "same.",
    "dl.mirror_direct": "GitHub direct",
    "dl.dir": "Destination folder",
    "dl.dir_default_tip": "Default: program folder\\KittensGame",
    "dl.set_service_dir": "After download, use this folder as the service "
                          "(game) directory",
    "dl.btn_download": "Start Download",
    "dl.log": "Download Log",
    "dl.busy": "Downloading, please wait…",
    "dl.version_fail": "Failed to list versions: {e}",
    "dl.version_pick": "Choose a version first.",
    "dl.dir_missing": "Destination folder is empty or invalid: {dir}",
    "dl.dir_has_content": "The destination already exists and is not empty: "
                          "{dir}\nContinuing will clear its contents. "
                          "Continue?",
    "dl.downloading": "Downloading ({mb:.1f} MB): {url}",
    "dl.downloaded": "Downloaded: {file} ({mb:.1f} MB)",
    "dl.unzip": "Extracting…",
    "dl.no_index": "No index.html found at the folder root after extraction "
                    "({dir})",
    "dl.done": "Download complete. Game folder: {dir}",
    "dl.service_set": "This folder has been set as the service (game) "
                      "directory.",
    "dl.cleanup": "Temporary files cleaned up.",
    "dl.fail": "Download failed: {e}",
    "dl.not_a_zip": "The downloaded content is not a valid zip (the version "
                    "may not exist or the mirror failed).",
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
    "msg.temp_path": "Temp folder: {path}",
    "msg.file_renamed": "Save file renamed: {old} → {new}",
    "msg.refreshed": "Save library refreshed.",
    "msg.cancel_pending": "Cancelling the save operation...",
    "msg.no_operation": "No save operation in progress",
    "msg.busy": "A save operation is in progress; cancel it or wait.",
    "msg.user_cancel": "Save operation cancelled by the user",
    "msg.save_start": "Saving to {slot}...",
    "msg.copied_path": "Path copied to clipboard: {path}",
    "msg.export_hint": "In the game click Options → Export, paste this path "
                       "and save it as a .txt file.",
    "msg.save_success": "Save OK: {src} → {dest} (overwritten)",
    "msg.process_fail": "Failed to process the save: {e}",
    "msg.read_fail": "Failed to read the save: {e}",
    "msg.copied_save": "{slot} save copied to the clipboard",
    "msg.load_hint": "Open the game, click Options → Import, paste (Ctrl+V) "
                     "and confirm.",
    "msg.import_hint": "When the game opens, click Options → Import and paste "
                       "(Ctrl+V) to import.",
    "msg.check_start": "Checking for abnormal files...",
    "msg.lib_abnormal": "[Save library] abnormal files found "
                        "(not managed by the program):",
    "msg.lib_clean": "[Save library] no abnormal files.",
    "msg.lib_empty": "[Save library] the following save files are empty:",
    "msg.temp_files": "[Temp folder] files found (not managed by the "
                      "program):",
    "msg.temp_clean": "[Temp folder] is empty.",
    "msg.check_tail": "These files are not managed by the program; decide "
                      "whether to move or delete them.",
    "msg.item": "  - {f}",
    "msg.monitor_timeout": "Timeout: no new file detected within 5 minutes. "
                           "Make sure the save was exported correctly.",
    "msg.monitor_error": "Monitor error: {e}",
    "err.file_empty": "The save file is empty",
    "err.file_too_large": "The save file is too large ({size} bytes)",
    "err.export_empty": "The exported file is empty",
    "err.export_content_empty": "The exported file has no content",
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
    "err.no_save": "The selected save is empty, nothing to copy.",
    "err.no_saves": "There are no saves available yet.",
    "dlg.rename_title": "Rename Slot",
    "dlg.rename_prompt": "Enter the new slot name (also used in save "
                         "filenames, e.g. name_1.kgsav):",
    "err.name_invalid": "The name must not be empty and cannot contain "
                        "\\ / : * ? \" < > | characters.",
    "err.rename_need_file": "This slot has no save file yet. Save once "
                            "before renaming.",
    "err.name_file_exists": "Target save file already exists, rename "
                            "aborted: {file}",
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
