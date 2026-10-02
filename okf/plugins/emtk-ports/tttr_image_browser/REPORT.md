# emtk port report - tttr_image_browser (port-incomplete upgrade, audit-all row 81)

Agent (Sonnet), 2026-10-02; saved by the reviewer (the agent could not write it). Owner request: "emtk image browser needs improvement".
Commits `390d91ad2` Qt baseline + stream state, `c39bca140` app at parity, `304fab5c1` refit/fitted columns, `882c40ef7` rating labels + hub test, `9d6cd9461` evidence + docs + log, `463a08ab1`.

## What changed
The stream's app opened on the detector-setup page, hid the browser behind a second tab, stacked 14 full-width controls, drew the file list by hand and could not zoom with the wheel.
Now: Qt-free `gui/model.py` (extends the unchanged `ImageBrowserViewModel`), spec `gui/browser_emtk.view.json`, rewritten `gui/app.py`, `guide.json` (9 steps, 3 await), `help.md`.
Image browser is page 1 (toolbar row, Files `data_table` with filter/sort, rating filter and rating 0..3, annotation autosave, image window about 66% of the frame, histogram with two draggable level lines,
colormap (7) + gamma, Auto levels/Min/Max, tile labels, Reset view; **wheel zooms about the pointer, drag pans**); the detector setup is the shared `ChannelDefinitionWidget` hosted unchanged on tab 2.
Qt controls: 121 inventoried, all implemented or explained (80 deliberate entries). Numbers equal the live Qt tool (subprocess, SP8 and SP5): mosaic shape/labels/sha1, TIFF shapes and sums, copied bytes, metadata JSON, rating filters.

## Evidence
130 passed (117 new: parity 41, clicks 56, layout 20; 13 older green); compare exit 0, lost [], untooltipped [], 237 emtk controls; 4 deliberate breakages caught and restored. Real-input coverage per control in the agent hand-back (section 6a).
Defects found (Qt shares most): `get_magma_lut()` returned None on matplotlib 3.9 (grey DOCX pictures; fixed in `core/image.py` with a guard test); Qt DOCX needs python-docx (absent; emtk has an OOXML writer);
silent adoption of the last used setup; multi-selection could not toggle off; frozen form during jobs; stale wheel notch stepping the next spin field.
Layout fixes with before/after PNGs in `layout/`: stretched toolbar, overlapping tile labels at 800 px, setup editor in a 720-px column, fitted file columns, star glyph gap.

## Reuse and docs
Reused: shared `ChannelDefinitionWidget` (no copy), `ImageCanvas.texture`, `SnapshotJob`, help/tour, `emtk_layout`, `FileDialog`/`DialogWindow`, spec forms, `data_table`. Flagged duplicates: ~30 lines of file-dialog handling, ~40 lines of `ImageCanvas.draw` plot setup.
Docs: new `docs/guides/86_image_browser.md` (3 regenerated figures), index, concept section in `imaging_flim_phasor.md`, link in guide 24, reference page regenerated.

## Open
Shared setup editor offers 8 of the 15 Qt TTTR formats (CZ-RAW, SM, PHOTONS, PHOTON-HDF5, SPC-QC, SPC-600_4096, BRIGHTEYES-TTR, FLIMLABS-STT1/ITT1 missing) and stretches fields; `data_table` has no Ctrl/Shift multi-select;
`PixelPainter` ignores the clip for images; a used wheel notch stays pending; `ImageCanvas.draw` stacks controls and has 4 of 7 colormaps. Repros in `scripts/gap_*.py`.

## Review (reviewer, 2026-10-02)
Re-run: 130 passed; compare exit 0, lost []; populated 1200x800 screenshot read (toolbar, Files column, mosaic with tile labels, histogram with level lines, status bar). **Accepted with one blocked item** (the 9 TTTR formats in the shared editor).
