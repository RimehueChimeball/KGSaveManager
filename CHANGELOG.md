# Changelog

All notable changes are listed by version.

## v1.3.0

- Second frontend: an HTML interface (`KGSaveManagerWeb.py` + `webapp/`) that
  renders the whole UI in the system browser (Edge/Chrome app window) and talks
  to the same logic layer over a local HTTP/JSON API. Both frontends share
  `kgsm_data/` and behave identically.
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
- Tests: 152 cases covering core (slots, flows, editor, download, server),
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
