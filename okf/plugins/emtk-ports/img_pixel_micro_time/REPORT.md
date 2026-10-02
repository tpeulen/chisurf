# emtk port report - `img_pixel_micro_time` (upgrade, audit-all row 64, imaging pixel family)

Agent: claude, 2026-10-02, per `UPGRADE_BRIEF.md`; board entry `T-20261002-IMGPIX`. Type B: the analysis is the Qt tool's Qt-free view model, unchanged; `gui/model.py` adds the emtk side.
The stream's hand-drawn app (`pre-upgrade/app.py.txt` and the other files there) is replaced by a spec form on the shared shell. Verdict: **accept**; open items in section 9.

Commits: `a1f71e7d3` Qt baseline and the earlier stream's state, `3035bb06b` app and tests, then the shared-shell / evidence commit (this report, screenshots, docs, log).

## 1. Checklist (Qt -> emtk -> test)
| Qt control | emtk | test |
|---|---|---|
| Toolbar Run / Add mean micro-time to HDF5 / ndX / Next | `Run`, `Add mean micro-time to HDF5`, `ndX`, `Next` (greyed outside the pipeline), `Save container`, `Cancel` | `test_run_without_a_file...`, `test_hdf5_...`, `test_ndx_...`, `test_next_...`, `test_cancel_...`, `test_the_container_...` |
| TTTR file + `...`, drops | `TTTR file` typed / `Browse` / `Database` / drop | `test_a_typed_path_*`, `test_browse_*`, `test_the_database_*`, `test_a_drop_*`, `test_the_qt_host_*` |
| Min. photons | `Min. photons` spin field | `test_min_photons_discriminates_pixels_and_needs_a_new_run` |
| channel combo in each map | `Detector window` + the Detectors tab (shared editor) | `test_the_detector_window_list_...`, `test_a_micro_time_range_selects_...`, `test_the_detectors_window_...` |
| Intensity / Mean micro-time (ns) / movie tabs, colormap, levels, play / loop / stop / fps | same tabs and controls | `test_every_tab_...`, `test_the_colormap_list_...` x3, `test_the_wheel_zooms_...` x3, `test_the_movie_plays_...`, `test_the_movie_has_one_...` |
Deliberate (`deliberate.json`): the pyqtgraph viewer's ROI / Menu / normalisation / extra colormaps. Gained: Cancel, Save container, Help / Guide, Detectors tab.

## 2. Numeric parity
Intensity equals the simulated photon counts and the Qt model; the mean micro-time of the two halves equals the expectation for 1 ns / 3 ns decays with the 0.64 ns offset and the clipped last bin (1.62 / 3.38 ns, 4 %), equals the live Qt model (clipped at zero) and an independent tttrlib CLSM image; the Qt capture numbers (`qt_values.json`) agree; the HDF5 columns round-trip.

## 4. Docs
`docs/guides/24_scan_images.md` (section "Mean micro-time, phasor and pixel-wise MLE", figure `figures/24_micro_time_tool.png` regenerated from the emtk app), `gui/help.md`, `gui/guide.json` (7 steps, 3 awaiting).

## 3. Tests and evidence
`python -m pytest chisurf/plugins/microscopy/img_pixel_micro_time/test` -> 53 passed, 1 strict xfail (the dataset picker's Open selected, emtk gap) in 46 s. Hermetic: temporary `CHISURF_SETTINGS_DIR` / `MMFDB_*` / HOME, seeded photon streams, no network, and a last test asserts the real
`~/.chisurf` is byte-for-byte unchanged. `compare` exit 0 (`compare.json`: lost [], stale_explanations [], untooltipped []), qt-free true. Layout asserted at 1200x800 and 800x600 (no overlapping text, controls inside,
image / plot area at least a quarter of the window, settings beside it).
Deliberate breakage, each restored and green after: the written column holding the intensity -> 3 failed; the up-to-date message replaced -> 1 failed.

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
