"""HTML 前端的界面端口与 API 实现。

`WebUiPort` 把 core 的界面请求变成事件（供页面轮询），并把需要阻塞等待的
对话框（confirm / ask_text）用 `threading.Event` 挂起，直到页面调用
`/api/answer` 作答。

`WebApi` 是页面能调用的方法集合：内部直接调用 `core` 的控制器，因此两个
前端的业务行为完全一致。
"""

import os
import threading
import time

from core.ui_port import UiPort

DIALOG_TIMEOUT = 300.0        # 对话框无人作答时的等待上限（秒）


class WebUiPort(UiPort):
    """把界面请求排进事件队列，交给浏览器页面渲染。"""

    def __init__(self, outbox):
        self.outbox = outbox              # 由 server 提供的线程安全事件缓冲
        self._pending = {}                # dialog_id -> {'event':Event,'ok':,'text':}
        self._next_dialog = 1
        self._lock = threading.Lock()

    # ---------------- 对话框 ----------------
    def _ask(self, kind, message, title="", initial=""):
        with self._lock:
            dialog_id = self._next_dialog
            self._next_dialog += 1
            slot = {"event": threading.Event(), "ok": False, "text": None}
            self._pending[dialog_id] = slot
        self.outbox.push({"type": "dialog", "dialog": kind, "id": dialog_id,
                          "message": message, "title": title,
                          "initial": initial})
        slot["event"].wait(DIALOG_TIMEOUT)
        with self._lock:
            self._pending.pop(dialog_id, None)
        return slot

    def answer(self, dialog_id, ok, text=None):
        """由 /api/answer 调用：回答一个挂起的对话框。"""
        with self._lock:
            slot = self._pending.get(int(dialog_id))
        if slot is None:
            return False
        slot["ok"] = bool(ok)
        slot["text"] = text
        slot["event"].set()
        return True

    def confirm(self, message, title=""):
        return bool(self._ask("confirm", message, title)["ok"])

    def ask_text(self, title, prompt, initial=""):
        slot = self._ask("text", prompt, title, initial)
        return slot["text"] if slot["ok"] else None

    def ask_directory(self, title, initial=""):
        slot = self._ask("text", self._pick_prompt(title), title, initial)
        return slot["text"] if slot["ok"] else None

    def ask_file(self, title, initial="", filetypes=None):
        slot = self._ask("text", self._pick_prompt(title), title, initial)
        return slot["text"] if slot["ok"] else None

    def _pick_prompt(self, title):
        """HTML 前端没有原生文件对话框，改为让用户粘贴路径。"""
        return title or ""

    # ---------------- 提示 ----------------
    def notify(self, message, title=""):
        self.outbox.push({"type": "toast", "level": "info",
                          "message": message, "title": title})

    def warn(self, message, title=""):
        self.outbox.push({"type": "toast", "level": "warn",
                          "message": message, "title": title})

    def fail(self, message, title=""):
        self.outbox.push({"type": "toast", "level": "error",
                          "message": message, "title": title})

    # ---------------- 日志与刷新 ----------------
    def log(self, message, tag=""):
        self.outbox.push({"type": "log", "channel": "saves",
                          "message": message, "tag": tag})

    def web_log(self, message, tag=""):
        self.outbox.push({"type": "log", "channel": "game",
                          "message": message, "tag": tag})

    def slots_changed(self):
        self.outbox.push({"type": "slots_changed"})

    # ---------------- 宿主能力 ----------------
    def pump(self):
        """等待期间无需为界面做事（HTTP 服务与页面各自独立运行）。"""
        return None

    def set_clipboard(self, text):
        self.outbox.push({"type": "clipboard", "text": text})
        return True


class EventPump:
    """把 core 事件队列里的后台结果转成页面能直接渲染的事件。

    同时调用 `core.dispatch()` 让 core 更新自己的内部状态（如下载忙碌标志）。
    """

    def __init__(self, core, outbox):
        self.core = core
        self.outbox = outbox
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name="webapp-events",
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                item = self.core.events.get(timeout=0.2)
            except Exception:
                continue
            try:
                self.core.dispatch(item)
                self._translate(item)
            except Exception:
                pass

    def _translate(self, item):
        kind = item[0]
        if kind == "server_log":
            self.outbox.push({"type": "log", "channel": "game",
                              "message": item[1], "tag": ""})
        elif kind == "bridge_log":
            self.outbox.push({"type": "log", "channel": "game",
                              "message": item[1], "tag": ""})
        elif kind == "dl_log":
            self.outbox.push({"type": "log", "channel": "download",
                              "message": item[1], "tag": ""})
        elif kind == "dl_progress":
            self.outbox.push({"type": "download", "progress": item[1]})
        elif kind == "dl_busy":
            self.outbox.push({"type": "download", "busy": item[1]})
        elif kind == "dl_versions":
            self.outbox.push({"type": "download_versions", "repo": item[1],
                              "items": [list(x) for x in item[2]]})
        elif kind == "dl_done":
            self.outbox.push({"type": "download_done", "target": item[1],
                              "set_service": item[2]})
        elif kind == "dl_fail":
            self.outbox.push({"type": "download_fail", "message": item[1],
                              "silent": bool(item[2]) if len(item) > 2 else False})
        elif kind == "dl_canceled":
            self.outbox.push({"type": "download_canceled"})
        elif kind == "dl_test_start":
            self.outbox.push({"type": "download_test_start"})
        elif kind == "dl_test_result":
            self.outbox.push({"type": "download_test_result",
                              "lines": item[1]})
        elif kind == "edit_live_data":
            self.outbox.push({"type": "editor_live", "ok": item[1] is not None,
                              "error": item[2]})
        elif kind == "edit_live_write":
            self.outbox.push({"type": "editor_sent", "result": item[1],
                              "error": item[2]})


class WebApi:
    """页面可调用的方法集合（全部返回可 JSON 序列化的结果）。"""

    def __init__(self, core, ui_port, *, on_shutdown=None):
        self.core = core
        self.ui = ui_port
        self.on_shutdown = on_shutdown
        self._manual = {}                 # session_id -> ManualSaveSession
        self._next_manual = 1
        self._lock = threading.Lock()
        self._last_seen = time.time()
        self.ever_seen = False

    # ---------------- 状态 ----------------
    def state(self):
        core = self.core
        return {
            "name": core.app_name,
            "version": core.app_version,
            "language": core.cfg.language,
            "config": {
                "language": core.cfg.language,
                "browser": core.cfg.browser,
                "game_dir": core.cfg.game_dir,
                "port": core.cfg.port,
                "home_slot": core.cfg.home_slot,
            },
            "strings": core.tr.table(),
            "slots": self.slots(),
            "server": core.server.status(),
            "repos": [{"label": label, "key": key}
                      for label, key in core.download.repo_choices()],
            "mirrors": core.download.mirrors(),
            "default_target": core.download.default_target(),
            "default_slot": core.cfg.home_slot,
            "paths": core.paths.as_dict(),
            "notes": [core.cfg.get_note(i) for i in range(core.slot_count)],
            "download_busy": core.download.busy,
            "editor": self.editor_state(),
        }

    def slots(self):
        core = self.core
        core.slots.refresh()
        out = []
        for i, info in enumerate(core.slots.info):
            out.append({
                "index": i,
                "label": core.slots.label(i),
                "name": core.slots.name(i),
                "exists": bool(info.get("exists")),
                "time": info.get("time", ""),
                "size": info.get("size", 0),
                "filename": (os.path.basename(info.get("filename", ""))
                             if info.get("exists") else ""),
                "note": core.cfg.get_note(i),
            })
        return out

    def editor_state(self):
        core = self.core
        ed = core.editor
        return {
            "has_data": ed.data is not None,
            "slot": ed.slot,
            "path": ed.path,
            "choices": [{"label": label, "index": index}
                        for label, index in ed.slot_choices()],
        }

    # ---------------- 通用 ----------------
    def set_language(self, code):
        self.core.set_language(code)
        return self.state()

    def set_config(self, **fields):
        allowed = {k: v for k, v in fields.items()
                   if k in ("game_dir", "port", "browser", "home_slot")}
        if allowed:
            self.core.cfg.update(**allowed)
        return self.state()

    def save_note(self, index, text):
        self.core.cfg.set_note(int(index), text)
        return True

    def refresh(self):
        return self.state()

    def open_url(self, url):
        from web_server import open_in_browser
        how = open_in_browser(url, browser_path=self.core.cfg.browser,
                              new_window=False)
        return bool(how)

    def open_doc(self):
        doc = self.core.paths.docs / "guide_en.html"
        if not doc.is_file():
            return False
        return self.open_url(doc.as_uri())

    # ---------------- 启动游戏 ----------------
    def start_server(self, open_browser=True):
        url = self.core.server.start(open_browser=bool(open_browser))
        return {"url": url or "", "server": self.core.server.status()}

    def stop_server(self):
        self.core.server.stop()
        return self.core.server.status()

    def open_game_window(self):
        return self.core.server.open_game_window()

    def server_status(self):
        return self.core.server.status()

    # ---------------- 存档管理 ----------------
    def auto_save(self, slot):
        return self.core.flows.auto_save(int(slot))

    def auto_load(self, slot):
        return self.core.flows.auto_load(int(slot))

    def copy_save(self, slot):
        return self.core.flows.copy_save(int(slot))

    def check_library(self):
        self.core.flows.check_library()
        return True

    def rename_slot(self, slot, name):
        path, error = self.core.slots.rename(int(slot), name)
        if path is None:
            if error:
                self.ui.fail(error)
            return {"ok": False, "error": error or ""}
        self.ui.slots_changed()
        return {"ok": True, "name": path.name}

    def manual_save_start(self, slot):
        session = self.core.flows.start_manual(int(slot))
        with self._lock:
            sid = self._next_manual
            self._next_manual += 1
            self._manual[sid] = session
        return {"session": sid, "temp_folder": str(self.core.paths.temp)}

    def manual_save_poll(self, session):
        item = self._manual.get(int(session))
        if item is None:
            return {"state": "gone"}
        state, content = self.core.flows.poll_manual(item)
        if state == "detected":
            path = item.path
            self.core.flows.finish_manual(item, content, detected=True,
                                          source_path=str(path) if path
                                          else None)
            self._close_manual(int(session))
            return {"state": "detected"}
        return {"state": state}

    def manual_save_submit(self, session, text):
        item = self._manual.get(int(session))
        if item is None:
            return {"state": "gone"}
        ok = self.core.flows.submit_manual_text(item, text)
        self._close_manual(int(session))
        return {"state": "saved" if ok else "cancelled"}

    def manual_save_cancel(self, session):
        item = self._manual.pop(int(session), None)
        if item is not None:
            self.core.flows.cancel_manual(item)
        return True

    def manual_copy_path(self):
        self.core.flows.copy_temp_path()
        return True

    def _close_manual(self, session):
        with self._lock:
            self._manual.pop(session, None)

    # ---------------- 下载游戏 ----------------
    def download_versions(self, repo, refresh=False):
        """拉取版本列表；refresh=True 时忽略缓存（对应「刷新版本列表」按钮）。"""
        self.core.download.refresh_versions(repo, refresh=bool(refresh))
        return True

    def download_test(self, repo, ref):
        return self.core.download.test_connectivity(repo, ref)

    def download_start(self, repo, mirror, ref, target, set_dir=True,
                       keep_temp=True):
        return self.core.download.start(repo, mirror, ref, target,
                                        set_service_dir=bool(set_dir),
                                        keep_temp=bool(keep_temp))

    def download_cancel(self):
        self.core.download.cancel()
        return True

    # ---------------- 修改存档 ----------------
    def editor_open_file(self, slot):
        ok = self.core.editor.open_file(int(slot))
        return {"ok": ok, "state": self.editor_state()}

    def editor_open_live(self):
        ok = self.core.editor.open_live()
        # 取档在后台进行：页面先显示「请求中」，结果经 editor_live 事件回来
        return {"ok": ok, "pending": ok, "state": self.editor_state()}

    def editor_source(self):
        return {"text": self.core.editor.source_text()}

    def editor_tree(self):
        return {"rows": self.core.editor.tree_rows()}

    def editor_set_value(self, path, raw):
        ok = self.core.editor.set_value(list(path), raw)
        return {"ok": ok, "rows": self.core.editor.tree_rows()}

    def editor_write(self, source_text=None):
        ok = self.core.editor.write(source_text=source_text)
        # 实时模式下发与确认在后台进行，结果经 editor_sent 事件回页面
        live = self.core.editor.path is None and self.core.editor.slot < 0
        return {"ok": ok, "pending": bool(ok and live),
                "state": self.editor_state()}

    # ---------------- 生命周期 ----------------
    def ping(self):
        """页面心跳：用于判断窗口是否已关闭。"""
        self._last_seen = time.time()
        self.ever_seen = True
        return {"time": self._last_seen}

    def last_seen(self):
        return self._last_seen

    def shutdown(self):
        if self.on_shutdown is not None:
            threading.Thread(target=self.on_shutdown, daemon=True).start()
        return True
