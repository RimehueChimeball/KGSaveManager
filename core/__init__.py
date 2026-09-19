"""core：与界面无关的逻辑层。

这一层的代码不允许 import 任何 GUI 工具包（tkinter / webview / …），
所有界面交互都通过 `core.ui_port.UiPort` 暴露。这样同一套逻辑可以接
Tkinter 前端、接 pywebview/HTML 前端，也可以在测试里接替身。

模块划分：
- `ui_port`：界面端口协议与无界面实现。
- `slots`：存档库与槽位的文件逻辑（扫描、命名、读写、改名、异常检查）。
- `flows`：自动存档 / 自动读档 / 手动导入流程与事件处理。
"""

from .flows import SaveFlows
from .slots import SlotStore, parse_filename
from .ui_port import NullUiPort, UiPort

__all__ = [
    "NullUiPort",
    "SaveFlows",
    "SlotStore",
    "UiPort",
    "parse_filename",
]
