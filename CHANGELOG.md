# Changelog

All notable changes are listed by version.

## v1.3.0

- Manual import replaced the temp-folder monitoring with an explicit file
  choice. The dialog no longer watches a folder: it offers “Browse for a save
  file” (system file dialog in the Tkinter frontend, the browser's file picker
  in the HTML frontend) and keeps the text area for pasting a save. The file you
  pick is read and written into the selected slot, is validated first, and is
  left untouched — the old behaviour deleted the consumed temp file. The
  previous slot content is still backed up to `kgsm_data/backups/` before being
  overwritten, and the whole candidate/polling state machine (candidate reset,
  half-written download suffixes, two-minute give-up, folder snapshots) is gone.
- The dialog now explains the save library: it shows the library folder with a
  Copy Path button and states that a save's slot comes from its file name
  (`name_1.kgsav` … `name_10.kgsav`), so files can be renamed in the file
  manager and picked up with Refresh.
- Both frontends now ship an application icon: the executables use `assets/KGSaveManager.ico`, the Lite window and its dialogs use the same icon, and the HTML version serves it as its favicon (`webapp/assets/favicon.ico` plus a PNG generated from it).

- Ported the v1.2.3 fixes into this line (bug fixes only, no feature changes):
  the default branch is now detected reliably instead of being guessed as `main`
  (the original repository only has `master`, so guessing made every download
  source answer 404 when the GitHub API was rate limited); the version list is
  cached for ten minutes and only refetched when the button is pressed; the
  download log explains why a fallback happened. The Lite (Tkinter) frontend also
  reports unhandled interface-callback exceptions (run log, page log and a dialog
  with the log path) instead of failing silently, and cancels its pending UI poll
  job on exit.
- The HTML frontend is now the main version and keeps the plain name
  `KGSaveManager.py`; the Tkinter frontend is the Lite version
  (`KGSaveManagerLite.py`). Both share `kgsm_data/` and behave identically.
- HTML interface: the whole UI is rendered in the system browser (Edge/Chrome
  app window) and talks to the same logic layer over a local HTTP/JSON API. No
  third-party dependency.
- Layered architecture: `core/` now holds all UI-agnostic logic (paths, config,
  logging, slots, save flows, web server and bridge lifecycle, downloader
  controller, save editor controller) and reaches the screen only through the
  `core.ui_port.UiPort` port. `ui_tk.py` implements that port for Tkinter;
  `webapp/` implements it for the browser.
- The Tkinter pages (`pages_manual.py`, `pages_editor.py`,
  `pages_download.py`) are views only: they build widgets, call `core`, and
  render events. `save_flows.py` was replaced by `core/flows.py` plus
  `pages_manual.py`.
- Web UI: page navigation, launch page with live log, save management with
  per-slot notes, manual save (drop a file into the temp folder or paste text),
  save editor (tree and JSON source), game downloader with progress and
  connectivity test, settings, bilingual strings pushed from the backend.
- The HTML frontend has its own self-test (`?selftest=1`) and the test suite
  drives it with headless Edge, so the browser UI is verified end to end.
- Ported the v1.2.4 fixes into this line (bug fixes only, no feature changes):
  save payloads keep their trailing whitespace, because a UTF-16 save is padded
  with spaces that are part of the payload and a whole-string trim corrupted it
  (only trailing line endings are trimmed now, and the codec accepts both a raw
  and a line-trimmed blob); the manual-save candidate scan no longer stalls
  when the exported file is renamed or deleted, ignores half-written browser
  downloads (`.crdownload`, `.part`, `.tmp` and friends), accepts a file that
  was already in the temp folder before the dialog opened, and gives up on a
  candidate that never stops growing after two minutes; overwriting a slot
  backs the previous file up into `kgsm_data/backups/` first.
- Bridge fixes from the same round: a second `request_save` while one is in
  flight now waits for the first instead of failing instantly (which surfaced
  as a bogus "timeout/decode failed"), the caller's timeout is honoured, and
  `apply_save` waits for the page to acknowledge the write — it reports
  confirmation, a page error, or "sent but unconfirmed" instead of assuming
  success on send. Live reads and live writes in the editor, and loading a slot
  into the game, run on background threads in both frontends so the window no
  longer freezes for the seconds the page needs to answer.
- The automatically assigned HTTP port is no longer written back to the
  configuration (the old behaviour stored a temporary port as a fixed one, so
  the next start failed when that port was taken); the launch log states that
  the port was chosen for this run only. The download log's cache note now
  reports the cached default branch instead of the raw list and source.
- Tests: 198 cases covering core (slots, flows, editor, download, server),
  bridge protocol and keepalive, injected script, downloader, i18n across
  Python and web assets, dead-code checks, and the browser self-test run.
- Note: pywebview was evaluated for an embedded-window variant and rejected —
  pywebview 6.2.1 with pythonnet 3.1.0 on Python 3.14 fails with an
  `AccessibilityObject.Bounds` recursion error and hangs. The browser-based
  frontend needs no third-party dependency at all.

## v1.2.2

- Bridge diagnosis corrected: `<div id="game">` is exposed as `window.game`
  before the game boots, which was misread as "engine exists but has no
  `save()`". DOM nodes are now excluded from engine candidates, the engine
  is re-scanned while booting, and `hello` is sent again once the engine is
  ready, so the log shows the real engine state.
- Live reads wait for the engine (up to five seconds) before falling back to
  the browser autosave snapshot, and the server log reports the data source
  (`engine` or `localStorage`).
- Idle bridge connections are kept alive with WebSocket ping frames instead
  of being closed after 30 seconds; a connection that stops answering pongs
  is reclaimed after 75 seconds. This removes the periodic
  disconnect/reconnect cycle in the launch log.
- Manual save: an existing file overwritten with different content is now
  detected (previously only brand-new file names were), the consumed temp
  file is deleted after a successful import, and files older than seven days
  are cleaned from the temp folder at startup.
- Mirror list fixed: the `ghproxy.net` entry pointed at the unrelated
  `mirror.ghproxy.com` domain, which no longer responds.
- Dead code removed: the pre-redesign home-page actions
  (`kgm_quick_run`, `kgm_copy_run`, `_resolve_kgm_save`,
  `_refresh_kgm_dir`, `_refresh_kgm_save`, `kgm_mode_var`,
  `open_download_tab`, `MONITOR_TIMEOUT`, `GAME_DOWNLOAD_URLS`, unused JSON
  helpers and imports). `msg.monitor_timeout` and 38 other translation keys
  without a reference were dropped.
- Default Save Slot (previously "Home Save Slot") now selects the slot used at startup (it had no consumer
  after the home page redesign).
- Save codec: compression now works on UTF-16 code units like the JS
  original, so saves containing non-BMP characters (emoji) round-trip
  without corruption.
- Tests added under `tests/` (standard library only): save codec round-trip
  and parity with the game's `lib/lz-string.js`, downloader extraction,
  bridge protocol and keepalive, injected page script scenarios, slot
  writing, translation tables, and static checks against unused imports,
  unreferenced functions and unused translation keys.

## v1.2.1

- Save bridge: engine discovery across window keys and `gamePage`;
  LZString compression fallback; live reads no longer depend only on
  `window.game`.
- Bridge diagnostics: the launch-page server log now shows connect /
  disconnect, the hello probe (engine capabilities and found keys), save
  request timeouts and send results.
- Bridge robustness: requests prefer the newest page connection; stale
  connections are dropped on send failure and retried.
- Reconnect wait: auto save, auto load and editor live operations wait up
  to six seconds for the page to reconnect after a reload before reporting
  an error.
- HTML injection is placed before the closing body/html tags; responses are
  marked `Cache-Control: no-store` to avoid a stale bridge script.

## v1.2.0

- Save Editor: before opening a slot file, a dated backup is written to
  `kgsm_data/backups/` as `name.kgsav.YYYYMMDD_HHMMSS.bak`.
- Home (KGSM): redesigned with page buttons on the left and a getting
  started flow on the right (read guide, download, configure, launch).
  The page title is retained.
- External translations: JSON and PO files under `i18n/` are loaded at
  startup. The guide documents the format and key prefixes.
- Save Editor view: array elements are labeled with the index and, for
  objects, the first key and value.
- Paths are normalized when saved (quotes removed, backslashes used).
- Run log system: `kgsm_data/kgsm_log/<start time>.log`, one file per
  launch.
- English offline documentation added: `docs/guide_en.html`, bundled with
  the executable.
- Documentation wording revised to plain technical language.

## v1.1.0

- Logs and dialogs fully localized (zh/en).
- README restructured: English main file, separate Chinese version.
- PyInstaller spec updated with explicit modules; build verified.
- Slot recognition reads names from library filenames; config stores only
  notes.
- Save Editor added: decode, edit (view/source), re-encode and write back;
  lz-string compression ported for write-back.
- Auto save and auto load over a local WebSocket bridge; manual save
  dialog (file import or pasted text with validation).
- Download Game page: repositories, versions, mirrors, connectivity test,
  flattened extraction.
- Code split into modules with page mixins.

## v1.0.0

- Initial release: tabbed GUI (KGSM, Launch Game, Save Management,
  Settings), 10 save slots, notes persistence, local web server, bilingual
  UI.
