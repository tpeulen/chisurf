# emtk upgrade report - `clsm_generator` (audit-all row 67)

Agent: claude (Sonnet), 2026-10-03, board `T-20261002-EMTKUP5`. Verdict: **accept**. Commits: `5bf40b23f` (Qt baseline + the stream's app, `pre-upgrade/`), then app/tests and evidence/docs commits.

## 1. Baseline and defects
Qt populated baseline (`before_populated_{empty,maps_loaded,generated,maps_tab}.png`; inputs: a 64 x 64 two-blob brightness image and two lifetime maps, `scripts/fixtures.py`; 129,201 photons) and the earlier emtk app (`before_emtk_generated_1200x800.png`). The earlier app: one button per line, the lifetime list a plain selectable list, the simulation fields stacked sliders, captions of Output format / Map to the right of their fields, no wrapping of the button rows, the tour's last card able to lose presses over the map canvas.

## 2. Checklist of the Qt controls
Intensity image + browse, lifetime list (Files, Database, Remove, Clear), Simulation fold (pixel size, dwell, micro-time channels, channel width, brightness, IRF centre / sigma, lifetime and intensity levels), Generate, Save, status, Maps tab (Map choice and the viewer) -> all present: Intensity image, Add lifetime maps, Database lifetime maps, Remove selected, Clear maps, the lifetime `data_table`, the folded Simulation form with spin fields, Generate (+ Cancel generation), Save photon stream with the Output format choice, Save / Load settings, Map choice and canvas, Guide, Help.

## 3. Changes
Wrapping button rows, greyed Remove / Clear / Save until they apply, the lifetime maps as a `data_table` (select, Delete key), the Simulation panel through `draw_form` with spin arrows and steps (the spec had none), labels to the left of Map and Output format, pointer masked under the tour card over the map canvas (emtk gap, same helper as spot_finder / clsm).

## 4. Tests
`pytest chisurf/plugins/microscopy/clsm_generator`: **33 passed** (13 earlier + 20 new real-input tests: Intensity dialog (cancel, close, pick), lifetime dialog, drops (first an intensity image, then lifetime maps), row select, Remove selected, Delete key, Clear, greyed Save and the missing-input reason, nine simulation fields typed, clamped, arrowed and with garbage, Generate and the Map choice, Cancel generation, Save photon stream through the dialog as .npz and with an unknown suffix (the dialog appends the filter's suffix), settings round trip, Help/Guide with the tour walked, layout at 1200x800 and 900x650, HOME untouched). Breakage (restored): Remove selected pops the first row -> the lifetime test fails; settings load ignores the intensity path -> the round-trip test fails. `after`: 22 controls, 0 untooltipped, qt-free yes; `compare` exit 0 (`deliberate.json`).

## 5. Layout, reuse, docs
Read at 1200x800 and 800x600 (`after_populated_*`): nothing clipped; the map gets the space. Reused: `ImageCanvas`, `DatasetPicker`, `SnapshotJob`, `emtk_layout`, spec forms, `data_table`, `FileDialog`, help/tour, `real_input.Ui`, the Qt tool's `generator.view.json`. Docs: new `docs/guides/98_clsm_generator.md` (registered) with a figure from the app; the plugin had no guide.
