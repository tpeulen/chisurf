# emtk upgrade report - `spot_finder` (audit-all row 73)

Agent: claude (Sonnet), 2026-10-03, board `T-20261002-EMTKUP5`. Verdict: **accept**. Commits: `6604603f4` (Qt baseline + the stream's app/tests, `pre-upgrade/`), then app/tests and evidence/docs commits.

## 1. Baseline and what was wrong
Qt populated baseline: the tool's own known-field demo (four objects, simulated PTU), Preview and Detect: `before_populated_{empty,demo_loaded,preview,detected}.png`; emtk before: `before_emtk_detected_1200x800.png`. Found in the earlier emtk app: every button on its own line; the detector fields as sliders with captions above; Detector channels / Frame / Filter regions / Selected region with their captions to the right of the field; the summary printed twice; the run and measurement tables hand-drawn (`begin_table`); the file list a plain list; no rectangles for the spec fields (the tour could not point at them).

## 2. Checklist of the Qt controls
Files (path list: Files, Database, Remove, Clear) -> Add files, MMFDB datasets, Remove file, Clear files + a `data_table` (select, Delete key); Workflow, Detection name; Analysis region editor (shapes, clear, combine, save/load) -> the shared `RegionControls`; Detector (method, threshold, sigma, peak footprint), Spot width (4 fields), Filters (3), Pick by clicking (fit window, Add/Clear picks) -> spec forms with spin fields, folds; Load demo, Preview, Detect, Export, Guide, `?` -> Help; Region list/info/image with picking; Run table; region measurements; Save/Load settings; drops. All present; Detector channels, Frame, Write results are drawn in an Input fold.

## 3. Changes
Button rows wrap (`button_row`), spec forms through `draw_form` + `layout_spec` with spin arrows, the three tables are `data_table`s (the measurement columns come from the result), labels beside the fields, one status line; a tour card over a table lost its button presses to the table: while the tour is shown the tables get no pointer input (emtk gap, repro: a `data_table` under the tour card swallows the press). The last tour step's target "Run" now has a rectangle.

## 4. Tests
`pytest chisurf/plugins/microscopy/spot_finder`: **92 passed** (7 stream tests in `tests/`, 85 older tests, 17 new real-input tests in `tests/test_emtk_spot_finder_clicks.py`: add-files dialog (cancel, close, pick), drop, file-row select/remove/clear, workflow choice, typed/clamped/arrowed detector fields, folds, channels/frame/write toggle, Preview, Detect, no-files message, Export through the dialog, settings save/load round trip, result tabs and region filter, a click on the image picks and Add/Clear picks, Help/Guide with the tour walked, the demo button (real simulated PTU) and Detect finding 4, layout at 1200x800 and 900x650, HOME untouched). Breakage (restored): `remove_file` pops the first row -> `test_drop_add_files_dialog_remove_and_clear` fails; channel parse off by one -> `test_channels_frame_and_write_results` fails. `after`: 57 controls, 0 untooltipped, qt-free yes; `compare` exit 0 (`deliberate.json`).

## 5. Layout
Read at 1200x800 and 800x600 (`after_populated_*`): no clipped or overlapping text; the image gets the space; tables have headers and a count line.

## 6. Reuse and docs
Reused: `RegionControls`, `ImageCanvas`, `DatasetPicker`, `SnapshotJob`, `emtk_layout`, spec forms and `data_table`, `FileDialog`, help/tour, `traj_save_topology/test/real_input.Ui`, the Qt tool's `spot_finder.view.json`. Docs: `docs/guides/84_spot_finder.md` figure and caption of the window replaced by the emtk app; its two detail figures (camera data) still show the Qt tool (that dataset is not in the repository). Open: guide 84's text still names the Image Tools hub tabs in places.
