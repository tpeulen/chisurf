# emtk port report - `img_pixel_phasor` (upgrade, audit-all row 65, imaging pixel family)

Agent: claude, 2026-10-02, per `UPGRADE_BRIEF.md`; board entry `T-20261002-IMGPIX`. Type B: the analysis is the Qt tool's Qt-free view model, unchanged; `gui/model.py` adds the emtk side.
The stream's hand-drawn app (`pre-upgrade/app.py.txt` and the other files there) is replaced by a spec form on the shared shell. Verdict: **accept**; open items in section 9.

Commits: `9e74b4daf` Qt baseline and the earlier stream's state, `65abe4ef5` app and tests, then the shared-shell / evidence commit (this report, screenshots, docs, log).

## 0. Defect found and fixed
A typed **Frequency (MHz)** was passed to tttrlib as typed; tttrlib takes cycles per micro-time channel, so every pixel became (g, s) = (1, 0). `PhasorImgViewModel._frequency_per_channel` converts MHz with the file's micro-time resolution (-1 still reads the header); a test pins 40 MHz == header value and the photon-weighted g, s of each half to the analytic expectation for 1 ns and 3 ns decays. The seeded stream now carries a 25 ns laser period like a real file (before it did not, which first made the numbers look wrong).

## 1. Checklist (Qt -> emtk -> test)
| Qt control | emtk | test |
|---|---|---|
| Toolbar Run / Add phasor to HDF5 / ndX / Next | same buttons + `Save container`, `Cancel` | shared checks (run, hdf5, container, ndX, next, cancel) |
| TTTR file, drops | typed / `Browse` / `Database` / drop | shared file checks |
| Min photons, Frequency (MHz, -1=auto) | spin fields with the Qt ranges | `test_the_phasor_frequency_and_min_photons_fields_need_a_new_run`, `test_an_explicit_frequency_in_mhz_...` |
| channel combos, IRF per detector (IRF & BG step) | `Detector window`, Detectors tab, `IRF reference` panel (window, file, `Browse IRF`, `Clear IRF`) | `test_the_irf_reference_...`, `test_the_detectors_window_...` |
| Phasor cursors region list (add rectangle / ellipse / polygon, combine, invert, rename, geometry, duplicate, remove, save, load) | `Analysis regions` (shared `RegionControls`), `Clear all`, drag handles on the plot | `test_an_ellipse_cursor_...` (handle dragged), `test_rectangle_and_polygon_...`, `test_invert_and_the_enabled_box_...`, `test_duplicate_remove_and_the_combine_rule`, `test_a_cursor_handle_dragged_...`, `test_cursors_are_saved_and_loaded_...`, `test_the_cursors_are_part_of_the_saved_settings` |
| Intensity / Selected / g / s / g movie / s movie / Frames / Phasor plot / Phasor plot movie | the same nine tabs + a View list | `test_every_tab_...`, colormap / wheel / movie tests |
Deliberate: viewer chrome (`deliberate.json`); the Qt region editor's table chrome is the shared list's own (`extra_deliberate.json`); the phasor plot movie is drawn as an image of the density stack (axes in bins).

## 2. Numeric parity
g, s equal the live Qt model and a direct tttrlib call; each half's weighted mean phasor equals the analytic expectation (abs 0.02); cursor selection equals the geometric mask; histogram counts every valid pixel once.

## 4. Docs
`docs/guides/24_scan_images.md` (figure `figures/24_phasor_tool.png` from the emtk app with a cursor on the 1 ns cluster), `gui/help.md`, `gui/guide.json` (7 steps, 3 awaiting).

## 3. Tests and evidence
`python -m pytest chisurf/plugins/microscopy/img_pixel_phasor/test` -> 129 passed (the new parity file plus the plugin's analysis, cursor, service and CLI tests), 2 strict xfails (picker Open selected; an emptied text field on Enter) in 59 s. Hermetic: temporary `CHISURF_SETTINGS_DIR` / `MMFDB_*` / HOME, seeded photon streams, no network, and a last test asserts the real
`~/.chisurf` is byte-for-byte unchanged. `compare` exit 0 (`compare.json`: lost [], stale_explanations [], untooltipped []), qt-free true. Layout asserted at 1200x800 and 800x600 (no overlapping text, controls inside,
image / plot area at least a quarter of the window, settings beside it).
Deliberate breakage, each restored and green after: the MHz conversion removed (the original defect) -> 5 failed; the IRF reference never stored -> 3 failed.

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
