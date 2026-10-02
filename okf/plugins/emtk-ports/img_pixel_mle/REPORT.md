# emtk port report - `img_pixel_mle` (upgrade, audit-all row 68, imaging pixel family)

Agent: claude, 2026-10-02, per `UPGRADE_BRIEF.md`; board entry `T-20261002-IMGPIX`. Type B: the analysis is the Qt tool's Qt-free view model, unchanged; `gui/model.py` adds the emtk side.
The stream's hand-drawn app (`pre-upgrade/app.py.txt` and the other files there) is replaced by a spec form on the shared shell. Verdict: **accept**; open items in section 9.

Commits: `3441739bb` Qt baseline and the earlier stream's state, `4f27f6c79` app and tests, then the shared-shell / evidence commit (this report, screenshots, docs, log).

## 1. Checklist (Qt -> emtk -> test)
| Qt control | emtk | test |
|---|---|---|
| CLSM imaging files path list (add, drops, database, remove, clear) | `CLSM imaging files` list with `Add files` (multi-select chooser), `Database`, `Remove`, `Clear`, drops | `test_add_files_...`, `test_remove_and_clear_...`, `test_the_database_buttons_...`, `test_a_drop_...`, `test_the_qt_host_...` |
| IRF file list | `IRF file` list (one file) | `test_add_irf_takes_one_file_...` |
| Parallel / perpendicular channels, Fit start / stop, Micro-time binning, Min photons, Region | spec fields (typed, Qt ranges) + `Browse region` | `test_every_typed_setting_is_taken_on_enter` (12), `test_typed_numbers_are_clamped_...`, `test_the_region_file_...`, `test_a_region_confines_...` |
| Fit model + per-model parameter rows (value, fix) | `Fit model` list, rows of the selected model, each model keeps its own values | `test_the_fit_model_list_...` |
| IRF preparation, Fit flags, Background, Performance (folded) | same folding panels | `test_the_toggles_and_the_engine_choice_...` |
| Run; result file selector, colormap, z slider | `Run` (greyed with the reason), `Cancel`, `Result` list, colormap, frame slider | `test_run_is_greyed_...`, `test_run_is_pressed_...`, `test_cancel_stops_after_the_current_file...`, `test_the_result_list_...`, `test_the_wheel_zooms_...` |
Deliberate: the stream's extras that the Qt tool never had (rotation map, table preview, HDF5 / ndX export, Save container) are not carried (they are in `pre-upgrade/`); the Qt tool writes `<stem>_pixel_mle.csv` beside each input and so does this one. Viewer chrome in `deliberate.json`.

## 2. Numeric parity
tau maps, per-pixel tables, counts and the report equal the live Qt view model on the same files for the default and six setting sets (binning, IRF threshold / shift, background, 2I* / BIFL, loop engine, fit24); the CSV is written beside the input; the hub's setup / calibration reach the settings and a context that arrives while a worker runs is applied after it.

## 4. Docs
`docs/guides/24_scan_images.md` (figure `figures/24_mle_tool.png` from the emtk app), `gui/help.md`, `gui/guide.json` (8 steps, 3 awaiting: files, IRF, Run).

## 3. Tests and evidence
`python -m pytest chisurf/plugins/microscopy/img_pixel_mle/test` -> 73 passed (the new parity file plus the plugin's core and widget tests) in 38 s. Hermetic: temporary `CHISURF_SETTINGS_DIR` / `MMFDB_*` / HOME, seeded photon streams, no network, and a last test asserts the real
`~/.chisurf` is byte-for-byte unchanged. `compare` exit 0 (`compare.json`: lost [], stale_explanations [], untooltipped []), qt-free true. Layout asserted at 1200x800 and 800x600 (no overlapping text, controls inside,
image / plot area at least a quarter of the window, settings beside it).
Deliberate breakage, each restored and green after: the IRF no longer one file -> 1 failed; Cancel doing nothing -> 2 failed.

## 5. Real-input coverage
Every control of the checklist is pressed, typed into, dragged or wheeled through `Driver` (pointer press and release at drawn rectangles, Enter, host file drops incl. the Qt `ControlHost`); the guided tour is walked
operating each awaited control; no model call stands in for a click except where a test says otherwise.

## 6. Reuse
Shared: the `imaging_emtk` shell (`app_base`, `views.ImagePanel`, `testing.Driver`) and the family helpers added here once for all six plugins: `pixel_model` (actions,
worker bodies, hub adapters), `pixel_app` (hub contract, ndX over the maps, Cancel, MMFDB binding), `editors` (the detector editor window and the plane / region-list views),
`plane` (histogram on measured axes with draggable regions), `path_list`, `pixel_checks` (the checks every tool must pass) and `pixel_testing` (seeded photon streams). The detector /
channel editor `chisurf/emtk/channel_definition.py` is embedded as the Detectors tab (not edited), the region list is the shared `chisurf/emtk/regions.py` `RegionControls`, plus `DatasetPicker`,
`FileDialog`, `emtk_layout.layout_spec`, the help window and the guided tour. The stream's hand-drawn per-plugin copies of the file / ndX / dialog / region code are gone.

## 8. Layout
After screenshots read at full size: `after_populated_*_1200x800.png`, `*_800x600.png`, help, guide, dialogs (`after.json` is the union of every tab's inventory). Before (stream state): `before_emtk_populated_1200x800.png`:
unlabelled stacked buttons, detector windows as text. Fixed: spec form with capped widths and one label column, wrapped button rows, a View list because the tab row does not fit, the image / plot area on the right.

## 9. Gaps in shared code (not edited; repros)
1. `elide: "start"` in `input_text` clips the last characters of a long path (the file name) at the right edge of the field.
2. The embedded `ChannelDefinitionWidget` is taller than 800x600 and does not scroll: "Optical Setup..." is cut off at the bottom; it also draws its row buttons over their cells.
3. The tour card does not block what lies under it: a card over the coefficient table / a field makes Next and Close Tour dead (the tests drag the card away; coloc walks its tour through `tour.next()`).
4. `ImageCanvas` stacks colormap / gamma / levels / Reset above the image (about 110 px) and offers four colormaps (the Qt viewer had more).
5. An emptied text field is not committed on Enter (strict xfail in the phasor tests; a Clear IRF button replaces it).
6. The dataset picker's Open selected / Cancel share one id and never fire (known, img_drift REPORT); the tests use its own accept.
7. Core: `chisurf/core/fluorescence/imaging/pixel_maps.py` (foreign uncommitted edits, not touched) passes the phasor frequency straight to tttrlib, which takes cycles per micro-time channel: a typed MHz value
   gave (g, s) = (1, 0) for every pixel. Fixed in the plugin's view model (`PhasorImgViewModel._frequency_per_channel`), so the Qt tool is fixed too; a conversion in core `phasor_maps` / `phasor_frames` would be the clean place.
8. `imaging_tools/test/test_native.py::test_all_native_children_render_without_qt[molecule_mle]` fails: `region_mle.gui.app.make_app()` takes no `coordinator` (another stream's plugin).
