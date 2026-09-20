# KGSaveManager

A save manager for Kittens Game on Windows, written in Python with no
third-party dependencies.

Two frontends share one logic layer and the same `kgsm_data/` folder:
- **Main version — HTML UI** (`KGSaveManager.py` + `webapp/`) — the interface is a
  local web page opened as a browser app window (or as a browser tab, a setting on
  the Settings page); the window title and icon come
  from the page (`<title>`, `favicon.ico`, `manifest.webmanifest`), and the page
  can be installed as a standalone app from the browser menu.
- **Tk version — Tkinter UI** (`KGSaveManagerTk.py`) — the classic desktop
  window: its own interface needs no browser and opens no local port (folders are
  picked with the system dialog; the game itself is still a web page and still
  opens in the browser), for users who prefer it or have no Edge/Chrome.

## Features

- Bilingual interface (Chinese / English); language is detected from the system on first run
- Tabs in fixed order: KGSM, Launch Game, Save Management, Edit Save, Download Game, Settings
- Save Management: 10 slots recognized from filenames (`name_1.kgsav` .. `name_10.kgsav`); auto save (WebSocket bridge), manual import (browse for a file or paste text), copy save, auto load, rename, refresh, per-slot notes, abnormal-file check
- Edit Save: open a slot file or the running game; view/source modes; value editing; backup (`.bak`); write-back re-encodes to the game format
- Launch Game: local static web server (127.0.0.1) with an injected save bridge; opens the game in a new browser window; the bridge reports whether the save came from the running game or from the browser autosave snapshot
- Download Game: two GitHub repositories, GitHub direct or mirror sources, connectivity test, flattened extraction with `index.html` check
- Settings: language, browser, game directory, port, launch position (separate app window / browser tab) and window state (window / maximized / full screen); changes are saved automatically
- External translations: JSON or PO files in the `i18n/` folder next to the program
- Runtime data in `kgsm_data/`; run logs in `kgsm_data/kgsm_log/`, one file per launch
- Layered code: `core/` holds all UI-agnostic logic and reaches the screen only through a UI port (`core/ui_port.py`), so another frontend (for example an HTML/webview UI) can reuse it unchanged

## Run

```powershell
python KGSaveManager.py        # main version (HTML UI; opens a browser app window)
python KGSaveManagerTk.py     # Tk version (Tkinter UI)
```

The main (HTML UI) version accepts `--port N`, `--no-browser` and `--verbose`.
The page address is printed on startup; append `?selftest=1` to run its built-in
self-test. It exits only through the page's Exit button or Ctrl+C: it never
quits because the page stopped responding, since Chromium slows timers of a
hidden window to about once a minute.

## Quick Start

1. Download the game (Download Game tab, keep the default repository and version).
2. Set the game directory in Settings (the folder containing `index.html`).
3. Launch the game (Launch Game tab). The page connects to the save bridge.
4. Save or load saves in Save Management.

## Usage

- Auto Save: requires the game launched via KGSM and connected. Writes the current game save to the selected slot; confirms on overwrite.
- Manual Import: dialog showing the save library folder (Copy Path button). Use “Browse for a save file” to pick the save file exported by the game, or paste the save text and press OK. The content is validated before writing, the file you picked is left untouched, and the previous slot content is backed up to `kgsm_data/backups/` before being overwritten.
- Copy Save: copies the slot content to the clipboard for the game Import.
- Auto Load: confirms once, then sends the slot content to the game page; the page reloads and reports whether the page confirmed the write.
- Rename: renames the slot file. The slot must contain a save. A save's slot comes from its file name (`name_1.kgsav` … `name_10.kgsav`), so files renamed in the file manager are picked up by Refresh.
- Refresh: rescans the save library.
- Edit Save: open a file or live source; edit values in view mode or edit JSON in source mode; Write saves the result.

## Data Layout

```
program/
├─ KGSaveManager.py              main entry (HTML UI)
├─ KGSaveManagerTk.py            Tk entry (Tkinter UI)
├─ i18n.py / config_store.py / web_server.py / web_bridge.py
├─ savecodec.py / downloader.py
├─ pages_download.py / pages_editor.py / pages_manual.py  (Tkinter views)
├─ ui_tk.py                      Tkinter UI port
├─ core/                         UI-agnostic logic (paths / slots / flows /
│                                server / download / editor / ui_port / app)
├─ webapp/                       HTML backend (api.py, server.py)
│   └─ assets/                   index.html / app.js / style.css / selftest.js
├─ kgsm_logging.py / utils.py
├─ docs/guide_en.html / docs/guide_zh.html
├─ CHANGELOG.md / CHANGELOG_zh.md
├─ tests/                unit tests (standard library only)
└─ kgsm_data/
   ├─ kittens_saves/
   ├─ backups/
   ├─ kgsm_log/
   └─ kgsm_config.json
```

## Tests

```powershell
python -m unittest discover -s tests -t .
```

The suite covers the save codec (with an optional parity check against the
game's own `lib/lz-string.js` via Node.js), downloader extraction, the
WebSocket bridge protocol and keepalive, the injected page script, the core
logic layer (slots, flows, editor, download, server), the HTML backend over
real HTTP, the translation tables — and, when Edge or Chrome is installed, it
runs the HTML UI's self-test in a headless browser. It also fails when an
unused import, an unreferenced function or an unused translation key is left
in the code.

## Build

```powershell
pip install pyinstaller
pyinstaller KGSaveManager.spec        # dist/KGSaveManager/KGSaveManager.exe (main)
pyinstaller KGSaveManagerTk.spec      # dist/KGSaveManagerTk/KGSaveManagerTk.exe (Tk)
```

Output: `dist/KGSaveManager/KGSaveManager.exe` (main, HTML UI; bundles
`webapp/assets`) and `dist/KGSaveManagerTk/KGSaveManagerTk.exe` (Tk, Tkinter).

## License

MIT License. See [LICENSE](LICENSE). Copyright (c) 2026 RimehueChimeball.
