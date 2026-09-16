# Changelog

All notable changes are listed by version.

## v1.2.4

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
  decoder tolerates the trailing padding being cut off, matching the game’s
  JavaScript implementation.
- Auto Load and the editor’s live write now wait for the page to confirm the
  result (`apply_ok` / `apply_err`) instead of reporting success as soon as the
  data was sent. If the page does not confirm in time, the dialog says so instead
  of claiming success. Both run in the background, so the window no longer
  freezes while waiting.
- The editor’s “open from the running game” no longer blocks the window: the
  fetch runs in the background and the result is applied when it arrives.
- A slot file is backed up to `kgsm_data/backups/` before being overwritten by
  Manual Save or Auto Save, using the same naming as the editor.
- The automatically assigned port is no longer written into the configuration:
  it was stored as if it were a fixed port, so the next start failed whenever
  that port happened to be busy.
- Concurrent bridge requests no longer fail instantly: a request that arrives
  while another one is in flight waits for it instead of returning “no data”
  immediately, and the caller’s timeout is honoured.
- Fixed the version-list cache log line printing the source where the branch
  belongs.
- Tests: added `tests/test_manual_save.py` (manual-save state machine) and
  extended the bridge tests (apply confirmation, concurrent requests).

## v1.2.3

- The application now ships its own icon: the executable shows it in Explorer and
  on the taskbar, and the main window and its dialogs use the same icon at
  runtime.

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
