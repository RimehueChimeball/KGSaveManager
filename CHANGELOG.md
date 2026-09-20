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
  run falls back to an automatically assigned port, warns in the launch log and
  records the new port. The download log's cache note now reports the cached
  default branch instead of the raw list and source.
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
  game directory, port, browser and default slot are written on change/blur
  (matching the existing “all changes are saved automatically” hint). The
  sidebar button is now “Exit” with its own confirmation text, and the download
  page's dismiss button is “Cancel” instead of “Close”.
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
