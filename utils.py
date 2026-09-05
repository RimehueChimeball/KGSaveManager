"""
DPI设置
"""

import sys


def setup_dpi_and_scaling():
    """
    设置Windows DPI和高清缩放
    目的：解决Windows高分辨率屏幕显示模糊的问题
    """
    # 只对Windows系统进行DPI设置
    if sys.platform == "win32":
        try:
            # 导入Windows API相关模块
            from ctypes import windll

            # 方法1：现代DPI感知API（Windows 8.1及以上版本）
            try:
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                # Windows 8.1以下版本不支持此API，忽略错误
                pass

            # 方法2：旧版DPI感知API（Windows Vista及以上版本，兼容性更好）
            try:
                windll.user32.SetProcessDPIAware()
            except Exception:
                # 如果旧版API也失败，忽略错误
                pass

        except Exception as e:
            # 防止任何意外错误导致程序崩溃
            print(f"DPI设置警告: {e}")
