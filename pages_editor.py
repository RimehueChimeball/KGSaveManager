"""「修改存档」页（视图）。

逻辑全在 `core.editor.EditorController`：本模块只画控件、把用户操作交给
core，并把 core 的树形数据（`tree_rows()`）、源码文本（`source_text()`）
渲染出来。
"""

import tkinter as tk
from tkinter import scrolledtext, ttk


class EditorPageMixin:
    """「修改存档」标签页：文件/实时两种数据源，视图/源码两种显示。"""

    def build_editor_tab(self, parent, button_font, log_font):
        parent.columnconfigure(0, weight=1)
        # 只让内容区（第 2 行）吃掉多余高度；否则第 1 行的「视图/源码」
        # 也会被撑高，导致它与上下控件的间距过大
        parent.rowconfigure(2, weight=1)

        bar = ttk.LabelFrame(parent, text=self.t("ed.source"), padding="10")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        bar.columnconfigure(3, weight=1)

        self.edit_mode_var = tk.StringVar(value="file")
        ttk.Radiobutton(bar, text=self.t("ed.mode_file"),
                        variable=self.edit_mode_var, value="file",
                        command=self._edit_mode_changed).grid(row=0, column=0,
                                                              sticky="w")
        ttk.Radiobutton(bar, text=self.t("ed.mode_live"),
                        variable=self.edit_mode_var, value="live",
                        command=self._edit_mode_changed).grid(row=0, column=1,
                                                              sticky="w",
                                                              padx=(10, 0))

        self.edit_slot_var = tk.StringVar()
        ttk.Label(bar, text=self.t("ed.slot")).grid(row=0, column=2,
                                                    sticky="e", padx=(14, 4))
        self.edit_slot_combo = ttk.Combobox(bar, textvariable=self.edit_slot_var,
                                            state="readonly", width=28,
                                            takefocus=0)
        self.edit_slot_combo.grid(row=0, column=3, sticky="w")

        ttk.Button(bar, text=self.t("ed.btn_open"), style="Large.TButton",
                   command=self.edit_open_action).grid(row=0, column=4,
                                                       padx=(14, 0))
        ttk.Button(bar, text=self.t("ed.btn_write"), style="Large.TButton",
                   command=self.edit_write_action).grid(row=0, column=5,
                                                        padx=(8, 0))

        self.edit_view_var = tk.StringVar(value="view")
        view_bar = ttk.Frame(parent)
        view_bar.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        ttk.Radiobutton(view_bar, text=self.t("ed.view_tree"),
                        variable=self.edit_view_var, value="view",
                        command=self._edit_view_changed).pack(side=tk.LEFT)
        ttk.Radiobutton(view_bar, text=self.t("ed.view_source"),
                        variable=self.edit_view_var, value="source",
                        command=self._edit_view_changed).pack(side=tk.LEFT,
                                                              padx=(10, 0))

        body = ttk.Frame(parent)
        body.grid(row=2, column=0, sticky="nsew")
        parent.rowconfigure(2, weight=1)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self._edit_tree_frame = ttk.Frame(body)
        self._edit_tree_frame.grid(row=0, column=0, sticky="nsew")
        self._edit_tree_frame.columnconfigure(0, weight=1)
        self._edit_tree_frame.rowconfigure(0, weight=1)

        self.edit_tree = ttk.Treeview(self._edit_tree_frame,
                                      columns=("value",), show="tree headings")
        self.edit_tree.heading("#0", text=self.t("ed.col_key"))
        self.edit_tree.heading("value", text=self.t("ed.col_value"))
        self.edit_tree.column("#0", width=380, anchor="w")
        self.edit_tree.column("value", width=420, anchor="w")
        self.edit_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(self._edit_tree_frame, orient=tk.VERTICAL,
                            command=self.edit_tree.yview)
        self.edit_tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self.edit_tree.bind("<Double-1>", self._edit_tree_edit)

        self._edit_src_frame = ttk.Frame(body)
        self.edit_source = scrolledtext.ScrolledText(self._edit_src_frame,
                                                     wrap=tk.NONE,
                                                     font=('Consolas', 10))
        self.edit_source.pack(fill=tk.BOTH, expand=True)
        self.edit_source.bind("<KeyRelease>", self._mark_src_touched)
        self._edit_src_frame.columnconfigure(0, weight=1)
        self._edit_src_frame.rowconfigure(0, weight=1)

        self._edit_view_changed()
        # 建好控件后立刻填一次槽位下拉：否则启动后下拉是空的，
        # 用户直接点「打开」会报「请先选择一个有存档的槽位」
        self._refresh_edit_slots()

    # ---------------- 视图状态 ----------------
    def _edit_mode_changed(self):
        if self.edit_mode_var.get() == "file":
            self.edit_slot_combo.state(["!disabled"])
        else:
            self.edit_slot_combo.state(["disabled"])

    def _edit_view_changed(self):
        if self.edit_view_var.get() == "source":
            if not self.editor.src_touched:
                self.edit_source.delete("1.0", "end")
                self.edit_source.insert("1.0", self.editor.source_text())
            self._edit_tree_frame.pack_forget()
            self._edit_src_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self._edit_src_frame.pack_forget()
            self._edit_tree_frame.pack(fill=tk.BOTH, expand=True)
            self._rebuild_edit_tree()

    def _mark_src_touched(self, _event=None):
        self.editor.src_touched = True

    # ---------------- 动作 ----------------
    def edit_open_action(self):
        if self.edit_mode_var.get() == "file":
            slot = self._selected_edit_slot()
            if slot is None:
                self.ui.warn(self.t("ed.no_slot"))
                return
            if self.editor.open_file(slot):
                self._refresh_edit_slots()
                self._edit_view_changed()
        else:
            # 实时取档在后台线程进行（要等游戏页面回话），
            # 取到后由事件 `edit_live_data` 触发界面刷新
            self.editor.open_live()

    def edit_write_action(self):
        source_text = None
        if self.edit_view_var.get() == "source":
            source_text = self.edit_source.get("1.0", "end")
        if not self.editor.write(source_text=source_text):
            return
        # 实时模式下发与确认在后台进行，完成后由事件提示；
        # 文件模式改的是本地数据，直接重画
        if self.editor.path is not None or self.editor.slot >= 0:
            self._edit_view_changed()

    def edit_live_changed(self):
        """实时取档完成（core 状态已更新）后刷新编辑器视图。"""
        self._edit_view_changed()

    def _selected_edit_slot(self):
        label = self.edit_slot_var.get()
        for text, index in self.editor.slot_choices():
            if text == label:
                return index
        return None

    # ---------------- 渲染 ----------------
    def _rebuild_edit_tree(self):
        tree = self.edit_tree
        tree.delete(*tree.get_children())
        if self.editor.data is None:
            return
        self._edit_leaf_paths = {}
        iids = {}
        for row in self.editor.tree_rows():
            parent = iids.get(row["parent"], "")
            iid = tree.insert(parent, "end", text=row["label"],
                              values=(row["value"],))
            iids[row["id"]] = iid
            if row["kind"] == "leaf":
                self._edit_leaf_paths[iid] = row["path"]

    def _edit_tree_edit(self, _event=None):
        iid = self.edit_tree.focus()
        paths = getattr(self, "_edit_leaf_paths", {})
        if not iid or iid not in paths:
            return
        path = paths[iid]
        initial = self.editor.value_at(path)
        if initial is None:
            return
        raw = self.ui.ask_text(self.t("ed.value_title"),
                               self.t("ed.value_prompt"), str(initial))
        if raw is None or not raw.strip():
            return
        if self.editor.set_value(path, raw):
            self._rebuild_edit_tree()

    def _refresh_edit_slots(self):
        """让槽位下拉跟随存档库刷新（由主类 update_slots_display 调用）。

        重画选项时要保留当前选择：`configure(values=…)` 会清空文本框，
        若之后又退回第一项，用户每次点「打开」都会看到选择被重置。
        """
        if not hasattr(self, "edit_slot_combo"):
            return
        if not self._widget_alive(self.edit_slot_combo):
            return
        cur = self.edit_slot_var.get()
        mapping = {text: index for text, index in self.editor.slot_choices()}
        values = list(mapping.keys())
        self.edit_slot_combo.configure(values=values)
        if cur in mapping:
            self.edit_slot_var.set(cur)          # 选择还在：原样保留
            return
        if self.edit_mode_var.get() == "file":
            # 没选过、或选中的项已消失：跟随编辑器当前打开的槽位，其次第一项
            opened = self.editor.slot
            want = next((text for text, index in mapping.items()
                         if index == opened), None)
            self.edit_slot_var.set(want or (values[0] if values else ""))
        else:
            self.edit_slot_var.set("")
