"""HTML 前端的后端：界面端口实现、JSON API 与静态资源服务（纯标准库）。

浏览器里跑的页面通过 HTTP 与本模块通信：
- `GET  /`                 → 单页应用（HTML/CSS/JS）
- `GET  /api/state`        → 一次取走全部状态与文案表
- `POST /api/call`         → 调用一个 API 方法（见 `WebApi.METHODS`）
- `GET  /api/events?since` → 取 UI 事件（日志、进度、对话框、刷新）
- `POST /api/answer`       → 回答对话框（确认/输入）
- `POST /api/shutdown`     → 退出程序

之所以不依赖 pywebview：本机实测 pywebview 6.2.1 + pythonnet 3.1.0 在
Python 3.14 / .NET 上会陷入 `AccessibilityObject.Bounds` 递归错误并卡死
（详见项目计划书），而浏览器 + 本地 HTTP 服务只用标准库即可完成同样的
HTML 渲染，且用 Edge 的 `--app=` 模式也能得到独立窗口。
"""
