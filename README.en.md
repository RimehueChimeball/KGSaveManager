# KGSaveManager

A Kittens Game save manager for Windows (Python + Tkinter, no third-party dependencies).

## Features

- Four tabs, fixed order: KGSM → Launch Game → Save Management → Settings (UI is bilingual, zh/en)
- Save Management: 10 slots, auto-detected from filenames `name_slot.kgsav`; save/load, rename (renames the file on disk only), manual refresh, auto-saved notes, abnormal-file checker
- Launch Game: local static web server (bound to 127.0.0.1 only), one click to start and open in a new browser window, with a live server log
- KGSM home: quick launch the game; copy a save and launch; two download links (author's original / community fork, both on GitHub)
- Settings: language, browser (system default auto-detected), game directory, port, home save slot; every change is auto-saved to `kgsm_data/kgsm_config.json`
- All data lives in `kgsm_data/` (save library, temp folder, config); back up or migrate by copying that one folder

## Run

```powershell
python KGSaveManager.py
```

## Usage

- Save: select a slot → click "Save" → paste the path copied by the program into the game's Export dialog and save as .txt
- Load: select a slot → click "Load" → paste (Ctrl+V) into the game's Import
- Rename: requires an existing save in the slot; renaming renames the disk file (`newname_slot.kgsav`); save first if the slot is empty
- Refresh: after adding/renaming files outside the program, click "Refresh" to rescan the save library
- Launch game: first set the game directory in Settings (point to the folder containing the game files)
- First time: open Settings to set the game directory, then download the game on the KGSM tab

## Layout

```
KGSaveManager/
├─ KGSaveManager.py     # Main program
├─ i18n.py              # zh/en translations
├─ config_store.py      # Config storage (auto-save)
├─ web_server.py        # Local web server
├─ utils.py             # Windows DPI settings
├─ KGSaveManager.spec   # PyInstaller config
├─ README.md / README.en.md
└─ kgsm_data/           # Runtime data (git-ignored)
   ├─ kittens_saves/    # Save library
   ├─ kgsm_temp/        # Export staging folder
   └─ kgsm_config.json  # Config (notes included)
```

## Build

```powershell
pip install pyinstaller
pyinstaller KGSaveManager.spec
```

Output goes to `dist/KGSaveManager/`.

## Notes

- Slot names come from save filenames and are not translated (they are the real filenames).
- Saving works by the game exporting into the temp folder, then the program moves, renames and overwrites the save in the library.
