# KGSaveManager

A save manager for Kittens Game on Windows, written in Python with no
third-party dependencies.

Two frontends share one logic layer and the same `kgsm_data/` folder:
- **Main version — HTML UI** (`KGSaveManager.py` + `webapp/`) — the interface is a
  local web page opened as a browser app window.
- **Lite version — Tkinter UI** (`KGSaveManagerLite.py`) — the classic desktop
  window, for users who prefer it or have no Edge/Chrome available.

## Features

- Bilingual interface (Chinese / English); language is detected from the system on first run
- Tabs in fixed order: KGSM, Launch Game, Save Management, Edit Save, Download Game, Settings
- Save Management: 10 slots recognized from filenames (`name_1.kgsav` .. `name_10.kgsav`); auto save (WebSocket bridge), manual save (drop file or paste text), copy save, auto load, rename, refresh, per-slot notes, abnormal-file check
- Edit Save: open a slot file or the running game; view/source modes; value editing; backup (`.bak`); write-back re-encodes to the game format
- Launch Game: local static web server (127.0.0.1) with an injected save bridge; opens the game in a new browser window; the bridge reports whether the save came from the running game or from the browser autosave snapshot
- Download Game: two GitHub repositories, GitHub direct or mirror sources, connectivity test, flattened extraction with `index.html` check
- Settings: language, browser, game directory, port, default save slot (selected at startup); changes are saved automatically
- External translations: JSON or PO files in the `i18n/` folder next to the program
- Runtime data in `kgsm_data/`; run logs in `kgsm_data/kgsm_log/`, one file per launch
- Layered code: `core/` holds all UI-agnostic logic and reaches the screen only through a UI port (`core/ui_port.py`), so another frontend (for example an HTML/webview UI) can reuse it unchanged

## Run

```powershell
python KGSaveManager.py        # main version (HTML UI; opens a browser app window)
python KGSaveManagerLite.py   # lite version (Tkinter UI)
```

The main (HTML UI) version accepts `--port N`, `--no-browser`, `--serve` (keep running after the
window closes) and `--verbose`. The page address is printed on startup; append
`?selftest=1` to run its built-in self-test.

## Quick Start

1. Download the game (Download Game tab, keep the default repository and version).
2. Set the game directory in Settings (the folder containing `index.html`).
3. Launch the game (Launch Game tab). The page connects to the save bridge.
4. Save or load saves in Save Management.

## Usage

- Auto Save: requires the game launched via KGSM and connected. Writes the current game save to the selected slot; confirms on overwrite.
- Manual Save: dialog with the temp folder path (Copy Path button) and a text area. Drop the exported file into the temp folder, or paste the save text and press OK. Pasted content is validated. A new file, or an existing file overwritten with different content, is detected; the consumed temp file is deleted afterwards.
- Copy Save: copies the slot content to the clipboard for the game Import.
- Auto Load: confirms once, then sends the slot content to the game page; the page reloads.
- Rename: renames the slot file. The slot must contain a save.
- Refresh: rescans the save library.
- Edit Save: open a file or live source; edit values in view mode or edit JSON in source mode; Write saves the result.

## Data Layout

```
program/
├─ KGSaveManager.py              main entry (HTML UI)
├─ KGSaveManagerLite.py          lite entry (Tkinter UI)
├─ i18n.py / config_store.py / web_server.py / web_bridge.py
├─ savecodec.py / downloader.py
├─ pages_download.py / pages_editor.py / pages_manual.py  (Tkinter views)
├─ ui_tk.py                      Tkinter UI port
├─ core/                         UI-agnostic logic (paths / slots / flows /
│                                server / download / editor / ui_port / app)
├─ webapp/                       HTML backend (api.py, server.py)
│   └─ assets/                   index.html / app.js / style.css / selftest.js
├─ kgsm_logging.py / utils.py
├─ docs/guide_en.html
├─ tests/                unit tests (standard library only)
└─ kgsm_data/
   ├─ kittens_saves/
   ├─ kgsm_temp/
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
pyinstaller KGSaveManagerLite.spec    # dist/KGSaveManagerLite/KGSaveManagerLite.exe
```

Output: `dist/KGSaveManager/KGSaveManager.exe` (main, HTML UI; bundles
`webapp/assets`) and `dist/KGSaveManagerLite/KGSaveManagerLite.exe` (lite, Tkinter).

## License

MIT License. See [LICENSE](LICENSE). Copyright (c) 2026 RimehueChimeball.
