# emtk port report - `img_drift` (port-incomplete upgrade, audit-all row 85, imaging family 2 of 4)

Agent: claude (Sonnet), 2026-10-02, per `UPGRADE_BRIEF.md`; board entry `T-20261002-IMGFAM`. Type **B** (the Qt tool is an AutoForm `ImgDriftTool`; `gui/view_model.py` is already Qt-free and is reused, `gui/model.py` adds the emtk side). The earlier stream's app
(`pre-upgrade/app.py.txt`, 100 lines) is replaced. Verdict: **accept**; the stream's app had **real regressions** (section 0), no numerical difference from the Qt tool.

Commits: `439a8287d` Qt baseline and the stream's emtk state, then the app commit (code, tests, the shared-shell changes below) and the evidence commit.

## 0. REGRESSIONS found in the stream's app

`scripts/capture_emtk_before.py` / `before_emtk_choices.json` (the old module run on the drifting stack):

| What the stream's app offered | Result |
|---|---|
| Reference `middle` | `Drift measurement failed: unknown reference 'middle'; expected one of ('first', 'previous', 'mean')` |
| Boundary mode `nearest` | `unknown mode 'nearest'; expected 'wrap' or 'constant'` |
| Boundary mode `reflect` | same |
| (missing) Reference `previous`, mode `constant` | not offered at all |

Also: the shift table was hand drawn and its columns drew over each other (`before_emtk_populated_1200x800.png`); after a successful load the message still said "No image loaded." (it was read before the measurement); no Before / After projections, no channel choice, no
Export dialogs (the user typed output paths); the typed path did not start the measurement the Qt tool starts on choosing a file; the Estimator's smoothing field accepted any float. All replaced by spec-drawn controls with the Qt spec's own choices.

## 1. State at start

```
 M chisurf/plugins/microscopy/img_drift/manifest.json
?? chisurf/plugins/microscopy/img_drift/app.py
?? chisurf/plugins/microscopy/img_drift/strings.py
?? chisurf/plugins/microscopy/img_drift/test/test_native.py
```

Copied to `pre-upgrade/` (`app.py.txt`, `strings.py.txt`, `test_native.py.txt`, `manifest.json.diff`) and committed with the baseline. Files edited that I did not write: `manifest.json` (entrypoint path), `test/test_native.py` (import path; its two tests unchanged). `app.py` and `strings.py` are removed (the Qt
tool had no translations). Qt baseline: `before.png`, `before.json` (48 controls), mine `before_populated_{empty_measure_pressed,tiff_default,tiff_options,photon_stream,corrupt_file,one_frame}.png`, `before_tab_{Drift_trace,Projection,Projection_photon,Shifts}.png`, `qt_values.json`, `qt_shifts.csv`.
The data: a TIFF with a known linear drift (`scripts/make_data.py`: 14 blobs, 12 frames, drift (2, -1) px per frame) and the real photon stream `test/data/clsm/PQ_Olympus_MFIS.ht3` (40 frames, 4 channels).

## 2. What the Qt tool offered - control checklist

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Toolbar Measure (background run, "Measuring drift...", status = the model's) | `button_row` `measure`, `SnapshotJob`, status line | yes |
| 2 | Toolbar Export stack ("Writing corrected stack...", "Wrote ...") | `request_export_stack` -> FileDialog (`<stem>.corrected.tif`), worker | yes |
| 3 | Toolbar Export shifts | `request_export_shifts` -> FileDialog (`<stem>.drift.csv`) | yes |
| 4 | Guide, `?` | `Guide`, `Help` | yes |
| 5 | Image: path field, Browse, Database (MMFDB picker), drop; choosing a file measures it at once | `value` `filename` (Enter / click-away), `Browse`, `Database` (DatasetPicker), `files_dropped`; the worker measures after loading | yes |
| 6 | Measure on (channel names of the file) | `choice` `channel`, options from the file | yes |
| 7 | Reference: First frame / Previous frame / Stack mean | `choice` with the Qt labels | yes |
| 8 | Apply by: Wrapping (keep all signal) / Blanking (drop what leaves) | `choice` with the Qt labels | yes |
| 9 | Estimator fold: Smoothing 0-20 (2 decimals), Sub-pixel refinement | folding panel, spin field with arrows, toggle | yes |
| 10 | Views: Drift trace (dx, dy, \|d\|, legend) | `series_plot` | yes |
| 11 | Views: Projection with Before and After docks, a colormap combo each, shared `colormap` | `image_pair`: two image canvases side by side, colormap synced through the model | yes (3 colormaps lost) |
| 12 | Views: Shifts table (Frame, dx, dy, \|d\|) | spec `data_table`, numeric cells, `%+.2f` / `%.2f` as the Qt text | yes |
| 13 | Status bar messages | status line | yes |
| 14 | File drop | `files_dropped` | yes |
| 15 | Window geometry | `export_settings` / `restore_settings` (reference, mode, smoothing, sub-pixel, colormap, folder) | yes |
| 16 | Tooltips | spec `description`s | yes |

## 3. Files

| File | Change |
|---|---|
| `gui/model.py` | new: `DriftModel(EmtkModelMixin, DriftViewModel)`: the actions, status line, dialogs, numeric table rows, channel normalisation |
| `gui/drift_emtk.view.json` | new: settings form and four windows (text and ranges taken from the Qt spec) |
| `gui/app.py` | new: `ImgDriftApp`, `make_app(coordinator=None)` |
| `gui/guide.json`, `gui/help.md` | changed: 7 steps, 2 `await` (load, Measure); the button names of the emtk window |
| `test/test_emtk_img_drift_parity.py` | new: 66 tests (4 strict xfails) |
| `../imaging_emtk/*` | shared shell: `_draw_image_pair`, a per-app `LAYOUT`, the file chooser in a titled `DialogWindow` with a close button (it filled the whole window before), the load step also released by a dialog choice |

Qt files untouched: `gui/tool.py`, `gui/view_model.py`, `gui/drift.view.json`, `core.py`, `cli/`.

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity compare img_drift --out okf/plugins/emtk-ports/img_drift; echo exit=$?
{ "lost": [], "untooltipped": [] }
qt-free: True
exit=0          (explained 16, stale_explanations [], before 48 controls, after 107)
```

`after.json` is the populated app (every tab, the colormap and the three choice lists opened; `scripts/capture_emtk_after.py`); the stock `after` draws the empty app: kept as `after_empty.json`, `after_1200x800.png`, `after_800x600.png`. `controls_without_tooltip` is `[]`, `qt_free` is `{"ok": true}`.

## 5. Deliberate differences

| Lost / changed item | Why | What replaces it |
|---|---|---|
| `?` | Qt toolbar glyph | `Help` |
| `cividis`, `plasma`, `turbo` | colormaps of the pyqtgraph docks; the shared emtk canvas offers magma, inferno, viridis, gray | blocked (section 10) |
| `blur`, `divide`, `subtract`, `operation`, `mean`, `off`, `timerange`, `roi`, `menu`, `t`, `x`, `y` | pyqtgraph ImageView internals with no visible control in `before_tab_Projection.png` | gamma and display levels; axis titles `x [px]`, `y [px]` |
| Measure with nothing loaded | the Qt action did nothing, silently | the status line says "No image loaded." |
| Export stack / shifts before a measurement | silent in Qt | "Measure the drift first." |
| Failed measurement | the Qt status bar said "Drift measurement failed" and hid the reason | the status line shows the model's own message with the reason |
| Reading the file | Qt read it on the GUI thread | worker; the form and actions are greyed meanwhile |
| Table cells | strings | numbers; a header click sorts by value |

## 6. Tests

```
$ python -m pytest chisurf/plugins/microscopy/img_drift -q -p no:cacheprovider
77 passed, 4 xfailed in 27.93s        (13 earlier core / CLI tests + 2 native + 62 passed and 4 xfailed of the 66 new)
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider      -> 13 passed
$ python -m pytest test/test_plugin_help_guide_seam.py -q -k "img_drift or drawn or discoverable" ; test/test_prd_mentions.py   -> passed
```

(The seam file also fails for other plugins' guides, as the board notes; none is mine.)

| Required test | Test | Asserts |
|---|---|---|
| 1 reference | `test_choosing_a_drifting_stack_measures_exactly_the_injected_drift_and_the_qt_numbers`, `test_the_options_give_the_numbers_the_qt_window_showed`, `test_the_real_photon_stream_...`, `test_the_qt_tool_and_the_emtk_app_agree_on_every_result[6 scenarios]`, `..._on_the_photon_stream`, `test_the_shift_table_shows_what_the_qt_table_showed` | shifts equal the pinned Qt numbers, the live Qt tool (shifts, both projections, series, table cells) and the drift written into the stack (exact: `[[2k, -k]]`); the real photon stream gives "below one pixel" |
| 2 actions, errors | the errors, exports, dialog and picker tests | corrupt, one-frame and missing files, a failing worker, unwritable exports, busy, drops |
| 3 spec | `test_every_spec_key_exists_on_the_model`, `test_every_qt_setting_is_in_the_emtk_spec_with_the_same_range`, `test_the_qt_choice_lists_equal_the_emtk_choice_lists` | label, min, max, decimals, options, labels, description equal the Qt spec |
| 4 draws | `test_the_window_draws_empty_and_populated_at_both_sizes`, `test_every_view_is_drawn_after_a_measurement` | |
| 5 workflow | `measured()` in every test: type the path, Enter, wait for the worker; `test_the_estimator_panel_...` against the live Qt tool | |
| 6, 7, 8 | `test_port_is_qt_free`, `test_every_control_has_a_tooltip`, `test_the_populated_window_has_a_tooltip_...`, `test_settings_round_trip_and_invalid_values_are_ignored` | |

Deliberate breakage (restored; 77 passed and 4 xfailed afterwards): the table's `dx` column filled with `dy` AND the status line replaced by "Done" after a measurement -> 15 failed (`test_choosing_a_drifting_stack_...`, `test_the_options_give_...`, the six scenarios, the photon-stream tests, `test_the_shift_table_...`,
`test_browse_opens_the_dialog_...`, `test_a_worker_that_raises_...`, `test_the_window_draws_...`).

Pre-existing failures I did not cause: none in this folder.

### 6a. Real-input coverage (control -> test)

Pointer press / release at the drawn rectangles, typed keys, drags, the wheel, `ControlSurface.on_files_dropped`; no model call stands in for a click.

| Control | Test |
|---|---|
| Measure (and greyed while running; with nothing loaded) | `test_the_options_give_...`, `test_measure_with_nothing_loaded_...`, `test_the_actions_and_the_form_are_greyed_...`, `test_changing_a_setting_does_not_re_measure_...` |
| Image field typed + Enter, typed + click-away | `test_a_typed_path_is_measured_on_enter`, `test_a_path_typed_and_clicked_away_is_taken` |
| Browse: dialog, a clicked file, Cancel, the window's x, Escape | `test_browse_opens_the_dialog_...`, `test_browse_cancel_changes_nothing`, `test_the_file_dialog_window_has_a_title_and_a_close_button_and_escape_cancels` |
| Database: the picker, a clicked dataset, accept; Open selected / Cancel buttons (xfail), the window's x | `test_the_database_button_opens_the_picker_...`, `test_the_open_selected_button_...` (xfail), `test_the_cancel_button_of_the_database_picker_...` (xfail), `test_the_database_picker_window_close_button_...` |
| Drop (hook, empty, while busy, the Qt host's `dropEvent`) | `test_dropping_a_file_on_the_window_...`, `test_dropping_while_a_measurement_runs_is_refused`, `test_the_qt_host_delivers_a_dropped_file_to_the_app` |
| Measure on (channel list: open, the names, pick) | `test_the_channel_list_names_the_channels_...` |
| Reference / Apply by lists: open, each entry, Escape | `test_the_reference_list_...`, `test_the_apply_by_list_...`, `test_escape_closes_an_open_list_...` |
| Estimator fold, smoothing typed and arrows (limits 0 and 20), sub-pixel | `test_the_estimator_panel_opens_...`, `test_each_arrow_steps_smoothing_...`, `test_typed_extremes_are_clamped_...` (against the live Qt box) |
| Export stack / shifts: no result, dialog default names, Save (CSV and TIFF equal to the Qt files), Cancel, unwritable | `test_exports_without_a_result_...`, `test_export_shifts_writes_...`, `test_export_stack_writes_...`, `test_export_dialog_cancel_...`, `test_export_to_an_unwritable_place_...` |
| Drift trace: drag pan; wheel (xfail) | `test_a_drag_pans_the_drift_trace_and_an_image`, `test_the_wheel_zooms_the_drift_trace` |
| Projection: both canvases (drag pan, Reset view), shared colormap combo | `test_a_drag_pans_the_drift_trace_and_an_image`, `test_the_two_projections_share_one_colormap_...` |
| Shifts: header sort both ways, row click | `test_the_shift_table_header_sorts_by_value_...` |
| Tabs | the view tests click each tab's text |
| Wheel: settings window scroll; spin field (xfail) | `test_the_wheel_scrolls_the_settings_window_...`, `test_the_wheel_over_the_smoothing_field_steps_it` |
| Help, Guide, tour walked with each highlighted control operated, a dialog choice releasing the load step, every target drawn | `test_help_button_...`, `test_guide_button_...`, `test_the_tour_is_walked_to_the_end_...`, `test_a_file_chosen_in_the_dialog_also_releases_the_load_step`, `test_every_guide_target_is_a_drawn_control_or_window` |
| Settings, hub | `test_settings_round_trip_...`, `test_the_imaging_hub_contract` |

## 7. Screenshots I looked at (full size)

`after_populated_{Drift_trace,Projection,Shifts}_1200x800.png`, `..._{Drift_trace,Projection}_800x600.png`, `..._{Projection_colormap_open,reference_list_open,apply_by_list_open,channel_list_open,photon_stream,photon_stream_projection,measure_pressed_empty,corrupt_file,previous_blanking,export_dialog,help,guide_measure_step}_1200x800.png`,
`after_1200x800.png`, `after_800x600.png` (empty), `docs_drift_{workspace,before,after}.png`. Numbers equal the Qt screenshots (24.6 px, the table, the trace, the photon stream "below one pixel"). Fixed while reading: the file chooser filled the whole window with no title (now a titled window
with a close button, `after_populated_export_dialog_1200x800.png`); the image panel's guide rectangle was the plot's last item; the two projections initially shared one rectangle. Nothing is clipped at 1200x800 or 800x600; a long error message (corrupt file) wraps over five lines of the status line.

## 8. Workflow

Choose the drifting stack (Browse, a drop, a typed path or the database): the worker reads the channel list and measures: "Max drift 24.6 px over 12 frames."; the trace shows dx = -k, dy = +2k, |d| rising to 24.6; the Projection tab shows streaks before and round spots after; Shifts lists
the twelve rows. Change Reference / Apply by / the estimator and press Measure. Export shifts writes `frame,dx_px,dy_px,magnitude_px` (byte-equal to the Qt file); Export stack writes the corrected multi-page TIFF (shape, sum and frame statistics equal the Qt file). The real photon stream reports "below one pixel".

## 9. Persistence, guide, help, docs

`export_settings`: reference, mode, smoothing, sub-pixel, colormap, folder (the file and the channel are not remembered; the Qt tool remembered the window geometry only). Guide: 7 steps, 2 `await` (the load step is released by a typed path, a dialog choice or a drop; the Measure step by the outcome), targets `attr` names of the spec (the Qt
tool still resolves them) and the window titles. Help: `help.md`, links live (seam test). Docs: `docs/guides/43_drift_correction.md` (the three figures replaced by emtk screenshots of the same stack; the emoji button names). Docs gap: the tool has no demo of its own (neither had the Qt tool), so the tour needs a file of the user's.

## 10. Blocked / open

emtk gaps (none edited):
1. A tour card over a control cannot be pressed: see `okf/plugins/emtk-ports/img_tracking/REPORT.md` section 10 (the drift layout keeps the card clear of the form at 1000x700 and 1200x800, so no xfail here).
2. The wheel does not reach a spin field or an implot in a `DockManager` window: `scripts/gap_wheel_dock.py`; `test_the_wheel_zooms_the_drift_trace`, `test_the_wheel_over_the_smoothing_field_steps_it` (strict xfails).
3. **The dataset picker's buttons share one id** (`chisurf/emtk/dataset_picker.py`: `Refresh##dataset`, `Previous##dataset`, `Next##dataset`, `Open selected##dataset`, `Cancel##dataset`; emtk's `get_id` keeps only the text after `##`): the disabled Previous / Next take the release, so the picker's
   **Open selected and Cancel buttons never fire with the pointer** (the window's x and `accept()` work). Repro `scripts/gap_picker_ids.py` (5 lines of use after the stub client): both prints are True. Every Database button of the imaging tools is affected. Strict xfails `test_the_open_selected_button_...`, `test_the_cancel_button_...`.
4. The image canvas offers 4 colormaps (the Qt docks 7) and its plot tooltip talks about beads and analysis regions (`chisurf/emtk/image_canvas.py`).

## 11. Self-check against the Definition of Done

D1 yes (4). D2 yes (2, 5). D3 yes (4). D4 yes (7). D5 yes (6, 8). D6 yes (9). D7 yes (9). D8 yes (9). D9 yes (6). D10: report, evidence, board.

Evidence refreshed at the end of the imaging-family stream: every screenshot, `after.json` and `compare.json` were regenerated with the final shared shell (typed numbers kept to the decimals the field shows, wrapped messages, the file chooser as a titled window, an axis refit when a plot's data changes, the pointer parked off the window). Numbers, test counts and the compare result are those stated above.
