"""修改存档（逻辑层）：解码、树形视图数据、改值、重编码写回/下发。

前端只负责把 `tree_rows()` 画出来、把用户输入交回 `set_value()`，
以及在「源码」模式下把文本交给 `apply_source_text()` / `write(source_text=…)`。
事件：写回成功/失败通过 `UiPort` 提示与记日志；实时模式下发往游戏页面。
"""

import json
import os
from datetime import datetime
from pathlib import Path

import savecodec


# ---------------- JSON 小工具（紧凑 = JS JSON.stringify 风格） ----------------
def json_loads(text):
    return json.loads(text)


def json_dump(obj):
    """紧凑 JSON（JS JSON.stringify 风格）。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def json_compact(obj):
    return json_dump(obj)


def json_pretty(obj):
    """美化排版（保留键序，不排序）。"""
    return json.dumps(obj, ensure_ascii=False, indent=2)


def decode_to_obj(text):
    """把存档文本（原始 JSON / lz-string base64 / utf16）解码为对象。

    解码失败返回 None。
    """
    s = (text or "").strip()
    if not s:
        return None
    try:
        if s[0] == "{":
            return json_loads(s)
    except Exception:
        pass
    out = savecodec.decompress_base64(s)
    if not out or out[0] != "{":
        out = savecodec.decompress_utf16(s)
    if out and out[0] == "{":
        try:
            return json_loads(out)
        except Exception:
            return None
    return None


class EditorController:
    """「修改存档」页的状态与逻辑。"""

    def __init__(self, *, ui, slots, t, cfg, backup_dir, save_library,
                 max_save_size, get_bridge=None, is_server_running=None,
                 ensure_bridge_client=None, logger=None):
        self.ui = ui
        self.slots = slots
        self.t = t
        self.cfg = cfg
        self.backup_dir = Path(backup_dir) if backup_dir else None
        self.save_library = Path(save_library)
        self.max_save_size = max_save_size
        self._get_bridge = get_bridge or (lambda: None)
        self._is_server_running = is_server_running or (lambda: False)
        self._ensure_bridge_client = ensure_bridge_client or (lambda timeout: False)
        self.logger = logger

        self.data = None
        self.slot = -1
        self.path = None
        self.src_touched = False

    # ---------------- 选择项 ----------------
    def slot_choices(self):
        """有存档的槽位：[(显示文本, 槽位号)]。"""
        return [(self.slots.label(i), i) for i in range(len(self.slots.info))
                if self.slots.info[i].get('exists')]

    # ---------------- 打开 ----------------
    def open_file(self, slot):
        """打开槽位文件（打开前备份）。"""
        if slot < 0 or not self.slots.exists(slot):
            self.ui.warn(self.t("ed.no_slot"))
            return False
        path = self.slots.path(slot)
        try:
            content = self.slots.read(path, self.max_save_size)
        except Exception as e:
            self.ui.fail(str(e), self.t("err.load_fail"))
            return False
        obj = decode_to_obj(content)
        if obj is None:
            self.ui.fail(self.t("ed.parse_err", err="decode"),
                         self.t("err.load_fail"))
            return False
        self._backup(path)
        self.data = obj
        self.slot = slot
        self.path = str(path)
        self.src_touched = False
        self.ui.log(self.t("ed.loaded", name=self.slots.label(slot)),
                    self.t("tag.load"))
        return True

    def open_live(self):
        """从运行中的游戏页面拉取当前存档。"""
        bridge = self._get_bridge()
        if not (self._is_server_running() and bridge is not None):
            self.ui.warn(self.t("ed.no_bridge"))
            return False
        if not bridge.has_client and not self._ensure_bridge_client(6.0):
            self.ui.warn(self.t("ed.no_bridge"))
            return False
        content = bridge.request_save(timeout=15)
        obj = decode_to_obj(content or "")
        if obj is None:
            self.ui.fail(self.t("ed.parse_err", err="decode"),
                         self.t("err.load_fail"))
            return False
        self.data = obj
        self.slot = -1
        self.path = None
        self.src_touched = False
        self.ui.log(self.t("ed.pulled"), self.t("tag.load"))
        return True

    def _backup(self, path):
        if self.backup_dir is None:
            return
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.backup_dir / f"{Path(path).name}.{ts}.bak"
            bak.write_bytes(Path(path).read_bytes())
            self.ui.log(self.t("ed.backup", path=bak.name), self.t("tag.load"))
        except OSError as e:
            self.ui.log(self.t("msg.read_fail", e=e), self.t("tag.error"))

    # ---------------- 视图数据 ----------------
    def source_text(self):
        """源码模式文本（美化 JSON）。"""
        if self.data is None:
            return ""
        return json_pretty(self.data)

    def tree_rows(self):
        """树形视图数据（扁平行，含父子关系），空数据返回 []。"""
        rows = []
        if self.data is None:
            return rows
        rows.append({"id": 0, "parent": None, "label": "(root)",
                     "value": "", "kind": "root", "path": None})
        counter = {"n": 0}

        def add(parent_id, obj, label, path):
            counter["n"] += 1
            node_id = counter["n"]
            if isinstance(obj, dict):
                rows.append({"id": node_id, "parent": parent_id,
                             "label": label, "value": "",
                             "kind": "object", "path": path})
                if not obj:
                    return
                for k, v in obj.items():
                    add(node_id, v, str(k), path + [k])
            elif isinstance(obj, list):
                rows.append({"id": node_id, "parent": parent_id,
                             "label": label, "value": "",
                             "kind": "array", "path": path})
                for i, v in enumerate(obj):
                    text = str(i)
                    if isinstance(v, dict) and v:
                        k0 = next(iter(v))
                        val0 = v[k0]
                        if isinstance(val0, (str, int, float, bool)) or \
                                val0 is None:
                            text = f"{i} · {k0}: {str(val0)[:24]}"
                    elif isinstance(v, (str, int, float, bool)) or v is None:
                        text = f"{i} · {str(v)[:24]}"
                    add(node_id, v, text, path + [i])
            else:
                val = obj if isinstance(obj, str) else json_dump(obj)
                rows.append({"id": node_id, "parent": parent_id,
                             "label": label, "value": val,
                             "kind": "leaf", "path": path})

        add(0, self.data, "", [])
        return rows

    def _node_at(self, path):
        node = self.data
        for key in path:
            node = node[key]
        return node

    def value_at(self, path):
        """叶子当前值的字符串形式（供编辑框初值）。"""
        try:
            cur = self._node_at(path)
        except Exception:
            return None
        return cur if isinstance(cur, str) else json_dump(cur)

    def set_value(self, path, raw):
        """按路径写值：能解析为 JSON 就按类型写，否则按字符串写。"""
        if self.data is None or not path:
            self.ui.warn(self.t("ed.no_slot"))
            return False
        raw = (raw or "").strip()
        if not raw:
            return False
        try:
            value = json_loads(raw)
        except Exception:
            value = raw
        try:
            node = self._node_at(list(path)[:-1])
            node[list(path)[-1]] = value
        except Exception as e:
            self.ui.fail(str(e), self.t("ed.value_title"))
            return False
        self.src_touched = False
        return True

    # ---------------- 写回 ----------------
    def apply_source_text(self, text):
        """源码模式：解析文本并替换当前数据。"""
        try:
            self.data = json_loads(text)
        except Exception as e:
            self.ui.fail(self.t("ed.parse_err", err=str(e)),
                         self.t("err.save_fail"))
            return False
        self.src_touched = False
        return True

    def write(self, source_text=None):
        """写回：文件模式压缩后原子覆盖；实时模式下发并让页面刷新。"""
        if source_text is not None and self.src_touched:
            if not self.apply_source_text(source_text):
                return False
        if self.data is None:
            self.ui.warn(self.t("ed.no_slot"))
            return False
        blob = savecodec.compress_base64(json_compact(self.data))
        if self.path is not None or self.slot >= 0:
            return self._write_file(blob)
        return self._write_live(blob)

    def _write_file(self, blob):
        if self.path:
            dest = Path(self.path)
        else:
            if self.slot < 0:
                self.ui.warn(self.t("ed.no_slot"))
                return False
            dest = self.save_library / (
                f"{self.slots.base_for_write(self.slot)}"
                f"_{self.slot + 1}.kgsav")
        tmp = dest.with_name("." + dest.name + ".tmp")
        try:
            tmp.write_text(blob, encoding="utf-8")
            os.replace(str(tmp), str(dest))
        except OSError as e:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            self.ui.log(self.t("msg.process_fail", e=e), self.t("tag.error"))
            self._log_error(f"修改存档写回失败 {dest.name}: {e}")
            return False
        self.ui.log(self.t("ed.saved", dest=dest.name), self.t("tag.done"))
        self.ui.slots_changed()
        return True

    def _write_live(self, blob):
        bridge = self._get_bridge()
        if not (self._is_server_running() and bridge is not None):
            self.ui.warn(self.t("ed.no_bridge"))
            return False
        if not bridge.has_client and not self._ensure_bridge_client(6.0):
            self.ui.warn(self.t("ed.no_bridge"))
            return False
        if bridge.apply_save(blob):
            self.ui.log(self.t("ed.sent"), self.t("tag.done"))
            self.ui.notify(self.t("ed.sent"))
            return True
        self.ui.log(self.t("msg.auto_load_fail"), self.t("tag.error"))
        return False

    def _log_error(self, msg):
        if self.logger is not None:
            self.logger.error(msg)
