# emtk port report - `img_coloc` (upgrade, audit-all row 74, imaging pixel family)

Agent: claude, 2026-10-02, per `UPGRADE_BRIEF.md`; board entry `T-20261002-IMGPIX`. Type B: the analysis is the Qt tool's Qt-free view model, unchanged; `gui/model.py` adds the emtk side.
The stream's hand-drawn app (`pre-upgrade/app.py.txt` and the other files there) is replaced by a spec form on the shared shell. Verdict: **accept**; open items in section 9.

Commits: `425d73204` Qt baseline and the earlier stream's state, `40fe09210` app, tests and the shared editors / planes / path list helpers, then the evidence commit (this report, screenshots, docs, log).

## 1. Checklist (Qt -> emtk -> test)
| Qt control | emtk | test |
|---|---|---|
| Toolbar Run, Estimate background, Export CSV | `Run`, `Estimate background`, `Export CSV` (dialog, default name `<image>.coloc.csv`) | `test_run_is_greyed_...`, `test_estimate_background_...`, `test_export_csv_...`, `test_export_cancel_...` |
| Setup picker | the Detectors tab (the Setup tool's editor, with its saved-setup row) | `test_a_photon_stream_uses_the_detector_windows_...`, `test_the_detectors_window_...` |
| Image data source (browse, database, drop) | `Image` typed / `Browse` / `Database` / drop; choosing runs it | `test_a_typed_path_*`, `test_browse_*`, `test_the_database_*`, `test_a_drop_*` |
| Channel A / B, Frame, Axis order | lists and spin field | `test_the_channel_lists_...`, `test_every_typed_setting_...` |
| Background / thresholds (Auto background, Quantile, Background A / B, Costes thresholds, Threshold A / B) | same panel | settings tests, `test_every_setting_gives_what_the_qt_tool_gives...` (10 sets) |
| Scatter gate (Gate active, A / B min / max, region list, Clear gate), scatter rectangle, painted population | same + shared region list, handles dragged, `Paint gate` | `test_the_typed_box_...`, `test_a_gate_region_added_...`, `test_the_box_handle_dragged_...`, `test_a_scatter_population_painted_...`, `test_gates_and_the_painted_region_are_saved_...` |
| Region of interest (Brush px, Clear ROI, painting on Channel A) | `Paint ROI`, `Erase`, `Brush (px)`, `Clear ROI` | `test_a_region_is_painted_on_channel_a_...`, `test_without_paint_roi_...` |
| Objects, Significance / profile fields | same folding panels | typed-setting and toggle tests |
| Coefficients table, Channels, Colocalized pixels, Intensity scatter, van Steensel CCF, CCF map, PCC vs intensity, Objects, Object distances | the same nine tabs (data_table, two canvases, plane, series plots) + View list | `test_the_coefficient_table_...`, `test_the_picture_tabs_...`, `test_the_wheel_zooms_...`, `test_the_view_list_...` |
Deliberate: Qt painted with a modifier key; emtk has explicit `Paint ROI` / `Paint gate` / `Erase` switches (without them a drag pans). The Qt setup picker is replaced by the shared detector editor. Viewer chrome in `deliberate.json`.

## 2. Numeric parity
Every coefficient row, both maps, the mask, the histogram, the CCF map and the object map equal the live Qt view model for the default and ten setting sets; Pearson equals scipy's on the thresholded pixels (1e-9); the CSV equals the Qt file; the photon-stream path (detector windows as channels) equals the Qt model.

## 4. Docs
`docs/guides/38_colocalization.md` (buttons without emoji, figures `coloc_workspace.png`, `coloc_objects.png`, `coloc_object_distances.png`, `coloc_scatter.png` regenerated from the emtk app on a seeded two-channel image, captions say so), `gui/help.md`, `gui/guide.json` (6 steps, 1 awaiting: the image).

## 3. Tests and evidence
`python -m pytest chisurf/plugins/microscopy/img_coloc/test` -> 136 passed, 1 strict xfail (picker Open selected) in 40 s. Hermetic: temporary `CHISURF_SETTINGS_DIR` / `MMFDB_*` / HOME, seeded photon streams, no network, and a last test asserts the real
`~/.chisurf` is byte-for-byte unchanged. `compare` exit 0 (`compare.json`: lost [], stale_explanations [], untooltipped []), qt-free true. Layout asserted at 1200x800 and 800x600 (no overlapping text, controls inside,
image / plot area at least a quarter of the window, settings beside it).
Deliberate breakage, each restored and green after: a gate no longer switching gating on -> 3 failed; the status after a run replaced -> 3 failed.

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
