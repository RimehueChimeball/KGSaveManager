"""
kgsm_logging：运行日志系统。

- 保存位置：kgsm_data/kgsm_log/<启动时间>.log（每次启动一个新文件）
- 记录：启动信息（版本/平台/Python/配置概览）、服务与存档桥启停、
  存档操作（自动/手动/读档/改名/刷新/编辑写回）、下载操作、
  语言切换、错误等；附带时间戳与级别。
"""

import os
import platform
import sys
import threading
from datetime import datetime

APP_NAME = "KGSaveManager"


class AppLogger:
    def __init__(self, log_dir, app_version="", extra_header=None):
        self.log_dir = log_dir
        self.app_version = app_version
        self.extra_header = extra_header or []
        self._path = None
        self._fh = None
        self._lock = threading.Lock()
        self._open()

    def _open(self):
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._path = os.path.join(self.log_dir, f"{stamp}.log")
            self._fh = open(self._path, "a", encoding="utf-8")
            self.info(f"程序启动 {APP_NAME} {self.app_version}")
            self.info(f"平台: {platform.platform()} | Python: "
                      f"{platform.python_version()} | 进程: {sys.argv[0]}")
            for line in self.extra_header:
                self.info(line)
        except Exception as e:
            self._path = None
            self._fh = None
            print(f"[logger] 无法创建日志: {e}")

    @property
    def path(self):
        return self._path

    def _write(self, level, msg):
        if self._fh is None:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {level:<5} {msg}\n"
        with self._lock:
            try:
                self._fh.write(line)
                self._fh.flush()
            except Exception:
                pass

    def info(self, msg):
        self._write("INFO", msg)

    def warn(self, msg):
        self._write("WARN", msg)

    def error(self, msg):
        self._write("ERROR", msg)

    def action(self, action, detail=""):
        """带动作标签的记录，便于检索。"""
        self._write("INFO", f"[{action}] {detail}" if detail else f"[{action}]")

    def close(self):
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
