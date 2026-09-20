# Changelog

All notable changes are listed by version.

## v1.3.0

- Added an HTML interface as the main version, keeping the name `KGSaveManager.py` (backend in
  `webapp/`, assets in `webapp/assets/`): the interface is served on `127.0.0.1` and opened as a
  browser app window (Edge/Chrome `--app=`, no address bar or tabs), with the window size, title
  and icon provided by the page. The Tkinter frontend became the Tk version
  (`KGSaveManagerTk.py`) and is still shipped; both share `core/` and the same `kgsm_data/`.
- The HTML interface has six pages (home, Launch Game with a live log, Save Management with 10
  slots and notes, Edit Save with view/source modes and collapsible nodes, Download Game,
  Settings), supports `?page=…` deep links and runs a built-in self-test with `?selftest=1`.
- Interface style: ice-white background with a single misty blue-violet accent, hairline borders
  instead of drop shadows, serif headings with monospace eyebrow labels and a numbered pill
  navigation. Body colours were checked against WCAG AA (5.5:1 – 16.9:1 measured), and fill/ink
  is a fixed pair (4.69:1). Pages are single-column with their own vertical scrolling, and card
  grids use `minmax(0, 1fr)` so content cannot blow the layout out.
- Settings keep only what is actually used: language, browser, game directory, fixed port, where
  the game window opens (separate window (app mode) / browser tab) and resume automatically.
  Changes are saved as you edit them; the “Write” button is gone.
- Resume automatically (on by default): closing the game window or tab (a reload counts) stores
  the progress at that moment as `kgsm_data/session.kgsav`, and the next time the game is opened
  that save is restored as soon as the page connects — which makes it independent of the port,
  because the game's own save lives in browser storage isolated per origin (port included).
  Deleting or resetting the save inside the game clears this stored progress too.
- “Where the game window opens” applies only to the window “Launch Game” opens, which starts at
  the same size as the interface window; the program's own interface window is always an app
  window that sizes itself into a centred landscape window on load.
- The HTML version has no Browse buttons: a browser does not hand a page a local path (picking a
  file yields only its name), so paths are typed or pasted. Manual import uses the browser's own
  file picker; the Tk version keeps real system dialogs.
- Exiting: the page's Exit button, or simply closing the interface window (the backend waits a
  moment to be sure it is not a reload). The packaged HTML version has no console window — the
  address and logs live in the page, and run logs are still written to `kgsm_data/kgsm_log/`.
- Layering: `core/` holds all UI-agnostic logic (paths, config, logging, slots, save flows, web
  server and bridge lifecycle, downloader, save editor) and reaches the screen only through
  `core/ui_port.UiPort`. `ui_tk.py` and `webapp/` implement that port; page code only builds
  widgets, calls `core` and renders events.
- Manual Save is an explicit import now: pick a file (a system dialog in Tk, the browser's file
  picker in HTML) or paste the save text. The temp folder is no longer monitored,
  `kgsm_data/kgsm_temp` is not created or cleaned up any more, and the file you pick is never
  modified or deleted. Overwriting a slot still backs the old file up to `kgsm_data/backups/`.
- Port: with an empty port field the automatically assigned port is remembered and reused from
  then on; when a configured port is busy, this run falls back to an automatic port and the
  configured port stays as it was (an automatic port no longer replaces the value you set).
- The v1.2.3 and v1.2.4 fixes were ported into this line: default-branch detection, a ten-minute
  version-list cache, concurrent bridge requests and write confirmation, save payloads no longer
  being stripped, Manual Save no longer getting stuck, backup before overwrite, and more — each
  is described in full in the v1.2.3 / v1.2.4 sections above. Both of those releases shipped the
  Tkinter frontend only.
- The download page's two checkboxes line up with the first line of their labels; selects have a
  self-drawn chevron with room for it; slot labels read “存档NN-名字” / “Save NN-name”
  everywhere; a “Copy Path” button that should have been hidden no longer shows up in dialogs;
  the editor toolbar matches the Tk version (view/source on the left, open/write on the right)
  and starts with only the root level expanded; in live mode the slot dropdown is disabled.
- Offline documentation ships in English and Chinese (`docs/guide_en.html`,
  `docs/guide_zh.html`) plus a Chinese changelog `CHANGELOG_zh.md`. The in-app entries follow the
  interface language, and a file with the same name in `i18n/` can replace them.
- 221 tests, standard library only: save codec (compared against the game's own
  `lib/lz-string.js` when Node.js is available), slot scanning, save flows, editor, downloader,
  server and WebSocket bridge (including a Node harness for the injected script), i18n
  consistency across Python and the web assets, and dead-code checks. With Edge/Chrome
  installed, a headless browser also runs the HTML page's self-test.
- Two PyInstaller specs: `KGSaveManager.spec` (main version, bundles `webapp/assets`) and
  `KGSaveManagerTk.spec` (Tk version); both build an onedir bundle, and the two frontends are
  packaged separately as `KGSaveManager-v1.3.0-win-portable.zip` and
  `KGSaveManagerTk-v1.3.0-win-portable.zip`.

## v1.2.4

This version shipped the Tkinter frontend only (the HTML frontend arrives in
v1.3.0). It was released from the `release/1.2.x` branch; the fixes were ported
into the v1.3.0 line, see the “ported from v1.2.4” entry above.

- The application now ships its own icon: the executable shows it in Explorer and
  on the taskbar, and the main window and its dialogs use the same icon at
  runtime.
- Fixed Manual Save getting stuck forever: once a half-finished file (for
  example a browser's `.crdownload`) had been picked as the candidate and was
  then renamed or deleted, the dialog kept polling that path and never imported
  anything again. The candidate is now reset and rescanned when it disappears or
  when it does not stop changing for two minutes, and half-finished names
  (`.crdownload`, `.part`, `.tmp`, …) are ignored entirely.
- Manual Save now also works in the natural order “export the file first, then
  click Manual Save”: a file that is already in the temp folder is picked up as
  the candidate (the download log says so).
- Saves are no longer altered on import: only trailing line endings are removed
  instead of stripping the whole payload. UTF-16 saves end with padding spaces
  that are part of the data, so the old behaviour both changed the file and made
  the format check report “possibly invalid” for perfectly good saves.
  The codec now recognises the format first (JSON / Base64 / UTF-16) and the
  decoder tolerates the trailing padding being cut off, matching the game's
  JavaScript implementation.
- Auto Load and the editor's live write now wait for the page to confirm the
  result (`apply_ok` / `apply_err`) instead of reporting success as soon as the
  data was sent. If the page does not confirm in time, the dialog says so instead
  of claiming success. Both run in the background, so the window no longer
  freezes while waiting.
- The editor's “open from the running game” no longer blocks the window: the
  fetch runs in the background and the result is applied when it arrives.
- A slot file is backed up to `kgsm_data/backups/` before being overwritten by
  Manual Save or Auto Save, using the same naming as the editor.
- The automatically assigned port is no longer written into the configuration:
  it was stored as if it were a fixed port, so the next start failed whenever
  that port happened to be busy.
- Concurrent bridge requests no longer fail instantly: a request that arrives
  while another one is in flight waits for it instead of returning “no data”
  immediately, and the caller's timeout is honoured.
- Fixed the version-list cache log line printing the source where the branch
  belongs.
- Tests: added `tests/test_manual_save.py` (manual-save state machine) and
  extended the bridge tests (apply confirmation, concurrent requests).

## v1.2.3

This version shipped the Tkinter frontend only. It was released from the
`release/1.2.x` branch; the fixes were ported into the v1.3.0 line, see the
“ported from v1.2.3” entry above.

- Fixed the download page failing for the original repository
  (`nuclear-unicorn/kittensgame`) with every source reporting 404, while the
  community repository worked. The default branch was guessed as `main` whenever
  the GitHub API call failed; the original repository only has `master`, so all
  four sources answered 404. The branch is now detected properly: the API is
  queried first and, if it is unavailable (unauthenticated GitHub API calls are
  limited to 60 per hour per IP), the candidates are probed against the archive
  URL and the branch that actually exists is used. The download log now says why
  (for example “GitHub API unavailable (possibly rate limited), detected default
  branch: master”).
- The version list is cached for ten minutes and only refetched when the
  “Refresh versions” button is pressed, so browsing the page or switching
  language no longer burns the API quota.
- Fixed the Download Game page doing nothing when the download button was
  clicked: the version list stored the repository ref as a string while the
  start routine unpacked it as a `(kind, ref)` pair, so every click raised
  `ValueError: too many values to unpack` inside the Tkinter callback. In the
  packaged window build there is no console, so the failure was completely
  silent. The button now starts the download. (Broken since v1.2.0.)
- Unhandled exceptions in UI callbacks are no longer silent: they are written to
  the run log and the page log and shown in a message box with the log path.
- The download worker no longer touches Tkinter variables from its background
  thread (writing the game directory and syncing the input fields now happens on
  the UI thread after the `dl_done` event), which previously could raise
  `main thread is not in main loop`.
- The pending UI poll job is cancelled on exit, avoiding a Tcl error while
  shutting down.
- Added `tests/test_download_page.py`: it drives the download page with a stubbed
  downloader and fails if the button stops starting a download again.

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
