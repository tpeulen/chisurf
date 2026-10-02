# Shared detector setup editor: one page like the Qt page

Agent (Sonnet), 2026-10-02; saved by the reviewer. Owner target: `owner_target_qt_layout.png`. Commits `2773e29d6` (editor, core model, plugin, consumer tests), `c2ac8a8d0` (docs: guide 87, guides 86 and 37, figures), `6cbb3a585` (evidence, log, known issues, roadmap).
The editor was six tabs of stacked fields (8 of 15 file types, detectors as blocks). It is now the Qt DetectorWizardPage in one scroll: Setup row (combo, Save, Rename, Delete, Public, Calibration, ?), TTTR Reading routine (all 15 file types, Read, two-column timing grid, Plot),
PIE Windows (folded), Detectors (Polarization resolved, Add, data_table with typed cells and Qt range text `20:10`, `5:5`, `0:10;20:30`, Calc G / Delete), LUT handling (gate, Channel/LUT/Shift table, Assign LUT, Configure LUTs, Adjust shifts), Optical Setup.
Gaps fixed: range-text parity, last-used setup written on choice and opened at start (file and MMFDB), open-section state restored, a non-photon file raises like Qt (xfail now 4 passing tests), adding a LUT switches the gate on, rename keeps its place.
Setup row state moved to `chisurf/emtk/channel_setup_bar.py`. Consumers re-tested: setup_channel_definition 105, boarding 62, tttr_image_browser 130, trace_browser 185, audifier 15, microtime_histogram 13, count_rate 53, burst_background 26, bid_to_analysis 10, burst_irf_bg 64, accurate_fret 58, fcs_channel_preset 18, test/native_emtk/test_channel_definition.py 12.
Layout checked at 1200x800, 800x600, the 720-px image-browser column, the 43% bid_to_analysis column, 520 and 360 px. Real-input click tests for every control: `test_emtk_channel_page.py` (control -> test list in the agent hand-back). Breakage twice, restored.
Deliberate: cells open on double-click; no pictograms; blank setup reads "Unsaved"; G-Factor shows 1.0; Edit JSON and setups-file Load/Export removed (a dropped .json switches the library); Configure LUTs / Adjust shifts open in-app windows; LUT section open at first.
Reuse: `emtk_layout.button_row`, DialogWindow, FileDialog, TableBinding, implot, optical_configuration. Duplicate flagged: `burst_analysis/gui/setup_selection_app.py` (2178 lines), a second hand-written detector editor, to be replaced in that plugin's cycle; four copies of `pointer.py`.
emtk gaps (repros in the evidence): `data_table` has no action column (worked around with `_ButtonCells`), `input_int` is a drag field, `collapsing_header` spans the whole row, cells edit on double-click only.
Docs: guide 87 (new), 86, 37, figures, reference pages, plugin help/guide.

## Review (reviewer, 2026-10-02)
Re-run: setup_channel_definition 105 passed, boarding 62, tttr_image_browser 130; compare exit 0, lost []. Screenshots read at 1200x800 and 720x700: matches the owner's target layout. **Accepted.** `setup_channel_definition` is removed from `emtk_preview.json`.
