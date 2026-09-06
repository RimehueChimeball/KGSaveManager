"""
pages_download：KGSaveManager「下载游戏」标签页（Mixin）。

依赖主类的：self.root/self.t/self.cfg/self.event_queue/BASE_DIR/_handle_event
（事件见 KGSaveManager._handle_event：dl_log / dl_versions / dl_progress /
 dl_done / dl_fail）
"""

import os
import threading

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import downloader


class DownloadPageMixin:
    """「下载游戏」页：从 GitHub/镜像下载指定版本并摊平到目标目录。"""

    def build_download_tab(self, parent, button_font, log_font):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)

        self.dl = {
            "busy": False,
            "cancel": threading.Event(),
            "ver_map": {},
            "repo_map": {
                self.t("dl.repo_author"): "author",
                self.t("dl.repo_community"): "community",
            },
        }
        self.dl_repo_var = tk.StringVar(value=self.t("dl.repo_author"))
        self.dl_mirror_var = tk.StringVar(value="GitHub 直连")
        self.dl_dir_var = tk.StringVar(
            value=str(getattr(self, "base_dir", os.getcwd()) /
                      "KittensGame"))
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
                   command=self._dl_refresh_versions).grid(
            row=1, column=2, padx=(8, 0), pady=4)

        ttk.Label(cfg, text=self.t("dl.mirror")).grid(row=2, column=0,
                                                      sticky="w", pady=4,
                                                      padx=(0, 8))
        self.dl_mirror_combo = ttk.Combobox(
            cfg, textvariable=self.dl_mirror_var, state="readonly",
            values=list(downloader.MIRRORS.keys()), width=24, takefocus=0)
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

        ttk.Label(parent, text=self.t("dl.dir_default_tip"),
                  foreground="#888888").grid(row=1, column=0, sticky="w",
                                             pady=(0, 4))

        bar_frame = ttk.Frame(parent)
        bar_frame.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        self.dl_progress = ttk.Progressbar(
            bar_frame, variable=self.dl_progress_var, maximum=100)
        self.dl_progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.dl_btn_start = ttk.Button(
            bar_frame, text=self.t("dl.btn_download"),
            style="Large.TButton", command=self._dl_start)
        self.dl_btn_start.pack(side=tk.LEFT, padx=(10, 0))
        self.dl_btn_cancel = ttk.Button(
            bar_frame, text=self.t("msg.btn_close"),
            style="Large.TButton", command=self._dl_cancel,
            state=tk.DISABLED)
        self.dl_btn_cancel.pack(side=tk.LEFT, padx=(8, 0))

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

    # ---------------- 动作 ----------------
    def _dl_log(self, msg):
        if not hasattr(self, "dl_log_text") or not self._widget_alive(
                self.dl_log_text):
            return
        self._append_log(self.dl_log_text, msg, self.t("tag.download"))

    def _dl_browse_dir(self):
        chosen = filedialog.askdirectory(
            title=self.t("dl.dir"),
            initialdir=self.dl_dir_var.get().strip()
            or str(getattr(self, "base_dir", os.getcwd())))
        if chosen:
            self.dl_dir_var.set(chosen)

    def _dl_refresh_versions(self, silent=False):
        repo = self.dl["repo_map"].get(self.dl_repo_var.get(), "author")
        threading.Thread(
            target=self._dl_fetch_versions, args=(repo, silent),
            daemon=True).start()

    def _dl_fetch_versions(self, repo, silent):
        try:
            owner = downloader.REPOS[repo]["owner"]
            name = downloader.REPOS[repo]["repo"]
            items = downloader.list_versions(owner, name)
        except Exception as e:
            self.event_queue.put(
                ("dl_fail", self.t("dl.version_fail", e=str(e)), silent))
            return
        self.event_queue.put(("dl_versions", repo, items))

    def _dl_start(self):
        if self.dl.get("busy"):
            return
        repo = self.dl["repo_map"].get(self.dl_repo_var.get(), "author")
        mirror = self.dl_mirror_var.get()
        target = self.dl_dir_var.get().strip()
        label = self.dl_version_combo.get()
        ver_map = self.dl.get("ver_map", {})
        if not label or label not in ver_map:
            messagebox.showwarning(self.t("dl.version"),
                                   self.t("dl.version_pick"))
            return
        if not target:
            messagebox.showerror(self.t("dl.version"),
                                 self.t("dl.dir_missing", dir=target or "?"))
            return
        os.makedirs(target, exist_ok=True)
        has_content = any(
            os.path.join(target, n) != os.path.join(target, ".temp")
            for n in os.listdir(target)) and \
            any(n != ".temp" for n in os.listdir(target))
        if has_content:
            if not messagebox.askyesno(
                    self.t("dl.version"),
                    self.t("dl.dir_has_content", dir=target)):
                return

        kind, ref = ver_map[label]
        self.dl["busy"] = True
        self.dl["cancel"].clear()
        self.dl_btn_start.config(state=tk.DISABLED)
        self.dl_btn_cancel.config(state=tk.NORMAL)
        self.dl_progress_var.set(0)
        threading.Thread(
            target=self._dl_worker,
            args=(repo, mirror, ref, target, self.dl_set_dir_var.get()),
            daemon=True).start()

    def _dl_cancel(self):
        self.dl["cancel"].set()

    def _dl_worker(self, repo, mirror, ref, target, set_service):
        try:
            downloader.install_game(
                repo, mirror, ref, target,
                progress=self._dl_progress_cb,
                cancel=lambda: self.dl["cancel"].is_set())
            if set_service:
                self.cfg.update(game_dir=target)
                self._sync_page_vars()
                self._refresh_kgm_dir()
            self.event_queue.put(("dl_done", target, set_service))
        except downloader.DownloadCancelled:
            self.event_queue.put(("dl_canceled",))
        except Exception as e:
            self.event_queue.put(("dl_fail", self.t("dl.fail", e=str(e))))

    def _dl_progress_cb(self, done, total, stage=None):
        if stage == "extract":
            self.event_queue.put(("dl_log", self.t("dl.unzip")))
            return
        pct = 0
        if total:
            pct = min(99, int(done * 100 / total))
        self.event_queue.put(("dl_progress", pct))

    # 事件处理（由主类 _handle_event 分发）
    def _handle_dl_versions(self, items):
        labels = [f"{kind}: {label}" for kind, label, _ref in items]
        self.dl["ver_map"] = {f"{k}: {lab}": ref
                              for k, lab, ref in items}
        self.dl_version_combo.configure(values=labels)
        if labels:
            self.dl_version_combo.current(0)

    def _handle_dl_progress(self, pct):
        self.dl_progress_var.set(pct)

    def _handle_dl_done(self, target, set_service):
        self.dl["busy"] = False
        self.dl_btn_start.config(state=tk.NORMAL)
        self.dl_btn_cancel.config(state=tk.DISABLED)
        self.dl_progress_var.set(100)
        self._dl_log(self.t("dl.done", dir=target))
        if set_service:
            self._dl_log(self.t("dl.service_set"))
        self.update_slots_display()

    def _handle_dl_fail(self, msg, silent=False):
        self.dl["busy"] = False
        self.dl_btn_start.config(state=tk.NORMAL)
        self.dl_btn_cancel.config(state=tk.DISABLED)
        self._dl_log(msg)
        if not silent:
            messagebox.showerror(self.t("dl.version"), msg)

    def _handle_dl_cancel(self):
        self.dl["busy"] = False
        self.dl_btn_start.config(state=tk.NORMAL)
        self.dl_btn_cancel.config(state=tk.DISABLED)
        self._dl_log(self.t("dl.cancel"))

    def open_download_tab(self, repo_key):
        """从 KGSM 主页跳转到下载页并预选仓库。"""
        for label, key in self.dl["repo_map"].items():
            if key == repo_key:
                self.dl_repo_var.set(label)
                break
        self.notebook.select(
            getattr(self, "tab_order", ("kgsm", "game", "saves", "editor",
                                        "download", "settings")).index(
                                            "download"))
        self._dl_refresh_versions()
