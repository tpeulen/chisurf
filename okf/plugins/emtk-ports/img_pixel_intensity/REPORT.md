# emtk port report - `img_pixel_intensity` (upgrade, audit-all row 60, imaging pixel family 1 of 6)

Agent: claude, 2026-10-02, per `UPGRADE_BRIEF.md`; board entry `T-20261002-IMGPIX`. Type B: the analysis is the Qt-free `IntensityViewModel` (unchanged, shared with the Qt tool); `gui/model.py` adds the emtk side.
The stream's hand-drawn app (`pre-upgrade/app.py.txt`) is replaced by a spec form on the new shared pixel shell. Verdict: **accept** for this plugin; family-wide open items in section 9.

Commits: `19f9ff5a7` baseline + stream state, `32969da4b` app + shared shell + tests, `776ad275e` layout test, then the evidence commit (this report, screenshots, docs).

## 1. Defects found in the stream's app (`before_emtk_populated_1200x800.png`)
Nine unlabelled buttons stacked in one column, detector windows as plain text with no way to edit them, no status line or Cancel, the file as bare text, HDF5 / Run / ndX written from hand-drawn code with an invented "PTO" name.
Fixed: a spec form (labelled file field, wrapped button rows, Detector window choice), status line, Cancel (greyed while idle), the shared detector editor as a "Detectors" tab seeded with the windows actually computed (the editor's own defaults, green/red/yellow, would have shown windows that are not used).

## 2. Control checklist (Qt -> emtk)
| Qt control | emtk | test |
|---|---|---|
| Toolbar Run (background; "No file selected."; skip when nothing changed) | `Run` (greyed without a file, while a worker runs); status "Nothing changed ..." | `test_run_without_a_file_does_nothing_...`, `test_the_maps_are_the_photon_counts...` |
| Toolbar Create imaging HDF5 (pipeline file or asks) | `Create imaging HDF5` + save dialog | `test_hdf5_is_greyed_...`, `..._dialog_cancel_...`, `..._unwritable_...` |
| ndX | `ndX`, `Back to the maps` | `test_ndx_opens_over_the_maps_and_back_returns` |
| Next | `Next` (greyed outside the pipeline) | `test_next_is_greyed_outside_the_pipeline_...` |
| TTTR file field + `...` | `TTTR file` typed + Enter / click away, `Browse`, `Database`, drop | `test_a_typed_path_...` x2, `test_browse_*`, `test_the_database_*`, `test_a_drop_*`, `test_the_qt_host_*` |
| channel combo of each map | `Detector window` choice | `test_the_detector_window_list_switches_...` |
| colormap combo, levels, histogram | canvas colormap list, gamma, levels, Reset view | `test_the_colormap_list_...` x3 |
| Frames movie: play, loop, stop, fps | same controls, speed 1-120 | `test_the_movie_plays_loops_stops_...` |
| image wheel / drag | wheel zoom, drag pan | `test_the_wheel_zooms_and_a_drag_pans_the_image` x3 |
| Intensity / Count rate / Frames tabs | same three tabs | `test_every_tab_draws_...` |
| closing flushes HDF5 + container | `close()` flushes | `test_closing_a_computed_session_flushes_...` |
Gained: Cancel, Save container button, Help / Guide, the Detectors tab. Deliberate losses (`deliberate.json`): the pyqtgraph ImageView's ROI/Menu/Operation/time-range/extra colormaps (cividis, plasma, turbo) - display extras of the Qt viewer; the shared ImageCanvas offers four colormaps.

## 3. Numeric parity
Intensity map equals the photon counts written into the stream, the live Qt view model, an independent tttrlib CLSM image and the real Leica SP5 scan; count rate equals the Qt rate and the background-subtracted, zero-clipped rate; polarised windows split parallel/perpendicular exactly; HDF5 columns round-trip.

## 4. Tests
`python -m pytest chisurf/plugins/microscopy/img_pixel_intensity/test` -> 54 passed, 1 strict xfail (dataset picker Open selected never fires: emtk gap, see img_drift REPORT). Hermetic: temp settings/MMFDB/HOME, and a last test asserts the real `~/.chisurf` is unchanged. Layout at 1200x800 and 800x600 (texts apart, controls inside, image area >= 30 % of the window, settings beside the image). Deliberate breakage twice, restored: (1) status text + pipeline file not remembered -> 2 failed; (2) count off by one -> 5 failed. `compare` exit 0 (lost [], stale [], untooltipped []), qt-free true.

## 5. Real-input coverage
Every control in section 2 is pressed/typed/dragged/wheeled through `Driver` (pointer press and release at drawn rectangles, Enter, host drops incl. the Qt `ControlHost`); the guided tour is walked to the end operating Browse, Run and Create imaging HDF5 by pointer.

## 6. Reuse
Shared: `imaging_emtk` shell (`app_base`, `views.ImagePanel`), new `pixel_model` / `pixel_app` / `pixel_checks` / `pixel_testing` (one helper for the whole family, not six copies), the detector editor `chisurf/emtk/channel_definition.py` (embedded, not edited), `DatasetPicker`, `FileDialog`, `emtk_layout.layout_spec`, help/tour, `data` generators. Duplicates removed: `native_model.py`, the hand-drawn file/ndX/dialog code.

## 7. Docs
`docs/guides/24_scan_images.md` (new section "The Intensity tool" with steps), figure `docs/guides/figures/24_intensity_tool.png` regenerated from the emtk app, `gui/help.md`, `gui/guide.json` (8 steps, 3 awaiting: file, Run, HDF5). Plugin reference generation (`docs-plugins`) not run here.

## 8. Layout
Before: stacked buttons, text list of windows. After screenshots read at full size: `after_populated_{Intensity,Count_rate_kHz,Frames_movie,Detectors,Settings}_{1200x800,800x600}.png`, help, guide, hdf5 dialog. No clipping or overlap; image gets the right-hand area.

## 9. Gaps in shared code (not edited; repros)
1. `elide: "start"` in `input_text` clips the last characters of a long path (".ptu" cut): a spec value with a path longer than its field.
2. The embedded ChannelDefinitionWidget is taller than 800x600 and does not scroll: "Optical Setup..." is cut off.
3. It draws "Calc G"/"Delete" row buttons over their cells (same string twice).
4. A tour card over an editor makes Next dead (known); the guide points at the Detector window field.
5. `ImageCanvas` stacks colormap / gamma / levels / Reset above the image (about 110 px) and offers four colormaps.
