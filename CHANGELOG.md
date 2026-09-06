# Changelog

All notable changes are listed per version. Versions below are private
development history; the repository has not been made public yet.

## v1.2.0 (in development)

- Save Editor: opening a slot file now writes a dated backup to
  `kgsm_data/backups/` using the format `name.kgsav.YYYYMMDD_HHMMSS.bak`.
- Home (KGSM): redesigned. Left column lists buttons for all other pages;
  right column shows a getting-started flow (read guide, download,
  configure, launch). Page title retained. Copyright line added at the
  bottom left.
- External translations: JSON and PO files under `i18n/` are loaded at
  startup; documentation describes the file format and lists key prefixes.
- Save editor view: array elements are labeled with the index and, for
  objects, the first key and value.
- Paths are normalized when saved (quotes removed, backslashes used).
- Run log system: `kgsm_data/kgsm_log/<start time>.log` per launch.
- English offline documentation (`docs/guide_en.html`) added and bundled
  with the executable.
- Documentation wording revised to plain technical language.

## v1.1.0

- Runtime logs and dialogs fully localized (zh/en).
- README restructured: English is the main file, Chinese version separate.
- PyInstaller spec updated with explicit modules; build verified.
- Save recognition reads slot names from library filenames; the config
  file stores only notes.
- Editor page: decode, edit (view/source), re-encode and write back;
  lz-string compression ported for write-back.
- Auto save and auto load over a local WebSocket bridge; manual save dialog
  (file import or pasted text with validation).
- Download Game page: repositories, versions, mirrors, connectivity test,
  flattened extraction.
- Code split into modules with mixin pages.

## v1.0.0

- Initial public-facing version: tabbed GUI (KGSM, Launch Game, Save
  Management, Settings), 10 slots, notes persistence, local web server,
  bilingual UI.
