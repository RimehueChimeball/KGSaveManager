"""
pages_editor：KGSaveManager「修改存档」标签页（Mixin）。

从主类迁出（解耦）：
- 依赖主类属性：self.t/self.log/self.cfg/self.slot_info/self.root/
  self.lweb/self.bridge/self._read_save_file/self.slot_name/
  self.slot_default_base/self.update_slots_display/self.app_name/
  self.save_library
"""

import json
import os
from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog, ttk

import savecodec


def json_loads(text):
    return json.loads(text)


def json_dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def json_compact(obj):
    return json_dump(obj)


def json_pretty(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


class EditorPageMixin:
    """修改存档页：槽位文件 / 运行中游戏，双显示（视图/源码）。"""

    # ---------------- 修改存档页 ----------------
    def build_editor_tab(self, parent, button_font, log_font):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        self._edit = {"data": None, "mode": "file", "slot": -1,
                      "path": None, "src_touched": False,
                      "slot_map": {}, "leaf": {}}

        bar = ttk.Frame(parent)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        bar.columnconfigure(4, weight=1)
        self.edit_mode_var = __import__("tkinter").StringVar(value="file")
        ttk.Radiobutton(bar, text=self.t("ed.mode_file"),
                        variable=self.edit_mode_var, value="file",
                        command=self._edit_mode_changed).grid(
            row=0, column=0, padx=(0, 10))
        ttk.Radiobutton(bar, text=self.t("ed.mode_live"),
                        variable=self.edit_mode_var, value="live",
                        command=self._edit_mode_changed).grid(
            row=0, column=1, padx=(0, 14))
        ttk.Label(bar, text=self.t("ed.slot")).grid(row=0, column=2)
        self.edit_slot_var = __import__("tkinter").StringVar()
        self.edit_slot_combo = ttk.Combobox(
            bar, textvariable=self.edit_slot_var, state="readonly",
            width=24, takefocus=0)
        self.edit_slot_combo.grid(row=0, column=3, padx=(6, 10))
        self.edit_open_btn = ttk.Button(bar, text=self.t("ed.btn_open"),
                                        style="Large.TButton",
                                        command=self.edit_open_action)
        self.edit_open_btn.grid(row=0, column=4, sticky="e")
        self.edit_write_btn = ttk.Button(bar, text=self.t("ed.btn_write"),
                                         style="Large.TButton",
                                         command=self.edit_write_action)
        self.edit_write_btn.grid(row=0, column=5, padx=(8, 0))

        viewbar = ttk.Frame(parent)
        viewbar.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.edit_view_var = __import__("tkinter").StringVar(value="tree")
        ttk.Radiobutton(viewbar, text=self.t("ed.view_tree"),
                        variable=self.edit_view_var, value="tree",
                        command=self._edit_view_changed).pack(
            side=__import__("tkinter").LEFT, padx=(0, 10))
        ttk.Radiobutton(viewbar, text=self.t("ed.view_source"),
                        variable=self.edit_view_var, value="source",
                        command=self._edit_view_changed).pack(
            side=__import__("tkinter").LEFT)

        pane = ttk.Frame(parent)
        pane.grid(row=2, column=0, sticky="nsew")
        pane.columnconfigure(0, weight=1)
        pane.rowconfigure(0, weight=1)

        # 视图：键/值 树
        self._edit_tree_frame = ttk.Frame(pane)
        self.edit_tree = ttk.Treeview(self._edit_tree_frame,
                                      columns=("value",),
                                      show="tree headings")
        self.edit_tree.heading("#0", text="key")
        self.edit_tree.heading("value", text="value")
        vsb = ttk.Scrollbar(self._edit_tree_frame, orient="vertical",
                            command=self.edit_tree.yview)
        self.edit_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=__import__("tkinter").RIGHT, fill=__import__("tkinter").Y)
        self.edit_tree.pack(side=__import__("tkinter").LEFT,
                            fill=__import__("tkinter").BOTH, expand=True)
        self.edit_tree.bind("<Double-1>", self._edit_tree_edit)

        # 源码：JSON 文本
        self._edit_src_frame = ttk.Frame(pane)
        self.edit_source = scrolledtext.ScrolledText(
            self._edit_src_frame, wrap=__import__("tkinter").NONE,
            font=log_font)
        self.edit_source.pack(fill=__import__("tkinter").BOTH,
                              expand=True)
        self.edit_source.bind("<KeyRelease>",
                              lambda e: self._mark_src_touched())

        self._edit_view_changed()
        self._edit_mode_changed()

    def _edit_mode_changed(self):
        mode = self.edit_mode_var.get()
        self._edit["mode"] = mode
        if mode == "file":
            ids = [i for i, info in enumerate(self.slot_info)
                   if info.get('exists')]
            self._edit["slot_ids"] = ids
            self._edit["slot_map"] = {self.slot_label(i): i for i in ids}
            self.edit_slot_combo.configure(
                values=list(self._edit["slot_map"].keys()))
            self.edit_slot_combo.state(["!disabled"])
        else:
            self.edit_slot_combo.state(["disabled"])

    def _edit_view_changed(self):
        if self.edit_view_var.get() == "source":
            if self._edit["data"] is not None and not self._edit[
                    "src_touched"]:
                self.edit_source.delete("1.0", "end")
                self.edit_source.insert(
                    "1.0", json_pretty(self._edit["data"]))
            self._edit_tree_frame.grid_forget()
            self._edit_src_frame.grid(row=0, column=0, sticky="nsew")
        else:
            self._edit_tree_frame.grid(row=0, column=0, sticky="nsew")
            self._edit_src_frame.grid_forget()
            self._rebuild_edit_tree()

    def _mark_src_touched(self):
        self._edit["src_touched"] = True

    def _current_data_text(self):
        return json_compact(self._edit["data"]) if self._edit[
            "data"] is not None else ""

    def edit_open_action(self):
        mode = self._edit["mode"]
        if mode == "file":
            label = self.edit_slot_var.get()
            slot = self._edit["slot_map"].get(label, -1)
            if slot < 0 or not self.slot_info[slot].get('exists'):
                messagebox.showwarning(self.app_name, self.t("ed.no_slot"))
                return
            path = Path(self.slot_info[slot]['filename'])
            try:
                content = self._read_save_file(str(path))
            except Exception as e:
                messagebox.showerror(self.t("err.load_fail"), str(e))
                return
            obj = self._decode_to_obj(content)
            if obj is None:
                messagebox.showerror(self.t("err.load_fail"),
                                     self.t("ed.parse_err", err="decode"))
                return
            # 打开前自动备份
            try:
                bak = path.with_name("." + path.name + ".bak")
                bak.write_bytes(path.read_bytes())
                self.log(self.t("ed.backup", path=bak.name),
                         self.t("tag.load"))
            except OSError as e:
                self.log(self.t("msg.read_fail", e=e), self.t("tag.error"))
            self._edit.update({"data": obj, "slot": slot, "path": str(path),
                               "src_touched": False})
            self._edit_view_changed()
            self.log(self.t("ed.loaded", name=self.slot_label(slot)),
                     self.t("tag.load"))
        else:
            if not (self.lweb.running and self.bridge is not None
                    and self.bridge.has_client):
                messagebox.showwarning(self.app_name, self.t("ed.no_bridge"))
                return
            content = self.bridge.request_save(timeout=15)
            obj = self._decode_to_obj(content or "")
            if obj is None:
                messagebox.showerror(self.t("err.load_fail"),
                                     self.t("ed.parse_err", err="decode"))
                return
            self._edit.update({"data": obj, "slot": -1, "path": None,
                               "src_touched": False})
            self._edit_view_changed()
            self.log(self.t("ed.pulled"), self.t("tag.load"))

    def _decode_to_obj(self, text):
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
            return json_loads(out)
        return None

    def edit_write_action(self):
        if self.edit_view_var.get() == "source" and self._edit[
                "src_touched"]:
            try:
                obj = json_loads(self.edit_source.get("1.0", "end"))
            except Exception as e:
                messagebox.showerror(
                    self.t("err.save_fail"),
                    self.t("ed.parse_err", err=str(e)))
                return
            self._edit["data"] = obj
            self._edit["src_touched"] = False
        if self._edit["data"] is None:
            messagebox.showwarning(self.app_name, self.t("ed.no_slot"))
            return

        mode = self._edit["mode"]
        compact = json_compact(self._edit["data"])
        blob = savecodec.compress_base64(compact)
        if mode == "file":
            path = self._edit.get("path")
            if path is None:
                slot = self._edit.get("slot", self.selected_slot.get())
            else:
                slot = self._edit.get("slot")
            if slot < 0:
                messagebox.showwarning(self.app_name, self.t("ed.no_slot"))
                return
            dest = Path(path) if path else self.save_library / (
                f"{self.slot_name(slot) or self.slot_default_base(slot)}"
                f"_{slot + 1}.kgsav")
            tmp = dest.with_name("." + dest.name + ".tmp")
            try:
                tmp.write_text(blob, encoding="utf-8")
                os.replace(str(tmp), str(dest))
                self.update_slots_display()
                self.log(self.t("ed.saved", dest=dest.name),
                         self.t("tag.done"))
            except OSError as e:
                self.log(self.t("msg.process_fail", e=e),
                         self.t("tag.error"))
        else:
            if not (self.lweb.running and self.bridge is not None
                    and self.bridge.has_client):
                messagebox.showwarning(self.app_name, self.t("ed.no_bridge"))
                return
            if self.bridge.apply_save(blob):
                self.log(self.t("ed.sent"), self.t("tag.done"))
                messagebox.showinfo(self.app_name, self.t("ed.sent"))
            else:
                self.log(self.t("msg.auto_load_fail"), self.t("tag.error"))

    def _rebuild_edit_tree(self):
        tree = self.edit_tree
        tree.delete(*tree.get_children())
        self._edit["leaf"] = {}
        data = self._edit["data"]
        if data is None:
            return

        def add(parent_iid, obj, key_text, path):
            if isinstance(obj, dict):
                if not obj:
                    tree.insert(parent_iid, "end", text=key_text,
                                values=("{}",))
                    return
                for k, v in obj.items():
                    iid = tree.insert(parent_iid, "end", text=str(k),
                                      values=("",))
                    add(iid, v, str(k), path + [k])
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    iid = tree.insert(parent_iid, "end",
                                      text=f"index{i}", values=("",))
                    add(iid, v, f"index{i}", path + [i])
            else:
                val = obj if isinstance(obj, str) else json_dump(obj)
                iid = tree.insert(parent_iid, "end", text=key_text,
                                  values=(val,))
                self._edit["leaf"][iid] = path

        tree.insert("", "end", text="(root)", values=("",))
        add("", data, "", [])

    def _edit_tree_edit(self, _event=None):
        iid = self.edit_tree.focus()
        if not iid or iid not in self._edit["leaf"]:
            return
        path = self._edit["leaf"][iid]
        node = self._edit["data"]
        for key in path[:-1]:
            node = node[key]
        leaf_key = path[-1]
        cur = node[leaf_key]
        initial = cur if isinstance(cur, str) else json_dump(cur)
        raw = simpledialog.askstring(self.t("ed.value_title"),
                                     self.t("ed.value_prompt"),
                                     initialvalue=initial,
                                     parent=self.root)
        if raw is None:
            return
        raw = raw.strip()
        if not raw:
            return
        try:
            value = json_loads(raw)
        except Exception:
            value = raw
        node[leaf_key] = value
        self._edit["src_touched"] = False
        self._rebuild_edit_tree()
