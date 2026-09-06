# KGSaveManager

A save manager for Kittens Game on Windows (Python + Tkinter, no third-party dependencies).

## Features

- Bilingual interface (Chinese / English); language is detected from the system on first run
- Tabs in fixed order: KGSM, Launch Game, Save Management, Edit Save, Download Game, Settings
- Save Management: 10 slots recognized from filenames (`name_1.kgsav` .. `name_10.kgsav`); auto save (WebSocket bridge), manual save (drop file or paste text), copy save, auto load, rename, refresh, per-slot notes, abnormal-file check
- Edit Save: open a slot file or the running game; view/source modes; value editing; backup (`.bak`); write-back re-encodes to the game format
- Launch Game: local static web server (127.0.0.1) with an injected save bridge; opens the game in a new browser window
- Download Game: two GitHub repositories, GitHub direct or mirror sources, connectivity test, flattened extraction with `index.html` check
- Settings: language, browser, game directory, port, home save slot; changes are saved automatically
- External translations: JSON or PO files in the `i18n/` folder next to the program
- Runtime data in `kgsm_data/`; run logs in `kgsm_data/kgsm_log/`, one file per launch

## Run

```powershell
python KGSaveManager.py
```

## Quick Start

1. Download the game (Download Game tab, keep the default repository and version).
2. Set the game directory in Settings (the folder containing `index.html`).
3. Launch the game (Launch Game tab). The page connects to the save bridge.
4. Save or load saves in Save Management.

## Usage

- Auto Save: requires the game launched via KGSM and connected. Writes the current game save to the selected slot; confirms on overwrite.
- Manual Save: dialog with the temp folder path (Copy Path button) and a text area. Drop the exported file into the temp folder, or paste the save text and press OK. Pasted content is validated.
- Copy Save: copies the slot content to the clipboard for the game Import.
- Auto Load: confirms once, then sends the slot content to the game page; the page reloads.
- Rename: renames the slot file. The slot must contain a save.
- Refresh: rescans the save library.
- Edit Save: open a file or live source; edit values in view mode or edit JSON in source mode; Write saves the result.

## Data Layout

```
program/
├─ KGSaveManager.py
├─ i18n.py / config_store.py / web_server.py / web_bridge.py
├─ savecodec.py / downloader.py
├─ pages_download.py / pages_editor.py / save_flows.py
├─ kgsm_logging.py / utils.py
├─ docs/guide_en.html
└─ kgsm_data/
   ├─ kittens_saves/
   ├─ kgsm_temp/
   ├─ kgsm_log/
   └─ kgsm_config.json
```

## Build

```powershell
pip install pyinstaller
pyinstaller KGSaveManager.spec
```

Output: `dist/KGSaveManager/KGSaveManager.exe`.

## License

MIT License. See [LICENSE](LICENSE). Copyright (c) 2026 RimehueChimeball.
