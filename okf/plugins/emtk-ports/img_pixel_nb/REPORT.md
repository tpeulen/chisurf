# emtk port report - `img_pixel_nb` (upgrade, audit-all row 75, imaging pixel family)

Agent: claude, 2026-10-02, per `UPGRADE_BRIEF.md`; board entry `T-20261002-IMGPIX`. Type B: the analysis is the Qt tool's Qt-free view model, unchanged; `gui/model.py` adds the emtk side.
The stream's hand-drawn app (`pre-upgrade/app.py.txt` and the other files there) is replaced by a spec form on the shared shell. Verdict: **accept**; open items in section 9.

Commits: `b53f525a6` Qt baseline and the earlier stream's state, `5184007fb` app and tests, then the shared-shell / evidence commit (this report, screenshots, docs, log).

## 1. Checklist (Qt -> emtk -> test)
| Qt control | emtk | test |
|---|---|---|
| Toolbar Run / Add N&B to HDF5 / ndX / Next, Load demo, Calibrate analog | same buttons (+ `Save container`, `Cancel`) | shared checks, `test_load_demo_runs_the_demo_...`, `test_calibrate_analog_...`, `test_the_load_demo_failure_is_reported` |
| TTTR file, drops | typed / `Browse` / `Database` / drop | shared file checks |
| Stack corrections (Subtract, Add back, Box px, Box frames, Background, Detrend), Detector (Dead time, Pixel dwell, Gain S, Offset, Read variance), Estimator (Shape factor, Moment smoothing, Radius, Median) | the same folding panels and fields with the Qt ranges | `test_every_setting_gives_what_the_qt_tool_gives...` (7 sets), `test_typed_numbers_...`, `test_a_choice_of_the_estimator_panel_...`, `test_the_stack_correction_and_detector_panels_...` |
| Plane x / y, Bins, Log counts, Gate regions list, Clear gates | same + shared region list, drag handles | `test_the_plane_axes_...`, `test_bins_and_the_log_scale_...`, `test_a_gate_on_the_plane_...`, `test_gate_handles_are_dragged_...`, `test_region_list_actions_...`, `test_gates_survive_...` |
| Cross with | `Cross with` list; the cross maps are built on the worker | `test_cross_nb_is_built_on_the_worker_...` |
| ten map tabs | the same ten tabs + a View list | `test_every_tab_...`, colormap / wheel / movie tests |
Deliberate: viewer chrome and region-editor table chrome (`deliberate.json`).

## 2. Numeric parity
On the monomer / dimer demo: B, N, epsilon, n equal the moments of the simulated counts (rel 1e-9), epsilon / n medians sit at the simulated 0.5 / 1.0 and 6 / 3 (10 / 15 %), and every setting set gives the live Qt model's maps exactly.

## 4. Docs
`docs/guides/67_number_and_brightness.md` (button names without emoji, gate steps, figures `nb_brightness_map.png` and `nb_parameter_plane.png` regenerated from the emtk app on the demo), `gui/help.md`, `gui/guide.json` (8 steps, 1 awaiting: Load demo).

## 3. Tests and evidence
`python -m pytest chisurf/plugins/microscopy/img_pixel_nb/test` -> 80 passed, 1 strict xfail (picker Open selected) in 59 s. Hermetic: temporary `CHISURF_SETTINGS_DIR` / `MMFDB_*` / HOME, seeded photon streams, no network, and a last test asserts the real
`~/.chisurf` is byte-for-byte unchanged. `compare` exit 0 (`compare.json`: lost [], stale_explanations [], untooltipped []), qt-free true. Layout asserted at 1200x800 and 800x600 (no overlapping text, controls inside,
image / plot area at least a quarter of the window, settings beside it).
Deliberate breakage, each restored and green after: Calibrate analog enabled without a result -> 1 failed; the written HDF5 not remembered -> 1 failed.

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
