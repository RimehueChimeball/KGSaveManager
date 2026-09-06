# Changelog

All notable changes are listed by version.

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
