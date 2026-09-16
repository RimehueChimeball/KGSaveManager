"""存档库与槽位的文件逻辑（不含任何界面调用）。

槽位模型：存档库中的文件名 `<名字>_<槽位号>.kgsav`（槽位号 1..N，不补零）
决定槽位；同一槽位有多个文件时取修改时间最新者；名字完全来自文件名，
配置文件不保存槽位名。
"""

import os
from datetime import datetime
from pathlib import Path

SAVE_SUFFIX = ".kgsav"
MAX_SLOT_NAME_LEN = 40
INVALID_NAME_CHARS = '\\/:*?"<>|'


def parse_filename(filename, slot_count):
    """解析 `<名字>_<槽位号>.kgsav`。

    :return: (槽位号 0 起, 名字前缀)；不合规返回 None
    """
    if not filename.lower().endswith(SAVE_SUFFIX):
        return None
    stem = filename[:-len(SAVE_SUFFIX)]
    idx = stem.rfind("_")
    if idx <= 0:
        return None
    base, num = stem[:idx], stem[idx + 1:]
    if not num.isdigit():
        return None
    n = int(num)
    if not (1 <= n <= slot_count):
        return None
    return n - 1, base


class SlotStore:
    """存档库的扫描、显示名与文件读写。"""

    def __init__(self, library, t, slot_count=10):
        """
        :param library: 存档库目录（Path）
        :param t: 翻译函数 `t(key, **kw)`
        :param slot_count: 槽位数量
        """
        self.library = Path(library)
        self.t = t
        self.slot_count = slot_count
        self.info = []
        self.refresh()

    # ---------------- 扫描 ----------------
    def refresh(self):
        """重新扫描存档库，填充 `self.info` 并返回它。"""
        self.info = [{'exists': False, 'mtime': 0, 'name': ""}
                     for _ in range(self.slot_count)]
        try:
            files = list(self.library.iterdir())
        except OSError:
            files = []
        for p in files:
            if not p.is_file():
                continue
            parsed = parse_filename(p.name, self.slot_count)
            if parsed is None:
                continue
            i, base = parsed
            try:
                st = p.stat()
            except OSError:
                continue
            cur = self.info[i]
            if cur['exists'] and cur['mtime'] >= st.st_mtime:
                continue                      # 保留最新者
            self.info[i] = {
                'exists': True,
                'filename': str(p),
                'name': base,
                'time': datetime.fromtimestamp(st.st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"),
                'size': st.st_size,
                'mtime': st.st_mtime,
            }
        return self.info

    def exists(self, index):
        return bool(self.info[index].get('exists'))

    def path(self, index):
        """槽位文件路径；无文件返回 None。"""
        if not self.exists(index):
            return None
        return Path(self.info[index]['filename'])

    # ---------------- 显示名 ----------------
    def name(self, index):
        """槽位名（磁盘文件名前缀）；无文件返回空串。"""
        if index < len(self.info) and self.info[index].get('exists'):
            return self.info[index].get('name', "")
        return ""

    def name_text(self, index, exists):
        """名字显示区文案：有文件显示文件名前缀，无文件显示“空/empty”。"""
        return self.name(index) if exists else self.t("ui.empty_short")

    def label(self, index):
        """槽位列表显示文本：`<翻译前缀>NN.名字`。"""
        exists = index < len(self.info) and bool(self.info[index].get('exists'))
        return (f"{self.t('sv.slot_prefix')}{index + 1:02d}."
                f"{self.name_text(index, exists)}")

    def default_base(self, index):
        """无文件槽位新建存档时的默认文件名前缀（存档N，不补零）。"""
        return f"存档{index + 1}"

    def base_for_write(self, index):
        """写入该槽位时使用的文件名前缀：沿用已有名字，否则用默认名。"""
        return self.name(index) or self.default_base(index)

    # ---------------- 读写 ----------------
    def read(self, path, max_size):
        """读取存档文件并做体积校验；失败抛 ValueError（文案已翻译）。"""
        size = os.path.getsize(path)
        if size <= 0:
            raise ValueError(self.t("err.file_empty"))
        if size > max_size:
            raise ValueError(self.t("err.file_too_large", size=size))
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def write(self, index, text, max_size):
        """把存档文本原子写入槽位。

        只裁掉行尾换行：UTF-16 存档的尾部空格是载荷本身，整体 strip()
        会破坏它（详见 savecodec.validate 的格式判定）。

        :return: (路径, None) 成功；(None, (翻译键, 参数)) 失败；
                 文本为空时返回 (None, None)
        """
        text = (text or "").rstrip("\r\n")
        if not text.strip():
            return None, None
        if len(text) > max_size:
            return None, ("err.file_too_large", {"size": len(text)})
        base = self.base_for_write(index)
        dest = self.library / f"{base}_{index + 1}{SAVE_SUFFIX}"
        tmp = self.library / f".{dest.name}.tmp"
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(str(tmp), str(dest))
        except OSError as e:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return None, ("msg.process_fail", {"e": e})
        self.refresh()
        return dest, None

    def rename(self, index, new_base):
        """只改磁盘文件名：`旧名_N.kgsav` → `新名_N.kgsav`（不写入配置）。

        :return: (新路径, None) 成功；(None, 已翻译错误文案) 失败
        """
        new_base = (new_base or "").strip()
        if (not new_base or len(new_base) > MAX_SLOT_NAME_LEN
                or any(c in new_base for c in INVALID_NAME_CHARS)):
            return None, self.t("err.name_invalid")
        old_path = self.path(index)
        if old_path is None:
            return None, self.t("err.rename_need_file")
        if new_base == self.name(index):
            return old_path, None
        new_file = self.library / f"{new_base}_{index + 1}{SAVE_SUFFIX}"
        if new_file.exists():
            return None, self.t("err.name_file_exists", file=new_file.name)
        try:
            os.replace(str(old_path), str(new_file))
        except OSError as e:
            return None, str(e)
        self.refresh()
        return new_file, None

    # ---------------- 异常检查 ----------------
    def check(self):
        """检查存档库与临时目录中的异常文件。

        :return: {'invalid': [...], 'empty': [...], 'temp': [...]}
        """
        try:
            library_files = sorted(os.listdir(self.library))
        except OSError:
            library_files = []
        valid = {f for f in library_files
                 if parse_filename(f, self.slot_count) is not None}
        invalid = [f for f in library_files if f not in valid]
        empty = []
        for name in valid:
            p = self.library / name
            try:
                if p.is_file() and p.stat().st_size == 0:
                    empty.append(name)
            except OSError:
                pass
        return {'invalid': invalid, 'empty': empty}
