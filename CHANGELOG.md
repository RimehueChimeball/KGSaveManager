# Changelog

All notable changes are listed by version.

## v1.3.0

- HTML interface restyled after the reference design in
  `OpenDesign/Suzuyuki Corridor`: ice-white background with a single misty
  blue-violet accent, hairline borders instead of drop shadows, serif display
  headings with mono uppercase eyebrow labels per page, a light frosted sidebar
  whose navigation items are numbered pills (`01` … `06`, active item filled
  with the accent), light monospace log/code panels, numbered guide list and
  row-hover tables. Text combinations were checked against WCAG AA (5.5:1 to
  16.9:1; the hairline border is decorative, not text).
- The application window now opens in landscape. Chromium remembers the app
  window geometry per profile, so the launcher's `--window-size` is ignored
  once a window has been opened; the page therefore carries `fit=1` and sizes
  itself (measured: 1560x929, ratio 1.68, centred in the work area) unless the
  window is already wider than 1.15:1 and close to the target size.
- The temp folder (`kgsm_data/kgsm_temp`) is gone: it is no longer created,
  cleaned at startup or listed by the library check, because manual import now
  takes a file the user picks. Existing folders are left on disk untouched.
- HTML interface: wide multi-column layout (two columns from 1180px, three from
  1720px) with the content area scrolling on its own, so cards spread
  horizontally instead of stacking in one narrow column.
- The HTML page keeps the current tab in the address bar and accepts
  `?page=<kgsm|game|saves|editor|download|settings>` for deep links.
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
- Both frontends now ship an application icon: the executables use `assets/KGSaveManager.ico`, the Tk window and its dialogs use the same icon, and the HTML version serves it as its favicon (`webapp/assets/favicon.ico` plus a PNG generated from it).

- Ported the v1.2.3 fixes into this line (bug fixes only, no feature changes):
  the default branch is now detected reliably instead of being guessed as `main`
  (the original repository only has `master`, so guessing made every download
  source answer 404 when the GitHub API was rate limited); the version list is
  cached for ten minutes and only refetched when the button is pressed; the
  download log explains why a fallback happened. The Tk (Tkinter) frontend also
  reports unhandled interface-callback exceptions (run log, page log and a dialog
  with the log path) instead of failing silently, and cancels its pending UI poll
  job on exit.
- The HTML frontend is now the main version and keeps the plain name
  `KGSaveManager.py`; the Tkinter frontend is the Tk version
  (`KGSaveManagerTk.py`, packaged as `KGSaveManagerTk.exe`). Both share
  `kgsm_data/` and behave identically. The Tkinter frontend was called the Lite
  version while v1.3.0 was in development; the name was changed to Tk because
  “portable” describes both frontends equally and the difference between them is
  the interface technology.
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
- The port field keeps filling itself in: when no fixed port is configured, the
  automatically assigned HTTP port is written into the configuration and used as
  the fixed port from then on. A port that is already taken no longer breaks the
  next start — the port is probed first (Windows allows binding a busy port
  because of `SO_REUSEADDR`, so a bind test is not enough), and in that case the
  run falls back to an automatically assigned port and warns in the launch log.
  (The write-back rule was later corrected to “only when the field was empty”;
  see the busy-port entry above.) The download log's cache note now reports the
  cached default branch instead of the raw list and source.
- HTML page headers were trimmed: every page keeps the small bilingual eyebrow
  label as its title, and only the home page keeps the large serif heading, so
  the duplicated title no longer takes vertical space away from the content.
- Two interface faults fixed: the download page's two checkboxes sat at
  different heights (`.form label` out-specified `.check`, so the labels were
  block boxes with their own margins instead of flex rows — measured 8px apart,
  now flush and top-aligned), and the editor's tree got its collapse back: a
  triangle toggles a node, the state is kept per node path so it survives a
  re-render after editing a value (the root node's `path` is null, which is why
  the first attempt did nothing).
- The editor tree now starts like the Tkinter one: only the root level is
  expanded (both the synthetic `(root)` row and the save object itself), every
  nested container is collapsed, and the toggles are larger. The checkbox row
  keeps equal spacing above and below (16px each, it used to be 0 above and 22
  below, which read as "stuck to the top"), and selects use a drawn chevron with
  a 38px right padding instead of the browser arrow that sits against the edge.
- The editor toolbar mirrors the Tkinter layout again: view/source as a
  segmented switch on the left with a visible selection, open/write on the
  right.
- Button and pill fills use a lighter accent than the text accent: the text
  accent stays dark (`oklch(46% 0.105 262)`, hairlines and eyebrow labels) while
  fills use `oklch(56% 0.115 262)` (rgb(78,115,184)) with white ink (4.69:1,
  WCAG AA). The original dark fill read as too heavy, and anything paler than
  this step fails with white text.
- Documentation now ships in Chinese as well: `docs/guide_zh.html` (same
  structure and anchors as the English guide) and `CHANGELOG_zh.md` (mirrors
  this file section by section). The in-app entries pick the language: the
  about box offers “Offline guide” and “Changelog”, and the Tk version's
  guide button opens the Chinese guide when the interface is Chinese. Both
  changelogs are bundled by the PyInstaller specs.
- Settings are saved as you edit them: the “Write” button is gone and changes to
  game directory, port and browser are written on change/blur (matching the
  existing “all changes are saved automatically” hint). The
  sidebar button is now “Exit” with its own confirmation text, and the download
  page's dismiss button is “Cancel” instead of “Close”.
- Two new settings, <b>applying only to the window that “Launch Game” opens</b>
  (this program's own interface window stays an app window and keeps sizing itself
  into a centred landscape window on load): <b>game window opens in</b> (separate
  window (app mode) / browser tab) and <b>game window state</b> (window /
  maximized / full screen), both taking effect on the next start.
- “Launch Game” used to always open a plain browser window (with a tab strip and
  an address bar), so choosing app mode changed nothing there. It now follows the
  two settings; tab mode was measured to add a tab to the existing window instead
  of opening a new one (window count unchanged, title becomes “… and 1 other
  page”), and the state is greyed out there with that explanation.
- “Maximized” for the game window is a real maximize, applied through Win32
  `ShowWindow(SW_MAXIMIZE)`: measured client area 1920×1032 on a 1920×1032 work
  area, i.e. exactly filling it. A page-side `resizeTo` only sizes the outer frame
  to the work area and leaves a visible border (measured client area 1904×1024,
  which looks like a hand-made maximize), so it is now used for the interface
  window's landscape size only. “Full screen” uses `--start-fullscreen`, which was
  measured to work only when this launch starts the browser process (1920×1080,
  covering the taskbar); when the browser is already running the flag is ignored,
  the program falls back to maximized and says so in the run log and on the Launch
  Game page. Sending F11 natively was measured and does nothing, so that route was
  not used.
- Fixed the configured port being overwritten by an automatically assigned one:
  when the configured port is busy, the run falls back to an automatic port, but
  it no longer writes that new port back into the configuration. The old code
  cleared the “configured port” flag before deciding, so the user's fixed port was
  silently replaced — with a second copy of the program running (or the port taken
  by anything else), every start moved to a new random port, which is exactly what
  the repeated “fixed port N is busy, using an automatic port” lines in the run
  logs were. The configured value is now kept; the auto port is recorded only when
  the field was empty to begin with.
- The “Default Save Slot” setting is gone from both versions. It was the
  configuration entry for a Tk home-page feature that no longer exists; what
  remained was “which slot is selected at startup”, and in the HTML version it
  had no consumer at all — the page used `home_slot` only to fill its own
  dropdown, while the slot table always selected the first row (there was also a
  `default_slot` field in the API state that no frontend read). Configuration,
  API and translation keys are removed; a leftover `home_slot` in an existing
  config file is ignored and disappears on the next save.
- Exiting no longer leaves an error behind. The page used to await the
  `shutdown` call, so the closed server produced
  `ERROR TypeError: Failed to fetch` in the log; the request is now
  fire-and-forget, the app window closes itself and a plain browser tab shows
  “the program has exited; this page can be closed”.
- A button that should have been hidden showed up in every dialog: the
  “Copy Path” button appeared in the exit confirmation because
  `button { display: inline-flex }` out-specified the `hidden` attribute. A
  global `[hidden] { display: none !important }` fixes it for every element.
- Slot labels use the same text everywhere (“存档NN-名字” / “Save NN-name”, the
  separator is now a hyphen instead of a dot) and the slot table no longer
  appends the file name.
- Offline documentation follows the interface language, and external
  translations can replace it: the About box opens
  `docs/guide_zh.html` on a Chinese UI and `docs/guide_en.html` otherwise (the
  changelog link picks `CHANGELOG_zh.md` / `CHANGELOG.md`), and a file with the
  same name in `i18n/` wins over the bundled one, so a translated guide or
  changelog can be shipped without touching the program. The Tk version used
  to label its guide link with a hard-coded English file name.
- The document entries live on the home page only; the Settings page keeps a
  “Paths” card for the data folder instead of a second “About” block.
- Tk editor fixes: its slot dropdown was empty at startup, so pressing Open
  only produced “please select a slot that contains a save” even with saves in
  the library — the list is now filled while the page is built; and the
  view/source row no longer stretches vertically (two rows shared the extra
  height, leaving ~66px above and below it; now the content area takes it all).
- The main version no longer exits on its own. Chromium throttles the timers of a
  hidden page to about once a minute, so “the page has not spoken to us for a
  while” cannot tell an idle user apart from a minimised or covered window — the
  12-second watchdog first went to 180s, and the watchdog, its heartbeat
  endpoint (`/api/ping`) and the `--serve` flag it needed are now removed
  entirely. The program exits in exactly two ways: the Exit button in the page
  (closing the window triggers it too) and Ctrl+C in the console.
- Editor: the slot dropdown keeps the slot you picked. The list is redrawn from
  the backend on every refresh and used to jump back to the first entry each
  time you pressed Open. In live mode the dropdown is disabled and explains that
  live mode reads and writes the running game instead of a save slot.
- A merged design-system reference was added outside this repo at
  `Web_project/kgsm-design-system/`: this interface's own styling plus the
  elements the reference design has and this project did not use (tags, status
  badges, timeline rows, image placeholders, empty states, snow dividers,
  sparkle atmosphere, footer, frosted top nav, drawer, lift cards, scroll
  reveal, grid primitives), with a showroom page, split CSS
  (`tokens.css` / `base.css` / `components.css`), machine-readable
  `tokens.json`, and `README.md` / `AGENTS.md` / `SOURCES.md`.
- The HTML button fill uses the original accent hue lightened by one step
  instead of the cyan-leaning variant; the fill/ink pair, the active nav pill
  colours and the editor dropdown behaviour are asserted in the browser
  self-test.
- Tests: 208 cases covering core (slots, flows, editor, download, server),
  bridge protocol and keepalive, injected script, downloader, i18n across
  Python and web assets, dead-code checks, and the browser self-test run.
- Note: pywebview was evaluated for an embedded-window variant and rejected —
  pywebview 6.2.1 with pythonnet 3.1.0 on Python 3.14 fails with an
  `AccessibilityObject.Bounds` recursion error and hangs. The browser-based
  frontend needs no third-party dependency at all.

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
