# emtk port report - `img_tracking` (port-incomplete upgrade, audit-all row 83, imaging family 1 of 4)

Agent: claude (Sonnet), 2026-10-02, per `UPGRADE_BRIEF.md`; board entry `T-20261002-IMGFAM`. Type **B** (the Qt tool is an AutoForm `ImgTrackingTool`; its `gui/view_model.py` is already Qt-free and is reused, `gui/model.py` adds the
emtk side). The earlier stream's app was a 70-line page (a path field, a Simulate checkbox, a Track button, two float fields, a report, two plots): `before_emtk_populated_1200x800.png` shows what it drew. Verdict: **accept**; no numerical difference from the Qt tool. A quirk of the Qt tool found on the way (section 5 note): its True D box shows 4 decimals and so rounds its declared minimum 1e-06 to 0.0000 (it accepts a simulation with no motion); the emtk field now keeps typed numbers to the shown decimals, as the Qt box does, and agrees (tested against the live Qt box).

Commits: `d04659d8b` Qt baseline and the stream's emtk state, `d3f267ea5` emtk app at parity (code, tests, the shared `imaging_emtk` helper), then the evidence commit (this report, screenshots, docs, log).

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `img_tracking` / `chisurf/plugins/microscopy/img_tracking` |
| Port type | B (Qt AutoForm tool, Qt-free view model reused) |
| Shared code | `chisurf/plugins/microscopy/imaging_emtk/` (new, Qt-free, not `chisurf/emtk/*`): window shell `app_base.py`, model mixin `model_base.py`, views `views.py`, test driver `testing.py`; shared by `img_drift`, `img_flow`, `img_frc` |
| Entry point | `entrypoints.emtk` -> `chisurf.plugins.microscopy.img_tracking.gui.app:make_app` (was `...img_tracking.app:make_app`, the stream's module; kept in `pre-upgrade/`) |

## 1. State at start

`git status --short chisurf/plugins/microscopy/img_tracking`:

```
 M chisurf/plugins/microscopy/img_tracking/manifest.json
?? chisurf/plugins/microscopy/img_tracking/app.py
?? chisurf/plugins/microscopy/img_tracking/strings.py
?? chisurf/plugins/microscopy/img_tracking/test/test_native.py
```

The stream's files are the intended starting point: copied to `pre-upgrade/` (`app.py.txt`, `strings.py.txt`, `test_native.py.txt`, `manifest.json.diff`) and committed with the Qt baseline. Files edited that I did not write: `manifest.json` (entrypoint path), `test/test_native.py`
(import path; its two tests are unchanged). `app.py` and `strings.py` (the stream's thin app and five-label translation catalogue) are removed: the Qt tool had no translations, so there is nothing to keep parity with.

## 2. What the Qt tool offered - control checklist

Qt baseline: `before.png`, `before.json` (66 controls), mine `before_populated_{empty_track_pressed,simulate_panel,simulated,fit_alpha,file_loaded,file_tracked,missing_file,corrupt_file}.png`, `before_tab_{Report,Movie,Trajectories,MSD,Track_lengths,Tracks}.png`,
`qt_values.json` (every number the Qt window computed, from `scripts/capture_qt_populated.py`), `qt_exported.csv` (what Export CSV wrote).

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Toolbar: Track (background run, status counts frames, "6 tracks, D = ..." at the end) | spec `button_row` `track`, `SnapshotJob` worker, status line under Help / Guide | yes |
| 2 | Toolbar: Open (file dialog, Qt filter) | `open_file` -> `emtk.file_dialog.FileDialog` | yes |
| 3 | Toolbar: Export CSV ("Run the tracker first." without a result; default name `<stem>.tracks.csv`) | `request_export` -> FileDialog (save), same default name and message | yes |
| 4 | Toolbar: Guide, `?` | `Help`, `Guide` buttons (help window, guided tour) | yes (`?` -> Help) |
| 5 | Image stack field + "..." (typed path, commit on leaving) | `value` `filename` (commit on Enter or click-away) + the Open button | yes |
| 6 | Channel 0-63, Max frames 0-1e6 (spin boxes) | spin `value` fields, same limits | yes |
| 7 | "Simulate instead" fold: Simulate toggle, True D, Particles, Frames, Field, Spot amplitude, Background, Seed | folding panel, toggle, 7 spin fields with the Qt ranges and decimals | yes |
| 8 | 1. Detect: Detector (wavelet / quantile), Threshold, Min area, Min separation | `choice` + 3 spin fields | yes |
| 9 | 2. Link: Max step, Max gap | 2 spin fields | yes |
| 10 | 3. Transport: Pixel size, Frame interval, Min track length, Fit anomalous exponent, Bootstrap resamples, Tracks drawn | 5 spin fields + toggle | yes |
| 11 | Report (info) | `info` section `report_text` | yes |
| 12 | Views tabs: Movie, Trajectories, MSD, Track lengths, Tracks | five dock tabs | yes |
| 13 | Movie: play, loop, stop, fps 1-120, frame slider, colormap, level histogram, detection markers on the shown frame | Play / Pause, Loop, Stop, spin `fps`, `Z slice` slider, colormap combo, gamma, automatic levels / display min / max, Reset view, markers | yes (3 colormaps lost, section 5) |
| 14 | Trajectories plot (image coordinates, y inverted, per-track colours, cap `Tracks drawn`) | `series_plot`, inverted y, same colours | yes |
| 15 | MSD plot (log-log, measured points, fit line, legend) | `series_plot` | yes |
| 16 | Track lengths plot | `series_plot` | yes |
| 17 | Tracks table (#, Points, Frames, Net, tooltips) | spec `data_table` (numeric cells, header sorts by value, `%.2f` for Net as the Qt text) | yes |
| 18 | Status bar messages (run reason, counts, "Wrote ...") | status line | yes |
| 19 | File drop on the tool (`on_paths_dropped`) | `files_dropped` hook | yes |
| 20 | Window geometry remembered | `export_settings` / `restore_settings` (parameters, folder) | yes |
| 21 | Tooltips on every control | spec `description`s (sections, columns, buttons), measured | yes |

## 3. Files

| File | Change | Purpose |
|---|---|---|
| `gui/model.py` | new | `TrackingModel(EmtkModelMixin, ImgTrackingViewModel)`: the button actions, status line, dialogs, numeric table rows |
| `gui/tracking_emtk.view.json` | new | the settings form, report, five views (descriptions generated from the Qt spec's text) |
| `gui/app.py` | new | `ImgTrackingApp(ImagingToolApp)`, `make_app(coordinator=None)` (the imaging hub passes `coordinator`) |
| `gui/guide.json`, `gui/help.md` | changed | emtk wording (Z slice, Simulate instead header, Track); 9 steps, 5 `await` |
| `test/test_emtk_img_tracking_parity.py` | new | 93 tests, 3 of them strict xfails (section 6) |
| `test/test_native.py` | import path | |
| `manifest.json` | changed | `entrypoints.emtk` -> `gui.app:make_app` |
| `../imaging_emtk/*` | new, shared | shell, model mixin, views (series plot, image / movie panel, quiver), test driver |

Qt files untouched: `gui/tool.py`, `gui/view_model.py`, `gui/tracking.view.json`, `core.py`, `backend/`, `cli/`.

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity compare img_tracking --out okf/plugins/emtk-ports/img_tracking; echo exit=$?
{ "lost": [], "untooltipped": [] }
qt-free: True
exit=0          (explained 17, stale_explanations [], before 66 controls, after 128)
```

`after.json` is the populated app with every tab visited and the colormap and detector lists opened (`scripts/capture_emtk_after.py`: the stock `after` draws the empty app, where the views and the movie controls are not on screen;
its output is kept as `after_empty.json`, `after_1200x800.png`, `after_800x600.png`). `after.json` -> `controls_without_tooltip` is `[]`; `qt_free` is `{"ok": true, "output": "QT-FREE OK"}`.

## 5. Deliberate differences

| Lost / changed item | Why | What replaces it |
|---|---|---|
| `?` | Qt toolbar glyph | the `Help` button |
| `cividis`, `plasma`, `turbo` | colormap entries of the pyqtgraph dock; `chisurf/emtk/image_canvas.py` (shared, not mine) offers magma, inferno, viridis, gray | blocked: needs the list extended there (section 10) |
| `blur`, `divide`, `subtract`, `operation`, `mean`, `off`, `timerange`, `roi`, `menu`, `frame`, `t`, `x`, `y` | internals of pyqtgraph's ImageView, present in the Qt inventory but with no visible control in `before_tab_Movie.png` | gamma and display levels on the image canvas; axis titles `x [px]`, `y [px]` |
| status messages | Qt cleared them after 6-12 s | the status line holds the last message until the next action |
| Track while a run is in flight | the Qt action stayed live and started a second run | the action and the form are greyed while the worker runs (the worker's result replaces the model's state, so an edit made during the run would be lost) |
| table cells | Qt held strings (a click on "Points" sorted text: 10 before 2) | numbers; a header click sorts by value |
| Qt movie dock after a failed load | kept the previous run's frame and markers (`before_populated_corrupt_file.png`) | the movie view says "Press Track ..." again |

## 6. Tests

```
$ python -m pytest chisurf/plugins/microscopy/img_tracking -q -p no:cacheprovider
112 passed, 3 xfailed in 28.54s          (20 earlier core / RPC / CLI / view-model tests + 2 native tests + 90 passed and 3 xfailed of the 93 new parity tests)
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider
13 passed in 22.82s
$ python -m pytest test/test_plugin_help_guide_seam.py -q -k "img_tracking or drawn or discoverable"   -> 5 passed
$ python -m pytest test/test_prd_mentions.py -q                                                       -> 2 passed
```

| Required test | Test | Asserts |
|---|---|---|
| 1 reference | `test_the_track_button_gives_the_numbers_the_qt_window_showed`, `..._fit_alpha_checkbox_...`, `test_the_core_functions_give_the_same_answer_without_the_view_model`, `test_a_tiff_gives_the_same_tracks_as_the_simulation`, `test_the_qt_tool_and_the_emtk_app_agree_on_every_result[5 scenarios]`, `test_typed_extremes_are_clamped_to_the_range_the_qt_spin_box_enforced[19 fields]` | D, error, alpha, MSD, track table, detections, report text, status line equal to the pinned Qt numbers (`qt_values.json`) AND to the live Qt tool (report text, table cells read from the Qt `QTableWidget`, series) AND to a written-out `core.analyse` run; the Qt spin boxes and the emtk fields clamp identically |
| 2 actions, errors | `test_track_with_nothing_loaded_...`, `..._missing_file_...`, `test_a_corrupt_file_...`, `test_the_track_button_is_greyed_...`, `test_export_without_a_result_...`, `test_export_to_an_unwritable_place_...`, `test_a_worker_that_raises_...`, the dialog tests | every action and its failure path |
| 3 spec | `test_every_spec_key_exists_on_the_model`, `test_every_qt_setting_is_in_the_emtk_spec_with_the_same_range` | attr / call / action / source / column keys exist; label, min, max, decimals, description equal the Qt spec |
| 4 draws | `test_the_window_draws_empty_and_populated_at_both_sizes`, `test_every_view_is_drawn_after_a_run` | 1200x800 and 800x600, every tab |
| 5 workflow | `tracked()` in every test: press Track with the pointer, wait for the worker, read the result | |
| 6, 7, 8 | `test_port_is_qt_free`, `test_every_control_has_a_tooltip`, `test_the_populated_window_has_a_tooltip_on_every_control_too`, `test_settings_round_trip_and_invalid_values_are_ignored` | |

Deliberate breakage (restored; 90 passed + 3 xfailed afterwards):

| What I broke | Result |
|---|---|
| `views.py` playback: wrap at the end (`z %= n`) replaced by a clamp | `test_playback_wraps_when_loop_is_on_and_stops_at_the_last_frame_when_off` failed |
| `model.py`: the table's `net` column filled with `length` | 6 failed: `test_the_tracks_table_shows_what_the_qt_table_showed` and the five `test_the_qt_tool_and_the_emtk_app_agree_on_every_result[...]` (7 failed with the first) |

The Qt tool shares `gui/view_model.py` with the emtk app, so a model fault would pass a Qt-vs-emtk comparison by itself (the lesson of the earlier ports): the pinned numbers of `qt_values.json` (captured before the port) and the `core.analyse` run are the independent references.

Pre-existing failures I did not cause: none in this folder.

### 6a. Real-input coverage (control -> test)

Every test below presses / releases the pointer at the rectangle the control was drawn in (or at its drawn text), types with key events, drags, wheels, or drops through the `ControlSurface` hook; it reads the visible outcome. Nothing calls a model method to "click".
The painter measures text like the screenshot painter (`imaging_emtk/testing.py`).

| Control | Test |
|---|---|
| Track (also greyed while a run is in flight) | `test_the_track_button_gives_...`, `test_track_with_nothing_loaded_...`, `..._missing_file_...`, `..._corrupt_file_...`, `test_the_track_button_is_greyed_...` |
| Open: dialog, a clicked file, Cancel | `test_open_button_opens_the_file_dialog_...`, `test_open_dialog_cancel_changes_nothing` |
| Export CSV: no result, default name + Save (CSV bytes equal to the Qt file), typed name + extension, Cancel, unwritable | `test_export_without_a_result_says_so`, `test_export_csv_writes_the_file_the_qt_tool_wrote`, `test_export_csv_to_a_typed_name_...`, `test_export_to_an_unwritable_place_...` |
| Image stack: typed + Enter, typed and clicked away | `test_a_path_typed_into_the_field_is_taken_on_enter`, `test_a_path_typed_but_not_confirmed_is_not_taken` |
| File drop (hook, empty drop, while busy, the Qt host's `dropEvent`) | `test_dropping_a_file_on_the_window_loads_it`, `test_dropping_while_a_run_is_in_flight_is_refused`, `test_the_qt_host_delivers_a_dropped_file_to_the_app` |
| 12 spin fields: arrows up / down, limits | `test_each_arrow_steps_its_field_by_the_qt_step[12]` |
| 19 fields: typed 1e9 / -5 + Enter against the live Qt box | `test_typed_extremes_are_clamped_...[19]`, `test_the_simulation_fields_are_typed_and_clamped` |
| Simulate toggle, the 5 folding headers | `test_simulate_checkbox_and_the_folding_panels_are_clicked` |
| Detector combo: open, pick each, Escape | `test_the_detector_choice_lists_the_two_methods_...`, `test_escape_closes_the_open_detector_list_...` |
| Fit anomalous exponent | `test_the_fit_alpha_checkbox_gives_the_qt_numbers_...` |
| Settings form greyed while running | `test_the_settings_form_is_greyed_while_a_run_is_in_flight` |
| Report | `test_every_view_is_drawn_after_a_run`, the numbers tests (report text equal to Qt's) |
| Movie: Play, Pause, Stop, Loop on / off, fps typed and arrows, Z slice click and drag, colormap combo, gamma slider, Automatic levels, Reset view after a pan, markers per frame | `test_play_advances_...`, `test_playback_wraps_...`, `test_the_fps_field_...`, `test_the_fps_arrows_...`, `test_the_z_slice_slider_scrubs_the_movie`, `test_the_colormap_combo_gamma_and_levels_are_operated`, `test_reset_view_restores_the_image_after_a_pan`, `test_the_movie_markers_follow_the_frame` |
| Trajectories / MSD: drag pan; wheel zoom | `test_a_drag_pans_the_trajectory_plot`, `test_a_drag_pans_the_msd_plot`; wheel: `test_the_wheel_zooms_the_trajectory_plot` (xfail, emtk gap 2) |
| Track lengths | `test_every_view_is_drawn_after_a_run`, `test_every_view_says_what_to_do_...` |
| Tracks table: header sort ascending / descending, row click | `test_the_tracks_table_header_sorts_by_value_...` |
| Tabs | every view test clicks the tab's drawn text |
| Wheel over a spin field; the settings window scroll | `test_the_wheel_over_a_spin_field_steps_it` (xfail, gap 2), `test_the_wheel_scrolls_the_settings_window_...` |
| Help, its Start Guided Tour / Close, Guide, Close Tour, the tour walked to the end with each highlighted control operated, every guide target drawn | `test_help_button_...`, `test_guide_button_starts_...`, `test_the_tour_is_walked_to_the_end_...`, `test_every_guide_target_is_a_drawn_control_or_window`; overlap case: xfail gap 1 |
| Settings, hub | `test_settings_round_trip_...`, `test_the_imaging_hub_contract` |

## 7. Screenshots I looked at (full size)

`after_populated_{Movie,Trajectories,MSD,Track_lengths,Tracks}_1200x800.png`, `after_populated_{Movie,MSD}_800x600.png`, `after_populated_Movie_colormap_open_1200x800.png`, `after_populated_detector_list_open_1200x800.png`, `after_1200x800.png`, `after_800x600.png` (empty),
`docs_tracking_workspace.png`, `docs_tracking_trajectories.png` (the guide's own run: 8 tracks, D = 0.5038 +- 0.1, the numbers the guide prints). Numbers equal the Qt screenshots: 6 tracks, D = 0.5581 +- 0.098, 240 detections, the track table.
Fixed while reading them: the settings column was 37 % wide and clipped "Fit anomalous exponent" at 800 px (now 40 %); the Movie panel's frame rectangle (used by the guide) was the dummy item's 17 px strip, now the plot's. Nothing is clipped at 1200x800 or 800x600; the image plot is small at 800x600 because the
shared canvas stacks its controls (Z slice, colormap, gamma, levels, Reset view) above it.

## 8. Workflow

Open the "Simulate instead" panel, tick Simulate (or Open / drop a TIFF stack or photon stream), set the detector and Max step, press Track: the status line counts the frames, then reads "6 tracks, D = 0.5581 +- 0.098"; the report, the movie with the detections of the shown frame, the trajectories, the MSD with its fit, the
track-length histogram and the table follow. Export CSV writes `track,frame,y,x,intensity` (byte-equal to the Qt file). No data file is needed: the movie is simulated (seed 1, known D = 0.5) or a TIFF written by the tests from the same simulation.

## 9. Persistence, guide, help, docs

`export_settings`: the 22 analysis parameters and the last folder (never the file or the result); the Qt tool remembered the window geometry only. Guide: 9 steps, 5 `await` (Simulate instead header, Simulate toggle, Track outcome...), targets `attr` names of the spec (so the Qt tool still resolves them) and
`name`/`title` for the headers, views and the outcome; the tab a step points at is brought forward. Help: `help.md` (links checked by the seam test). Docs: `docs/guides/50_particle_tracking.md` (the two figures replaced by the emtk screenshots of the guide's own run, the "frame slider" wording).
Docs gap: none.

## 10. Blocked / open

emtk gaps found by the click tests (none edited; repros use only emtk):

1. A tour card drawn over a control of a window cannot be pressed: the control underneath claims the pointer first (`chisurf/emtk/help_guide.py` draws the card on the bare canvas, `hovered_id` is first-come). `test_the_tour_card_buttons_work_when_the_card_lies_over_a_form_field` (strict xfail).
   Repro: `scripts/gap_tour_overlap.py` (5 lines: open the Guide, click Close Tour; the tour stays active and the field "Tracks drawn" under the button takes the press). Works at 1200x800 where the card is clear of the form.
2. The wheel does not reach a spin field or an implot inside a `DockManager` window (it does in a plain `im.begin` window; the window's own scrolling works). Repro: `scripts/gap_wheel_dock.py` (emtk only): a spin value drawn by `draw_sections` in a `DockManager` window, `app.wheel(x, y, 1)` -> value unchanged (5); the same section in `im.begin("W", (0,0,400,200))` -> 6. `test_the_wheel_over_a_spin_field_steps_it`, `test_the_wheel_zooms_the_trajectory_plot` (strict xfails).
3. `chisurf/emtk/image_canvas.py` offers 4 colormaps (pyqtgraph's dock had 7) and its plot tooltip reads "Click a bead/spot to fit it. Drag to pan, scroll to zoom; blue handles edit analysis regions...", which is wrong for a tool that picks nothing. Shared file, not edited.

Defect found in my first draft of the shared shell and fixed by the click tests: the image panel was reset every frame (`id(array)` compared with `is not`), so Play stopped after one frame.

## 11. Self-check against the Definition of Done

D1 yes (4). D2 yes (2, 5). D3 yes (4). D4 yes (7). D5 yes (6, 8). D6 yes (9). D7 yes (9). D8 yes (9). D9 yes (6). D10: report, evidence, board.
