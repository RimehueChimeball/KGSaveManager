"""「下载游戏」页（视图）。

逻辑全在 `core.download.DownloadController`：本模块只画控件、把用户选择交给
core，并把 core 通过事件队列回传的进度/日志/结果画出来。
事件：dl_busy / dl_log / dl_progress / dl_versions / dl_done / dl_fail /
      dl_canceled / dl_test_start / dl_test_result
"""

import os

import tkinter as tk
from tkinter import scrolledtext, ttk


class DownloadPageMixin:
    """「下载游戏」页：从 GitHub/镜像下载指定版本并摊平到目标目录。"""

    def build_download_tab(self, parent, button_font, log_font):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)

        choices = self.download.repo_choices()
        self.dl = {
            "busy": False,
            "ver_map": {},
            "repo_map": {label: key for label, key in choices},
        }
        self.dl_repo_var = tk.StringVar(value=choices[0][0])
        self.dl_mirror_var = tk.StringVar(value=self.download.mirrors()[0])
        self.dl_dir_var = tk.StringVar(
            value=str(self.download.default_target()))
        self.dl_set_dir_var = tk.BooleanVar(value=True)
        self.dl_progress_var = tk.DoubleVar(value=0)

        cfg = ttk.LabelFrame(parent, text=self.t("dl.version"), padding="10")
        cfg.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        cfg.columnconfigure(1, weight=1)

        ttk.Label(cfg, text=self.t("dl.repo")).grid(row=0, column=0,
                                                    sticky="w", pady=4,
                                                    padx=(0, 8))
        repo_box = ttk.Combobox(
            cfg, textvariable=self.dl_repo_var, state="readonly",
            values=list(self.dl["repo_map"].keys()), width=34, takefocus=0)
        repo_box.grid(row=0, column=1, sticky="w", pady=4)
        repo_box.bind("<<ComboboxSelected>>",
                      lambda e: self._dl_refresh_versions())

        ttk.Label(cfg, text=self.t("dl.version")).grid(row=1, column=0,
                                                       sticky="w", pady=4,
                                                       padx=(0, 8))
        self.dl_version_combo = ttk.Combobox(cfg, state="readonly",
                                             width=30, takefocus=0)
        self.dl_version_combo.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Button(cfg, text=self.t("dl.refresh_versions"),
                   command=lambda: self._dl_refresh_versions(refresh=True)).grid(
            row=1, column=2, padx=(8, 0), pady=4)

        ttk.Label(cfg, text=self.t("dl.mirror")).grid(row=2, column=0,
                                                      sticky="w", pady=4,
                                                      padx=(0, 8))
        self.dl_mirror_combo = ttk.Combobox(
            cfg, textvariable=self.dl_mirror_var, state="readonly",
            values=self.download.mirrors(), width=24, takefocus=0)
        self.dl_mirror_combo.grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(cfg, text=self.t("dl.dir")).grid(row=3, column=0,
                                                   sticky="w", pady=4,
                                                   padx=(0, 8))
        ent = ttk.Entry(cfg, textvariable=self.dl_dir_var)
        ent.grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Button(cfg, text=self.t("ui.browse"),
                   command=self._dl_browse_dir).grid(row=3, column=2,
                                                     padx=(8, 0), pady=4)

        self.dl_set_dir_check = ttk.Checkbutton(
            cfg, text=self.t("dl.set_service_dir"),
            variable=self.dl_set_dir_var)
        self.dl_set_dir_check.grid(row=4, column=0, columnspan=3, sticky="w",
                                   pady=(4, 0))

        self.dl_keep_temp_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(cfg, text=self.t("dl.keep_temp"),
                        variable=self.dl_keep_temp_var).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))

        ttk.Label(parent, text=self.t("dl.dir_default_tip"),
                  foreground="#888888").grid(row=1, column=0, sticky="w",
                                             pady=(0, 4))

        bar_frame = ttk.Frame(parent)
        bar_frame.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        bar_frame.columnconfigure(0, weight=1)
        self.dl_progress = ttk.Progressbar(
            bar_frame, variable=self.dl_progress_var, maximum=100)
        self.dl_progress.grid(row=0, column=0, sticky="ew")
        self.dl_btn_test = ttk.Button(
            bar_frame, text=self.t("dl.btn_test"), style="Large.TButton",
            command=self._dl_test_connectivity)
        self.dl_btn_test.grid(row=0, column=1, padx=(10, 0))
        self.dl_btn_start = ttk.Button(
            bar_frame, text=self.t("dl.btn_download"),
            style="Large.TButton", command=self._dl_start)
        self.dl_btn_start.grid(row=0, column=2, padx=(10, 0))
        self.dl_btn_cancel = ttk.Button(
            bar_frame, text=self.t("msg.btn_close"),
            style="Large.TButton", command=self._dl_cancel,
            state=tk.DISABLED)
        self.dl_btn_cancel.grid(row=0, column=3, padx=(8, 0))
        self.dl_test_label = ttk.Label(bar_frame, foreground="#0a58ca",
                                       wraplength=760)
        self.dl_test_label.grid(row=1, column=0, columnspan=4, sticky="w",
                                pady=(4, 0))

        log_frame = ttk.LabelFrame(parent, text=self.t("dl.log"),
                                   padding="6")
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.dl_log_text = scrolledtext.ScrolledText(log_frame,
                                                     wrap=tk.WORD,
                                                     font=log_font,
                                                     height=6)
        self.dl_log_text.grid(row=0, column=0, sticky="nsew")
        self.dl_log_text.config(state=tk.DISABLED)
        self._dl_log(self.t("dl.version_pick"))

        self._dl_refresh_versions()
        self._update_download_buttons()

    # ---------------- 视图动作 ----------------
    def _dl_log(self, msg):
        if not hasattr(self, "dl_log_text") or not self._widget_alive(
                self.dl_log_text):
            return
        self._append_log(self.dl_log_text, msg, self.t("tag.download"))

    def _dl_browse_dir(self):
        chosen = self.ui.ask_directory(
            self.t("dl.dir"),
            self.dl_dir_var.get().strip()
            or str(getattr(self, "base_dir", os.getcwd())))
        if chosen:
            self.dl_dir_var.set(chosen)

    def _dl_repo_key(self):
        return self.dl["repo_map"].get(self.dl_repo_var.get(), "author")

    def _dl_ref(self):
        return self.dl.get("ver_map", {}).get(self.dl_version_combo.get())

    def _dl_refresh_versions(self, silent=False, refresh=False):
        self.download.refresh_versions(self._dl_repo_key(), silent,
                                       refresh=refresh)

    def _dl_start(self):
        ref = self._dl_ref()
        if ref is None:
            self.ui.warn(self.t("dl.version_pick"), self.t("dl.version"))
            return
        self.download.start(self._dl_repo_key(), self.dl_mirror_var.get(),
                            ref, self.dl_dir_var.get().strip(),
                            self.dl_set_dir_var.get(),
                            self.dl_keep_temp_var.get())

    def _dl_cancel(self):
        self.download.cancel()

    def _dl_test_connectivity(self):
        self.download.test_connectivity(self._dl_repo_key(), self._dl_ref())

    # ---------------- 事件渲染（由主类 _handle_event 分发） ----------------
    def _handle_dl_versions(self, items):
        labels = []
        mapping = {}
        for kind, label, ref in items:
            disp = label if kind == "branch" else f"{label} (tag)"
            labels.append(disp)
            mapping[disp] = ref
        self.dl["ver_map"] = mapping
        self.dl_version_combo.configure(values=labels)
        if labels:
            self.dl_version_combo.current(0)

    def _handle_dl_busy(self, busy):
        self.dl["busy"] = busy
        if not hasattr(self, "dl_btn_start"):
            return
        self.dl_btn_start.config(state=tk.DISABLED if busy else tk.NORMAL)
        self.dl_btn_cancel.config(state=tk.NORMAL if busy else tk.DISABLED)
        if busy:
            self.dl_progress_var.set(0)

    def _handle_dl_progress(self, pct):
        self.dl_progress_var.set(pct)

    def _handle_dl_test_start(self):
        self.dl_btn_test.config(state=tk.DISABLED)
        self.dl_test_label.config(text=self.t("dl.testing"))

    def _handle_dl_test_result(self, lines):
        self.dl_btn_test.config(state=tk.NORMAL)
        self.dl_test_label.config(text="\n".join(lines))

    def _handle_dl_done(self, target, set_service):
        self.dl_progress_var.set(100)
        self._dl_log(self.t("dl.done", dir=target))
        if set_service:
            self._dl_log(self.t("dl.service_set"))
            self._sync_page_vars()
        self.update_slots_display()

    def _handle_dl_fail(self, msg, silent=False):
        self._dl_log(msg)
        if not silent:
            self.ui.fail(msg, self.t("dl.version"))

    def _handle_dl_cancel(self):
        self._dl_log(self.t("dl.cancel"))

    def _update_download_buttons(self):
        """按 core 的忙碌状态刷新按钮（界面重建后调用）。"""
        self._handle_dl_busy(self.download.busy)
