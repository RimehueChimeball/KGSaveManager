"""游戏下载（逻辑层）：版本列表、连通性测试、下载解压进度与取消。

与界面无关：进度、日志、失败都通过 `events` 事件队列回传，前端负责显示。
事件契约（前端在 UI 线程处理）：
- `("dl_busy", bool)`：忙碌状态变化（按钮启用/禁用）
- `("dl_log", text)`：一行下载日志
- `("dl_progress", percent)`：进度百分比
- `("dl_versions", repo_key, items)`：版本列表就绪
- `("dl_done", target_dir, set_service_dir)`：完成
- `("dl_fail", message, silent)`：失败
- `("dl_canceled",)`：已取消
- `("dl_test_start",)` / `("dl_test_result", lines)`：连通性测试
"""

import os
import threading

import downloader


class DownloadController:
    """「下载游戏」页的后台逻辑。"""

    def __init__(self, *, ui, cfg, t, events, base_dir, logger=None):
        self.ui = ui
        self.cfg = cfg
        self.t = t
        self.events = events
        self.base_dir = base_dir
        self.logger = logger
        self.busy = False
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    # ---------------- 静态信息 ----------------
    def repo_choices(self):
        """返回 [(显示名, 仓库键)]，显示名随语言。"""
        return [(self.t("dl.repo_author"), "author"),
                (self.t("dl.repo_community"), "community")]

    def mirrors(self):
        return list(downloader.MIRRORS.keys())

    def default_target(self):
        return os.path.join(str(self.base_dir), "KittensGame")

    # ---------------- 版本列表 ----------------
    def refresh_versions(self, repo_key, silent=False, refresh=False):
        """后台拉取版本列表；refresh=True 时忽略缓存强制重抓。"""
        threading.Thread(target=self._fetch_versions,
                         args=(repo_key, silent, refresh), daemon=True).start()

    def _fetch_versions(self, repo_key, silent, refresh=False):
        try:
            owner = downloader.REPOS[repo_key]["owner"]
            name = downloader.REPOS[repo_key]["repo"]
            notes = []
            items = downloader.list_versions(owner, name, notes=notes,
                                            refresh=refresh)
        except Exception as e:
            self.events.put(
                ("dl_fail", self.t("dl.version_fail", e=str(e)), silent))
            return
        for line in notes:          # 诊断提示（限流/缓存等）先写进下载日志
            self.events.put(("dl_log", line))
        self.events.put(("dl_versions", repo_key, items))

    # ---------------- 连通性测试 ----------------
    def test_connectivity(self, repo_key, ref):
        if not ref:
            self.ui.warn(self.t("dl.version_pick"), self.t("dl.version"))
            return False
        self.events.put(("dl_test_start",))
        threading.Thread(target=self._test_worker, args=(repo_key, ref),
                         daemon=True).start()
        return True

    def _test_worker(self, repo_key, ref):
        try:
            results = downloader.test_sources(repo_key, ref, timeout=6)
        except Exception as e:
            self.events.put(
                ("dl_test_result",
                 [f"test error: {type(e).__name__}: {e}"]))
            return
        lines = []
        for source in downloader.MIRRORS:
            ok, detail = results.get(source, (False, "not tested"))
            mark = "OK" if ok else "FAIL"
            lines.append(f"{source}: {mark} ({detail})")
        self.events.put(("dl_test_result", lines))

    # ---------------- 下载 ----------------
    def start(self, repo_key, mirror, ref, target, set_service_dir=False,
              keep_temp=True):
        """开始下载安装。

        :return: True 表示已在后台开始
        """
        with self._lock:
            if self.busy:
                return False
        if not ref:
            self.ui.warn(self.t("dl.version_pick"), self.t("dl.version"))
            return False
        target = (target or "").strip()
        if not target:
            self.ui.fail(self.t("dl.dir_missing", dir=target or "?"),
                         self.t("dl.version"))
            return False
        try:
            os.makedirs(target, exist_ok=True)
            names = [n for n in os.listdir(target) if n != ".temp"]
        except OSError as e:
            self.ui.fail(str(e), self.t("dl.version"))
            return False
        if names and not self.ui.confirm(
                self.t("dl.dir_has_content", dir=target), self.t("dl.version")):
            return False

        with self._lock:
            self.busy = True
        self._cancel.clear()
        self.events.put(("dl_busy", True))
        threading.Thread(
            target=self._worker,
            args=(repo_key, mirror, ref, target, set_service_dir, keep_temp),
            daemon=True).start()
        return True

    def cancel(self):
        self._cancel.set()

    def _worker(self, repo_key, mirror, ref, target, set_service_dir,
                keep_temp):
        try:
            downloader.install_game(
                repo_key, mirror, ref, target,
                progress=self._progress_cb,
                cancel=lambda: self._cancel.is_set(),
                delete_temp=not keep_temp)
        except downloader.DownloadCancelled:
            self.events.put(("dl_canceled",))
            return
        except Exception as e:
            self.events.put(("dl_fail", self.t("dl.fail", e=str(e)), False))
            return
        if set_service_dir:
            self.cfg.update(game_dir=target)
        self.events.put(("dl_done", target, set_service_dir))

    def _progress_cb(self, done, total, stage=None):
        if stage == "extract":
            self.events.put(("dl_log", self.t("dl.unzip")))
            return
        pct = 0
        if total:
            pct = min(99, int(done * 100 / total))
        self.events.put(("dl_progress", pct))

    # ---------------- 事件同步 ----------------
    def sync_event(self, item):
        """前端渲染事件之前调用：让 core 的内部状态跟上事件。"""
        kind = item[0]
        if kind in ("dl_done", "dl_fail", "dl_canceled"):
            with self._lock:
                self.busy = False
        if kind == "dl_fail" and self.logger is not None:
            self.logger.error(f"下载失败: {item[1]}")
