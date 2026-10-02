# emtk port report - `img_frc` (port-incomplete upgrade, audit-all row 84, imaging family 3 of 4)

Agent: claude (Sonnet), 2026-10-02, per `UPGRADE_BRIEF.md`; board entry `T-20261002-IMGFAM`. Type **B** (the Qt tool is an AutoForm `ImgFrcTool`; `gui/view_model.py` is already Qt-free and is reused, `gui/model.py` adds the emtk side). The earlier stream's app (`pre-upgrade/app.py.txt`, 69 lines)
is replaced. Verdict: **accept**; no numerical difference from the Qt tool; defects of the stream's app and one defect of the Qt status bar are listed in section 0.

Commits: `8d0902b09` Qt baseline and the stream's emtk state, then the app commit (code, tests, shared-shell changes) and the evidence commit.

## 0. Defects found

In the stream's app (`before_emtk_populated_1200x800.png`): after a successful measurement the message still read "No image loaded." (it was read before the model ran); the resolution marker was a one-point line, invisible (the legend entry "resolution" had no symbol); no pixel size, channel, second channel,
second file, axis order, ring width, no resolution summary, no halves, no ring table, and the output path was typed by hand. In the Qt tool: a failed measurement says only "Measurement failed" in the status bar (the reason is in the model and was never shown), and the Second channel combo shows the first channel's name while the
measurement uses the channel after the first (the emtk list says "next channel" until a channel is chosen).

## 1. State at start

```
 M chisurf/plugins/microscopy/img_frc/manifest.json
?? chisurf/plugins/microscopy/img_frc/app.py
?? chisurf/plugins/microscopy/img_frc/strings.py
?? chisurf/plugins/microscopy/img_frc/test/test_native.py
```

Copied to `pre-upgrade/` and committed with the baseline. Files edited that I did not write: `manifest.json` (entrypoint path), `test/test_native.py` (import path; its two tests unchanged). `app.py` and `strings.py` removed (the Qt tool had no translations). Qt baseline: `before.png`, `before.json` (58 controls), mine
`before_populated_{empty_measure_pressed,tiff_loaded,tiff_even_odd,tiff_25nm,two_files_without_second,two_files,axis_channels,photon_even_odd,photon_channels,corrupt_file,one_frame}.png`, `before_tab_{FRC,Diagnostics,Halves,Rings,Half_1,Half_2}.png`, `qt_values.json` (every number and message of every scenario), `qt_frc.csv`.
Data (own, generated): `scripts/make_data.py` (an object seen through independent Poisson noise in 40 frames: two stacks of different seeds) and the real photon stream `test/data/clsm/PQ_Olympus_MFIS.ht3`.

## 2. What the Qt tool offered - control checklist

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Toolbar Measure ("Measuring...", then the model's status, or "Measurement failed") | `measure`, `SnapshotJob`; the status line shows the model's own message | yes |
| 2 | Toolbar Export CSV ("Nothing to export yet", `frc_resolution.csv`, "Wrote ...") | `request_export` -> FileDialog, same messages and name | yes |
| 3 | Guide, `?` | `Guide`, `Help` | yes |
| 4 | Image: path field, Browse, Database, drop (choosing reads the channels, does not measure) | `value` `filename`, `Browse`, `Database`, `files_dropped`; the worker reads the channels | yes |
| 5 | Split into halves by: Even / odd, First / second half, Two channels, Two files | `choice` with the Qt labels | yes |
| 6 | Channel, Second channel (channel names) | two `choice`s; the second adds "next channel" | yes |
| 7 | Second file: path field, Browse, Database, drop | `value` `second_filename`, `Browse`, `Database`; a drop is routed by what is missing | yes |
| 8 | Pixel size [nm] 0-1e5 (2 decimals) | spin field | yes |
| 9 | Criterion: Fixed 1/7, half-bit, 2 sigma | `choice` | yes |
| 10 | Estimator fold: TIFF axis order (Auto / All planes are frames / Leading axis is channels), Ring width 0-0.5 (4 decimals), Smoothing 1-51 | folding panel, `choice`, two spin fields | yes |
| 11 | Resolution (HTML summary) | `info` section `summary_text` | yes |
| 12 | FRC plot (curve, threshold, crossing marker, y range -0.25..1.05, legend) | `series_plot` with `y_range` | yes |
| 13 | Halves: Half 1, Half 2 docks with a shared colormap | `image_pair`, colormap synced through the model | yes (3 colormaps lost) |
| 14 | Rings table (Frequency, Period, FRC, Threshold, Ring px) | spec `data_table`, numeric cells, formats as the Qt text | yes |
| 15 | Status bar | status line | yes |
| 16 | Hub: `apply_setup_settings`, `apply_pipeline_context` | the same methods on the app (reads on the worker) | yes |
| 17 | Window geometry | `export_settings` / `restore_settings` (split, criterion, pixel size, ring width, smoothing, axis order, colormap, folder) | yes |
| 18 | Tooltips | spec `description`s | yes |

## 3. Files

| File | Change |
|---|---|
| `gui/model.py` | new: `FrcModel(EmtkModelMixin, FrcViewModel)`: actions, status line, dialogs, drop routing, numeric ring rows, hub adapters on the worker |
| `gui/frc_emtk.view.json` | new: settings form and five windows (text, ranges and choices from the Qt spec) |
| `gui/app.py` | new: `ImgFrcApp` with its own four-region layout, `make_app(coordinator=None)` |
| `gui/guide.json` | changed: 6 steps, 2 `await` (load, Measure) |
| `test/test_emtk_img_frc_parity.py` | new: 74 tests (3 strict xfails) |
| `../imaging_emtk/*` | shared shell: typed floats kept to the decimals the field shows (as a Qt spin box), muted messages wrap, `y_range` and a refit when a plot's data changes, drops routed by the model, a second database target |

Qt files untouched: `gui/tool.py`, `gui/view_model.py`, `gui/frc.view.json`, `core.py`, `backend/`, `cli/`, `client.py`, `api/`.

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity compare img_frc --out okf/plugins/emtk-ports/img_frc; echo exit=$?
{ "lost": [], "untooltipped": [] }
qt-free: True
exit=0          (explained 22, stale_explanations [], before 58 controls, after 176)
```

`after.json` is the populated app (both diagnostics tabs, every list opened; `scripts/capture_emtk_after.py`); the stock `after` draws the empty app: kept as `after_empty.json`, `after_1200x800.png`, `after_800x600.png`. `controls_without_tooltip` is `[]`, `qt_free` is `{"ok": true}`.

## 5. Deliberate differences

| Lost / changed item | Why | What replaces it |
|---|---|---|
| `?` | Qt toolbar glyph | `Help` |
| `cividis`, `plasma`, `turbo` | pyqtgraph docks have 7 colormaps; the shared emtk canvas offers magma, inferno, viridis, gray | blocked (section 10) |
| `blur`, `divide`, `subtract`, `operation`, `mean`, `off`, `timerange`, `roi`, `menu`, `frame`, `t`, `x`, `y` | pyqtgraph ImageView internals, no visible control in `before_tab_Halves.png` | gamma and display levels; axis titles |
| `2`, `4`, `5`, `6`, `7` | number texts of the Qt inventory (axis ticks) | the emtk plots' own ticks |
| Second channel list | the Qt combo showed a channel name while the measurement used the next channel | "next channel" first in the list |
| Failed measurement | the Qt bar said "Measurement failed" | the model's message with the reason |
| Drop | Qt routed a drop to the field under the pointer; an emtk drop has no position | with the two-file split and a first file chosen the drop is the second file; two dropped files fill both |
| Reading the file | Qt read it on the GUI thread | worker; the form and actions are greyed meanwhile |
| Table cells; plot view | strings; the Qt plot re-ranged on every refresh | numbers sortable by value; the axes refit once when a new result brings another range |

## 6. Tests

```
$ python -m pytest chisurf/plugins/microscopy/img_frc -q -p no:cacheprovider
98 passed, 3 xfailed in 44.84s        (25 earlier core / RPC / CLI tests + 2 native + 71 passed and 3 xfailed of the 74 new)
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider      -> 13 passed
$ python -m pytest test/test_plugin_help_guide_seam.py -q -k "img_frc or drawn or discoverable"; test/test_prd_mentions.py   -> passed
```

| Required test | Test | Asserts |
|---|---|---|
| 1 reference | `test_measure_gives_the_numbers_the_qt_window_showed_...`, `test_the_calibrated_and_the_other_criteria_...`, `test_two_files_...`, `test_the_real_photon_stream_...`, `test_the_qt_tool_and_the_emtk_app_agree_on_every_result[8 scenarios]`, `..._on_the_photon_stream_and_the_channel_split`, `test_the_hub_setup_payload_...`, `test_the_result_equals_a_written_out_split_fed_to_the_core_ring_correlation` | resolution, curve, threshold, ring counts, summary, both halves, series and table cells equal the pinned Qt numbers, the live Qt tool and numpy sums of the even and odd frames fed to the core's ring correlation |
| 2 actions, errors | the errors, exports, dialog, picker and drop tests | no image, a split that cannot be made (3 messages), unknown channel, corrupt / one-frame / missing, busy, a failing worker, unwritable export |
| 3 spec | `test_every_spec_key_exists_on_the_model`, `test_every_qt_setting_is_in_the_emtk_spec_with_the_same_range_and_choices` | label, min, max, decimals, options, labels, description equal the Qt spec |
| 4 draws | `test_the_window_draws_empty_and_populated_at_both_sizes` | |
| 5 workflow | `loaded()` + `measure()`: type the path, Enter, press Measure with the pointer | |
| 6, 7, 8 | `test_port_is_qt_free`, `test_every_control_has_a_tooltip`, `test_the_populated_window_has_a_tooltip_...`, `test_settings_round_trip_and_invalid_values_are_ignored` | |

Deliberate breakage (restored; 98 passed and 3 xfailed afterwards): the ring table's `period` filled with the frequency AND the two-file drop routing disabled -> 10 failed (`test_the_ring_table_shows_what_the_qt_table_showed`, the eight scenario comparisons, `test_a_drop_loads_the_first_file_and_with_the_two_file_split_the_second_one`).
A real defect the click tests found in my first draft: a file dropped before the worker handed back its snapshot lost a second file set meanwhile (the worker's copy overwrote it); the model now sets the cheap state first.
Pre-existing failures I did not cause: none in this folder.

### 6a. Real-input coverage (control -> test)

Pointer press / release at the drawn rectangles, typed keys, drags, the wheel, `ControlSurface.on_files_dropped`; no model call stands in for a click.

| Control | Test |
|---|---|
| Measure (greyed while running; nothing loaded) | the numbers tests, `test_measure_with_nothing_loaded_...`, `test_the_actions_and_the_form_are_greyed_...`, `test_changing_a_setting_does_not_re_measure_...` |
| Image field typed + Enter / click-away; Browse (dialog, a clicked file, Cancel, x, Escape) | `test_a_typed_path_is_taken_on_enter_...`, `test_choosing_a_file_reads_its_channels_...`, `test_browse_opens_the_dialog_...`, `test_browse_cancel_the_window_close_button_and_escape_...` |
| Second file typed, click-away, Browse | `test_the_second_file_is_typed_browsed_and_clicked_away` |
| Database buttons (both): picker, a clicked dataset, accept; Open selected (xfail); the window's x | `test_the_database_buttons_pick_the_first_and_the_second_acquisition`, `test_the_open_selected_button_...` (xfail), `test_the_database_picker_window_close_button_closes_it` |
| Drops (first file, second file by routing, two files, while busy, the Qt host's `dropEvent`) | `test_a_drop_loads_the_first_file_...`, `test_dropping_while_a_worker_runs_is_refused`, `test_the_qt_host_delivers_a_dropped_file_to_the_app` |
| Split list (4), Criterion list (3), TIFF axis order list (3): open, each entry, Escape | `test_the_split_list_...`, `test_the_criterion_list_...`, `test_the_axis_order_list_...`, `test_escape_closes_an_open_list_...` |
| Channel and Second channel lists (names, "next channel") | `test_the_channel_lists_name_the_channels_...` |
| Pixel size, Ring width, Smoothing: typed, arrows, limits, decimals; clamps against the live Qt boxes | `test_the_numeric_fields_take_typed_values_...`, `test_typed_extremes_are_clamped_...` |
| Estimator fold | `test_the_axis_order_list_...`, `test_the_numeric_fields_...` |
| Export CSV: no result, default name + Save (bytes equal to the Qt file), typed name, Cancel, unwritable | `test_export_without_a_result_says_so`, `test_export_csv_writes_the_file_the_qt_tool_wrote`, `test_export_to_a_typed_name_cancel_and_an_unwritable_place` |
| Resolution window, FRC plot (drag pan, refit on a new result; wheel xfail), no crossing | `test_the_resolution_window_and_the_curve_are_drawn_...`, `test_a_drag_pans_the_curve_and_a_new_result_refits_the_view`, `test_the_wheel_zooms_the_curve` (xfail), `test_no_crossing_is_reported_...` |
| Halves: colormap combo (shared), pan, Reset view | `test_the_two_halves_share_one_colormap_...`, `test_a_drag_pans_a_half_image_and_reset_view_restores_it` |
| Rings table: header sort both ways, row click | `test_the_ring_table_header_sorts_by_value_...` |
| Tabs | the view tests click each tab's text |
| Wheel: settings window scroll; spin field (xfail) | `test_the_wheel_scrolls_the_settings_window_...`, `test_the_wheel_over_the_pixel_size_field_steps_it` |
| Help, Guide, the tour walked with each highlighted control operated, a dialog choice releasing the load step, every target drawn | `test_help_button_...`, `test_guide_button_...`, `test_the_tour_is_walked_to_the_end_...`, `test_a_file_chosen_in_the_dialog_releases_the_load_step`, `test_every_guide_target_is_a_drawn_control_or_window` |
| Settings, hub | `test_settings_round_trip_...`, `test_the_imaging_hub_adopts_its_source_...`, `test_the_hub_setup_payload_...` |

## 7. Screenshots I looked at (full size)

`after_populated_{Halves,Rings}_1200x800.png`, `..._{Halves,Rings}_800x600.png`, `..._{Halves_colormap_open,split_list_open,criterion_list_open,axis_order_list_open,channel_list_open,second_channel_list_open,pixels,half_bit,two_files,photon_even_odd,photon_channels,measure_pressed_empty,two_files_without_second,corrupt_file,export_dialog,help,guide_measure_step}_1200x800.png`,
`after_1200x800.png`, `after_800x600.png` (empty), `docs_frc_workspace.png`. Numbers equal the Qt screenshots (4.292 px, 107.3 nm, 116.4 nm for the photon stream). Fixed while reading: the diagnostics region was too narrow (the second half image and the table headers were cut: layout 42 / 58 and fitted columns); the empty-state messages ran past
their window (now wrap); the file chooser fills the window without a title (now a titled window with a close button). Nothing is clipped at 1200x800; at 800x600 the table's last column and the curve's axis labels crowd (emtk layout).

## 8. Workflow

Choose the stack (Browse, a drop or a typed path): its channels are read, nothing is measured; press Measure: "Resolution 4.292 px (fixed_1/7).", the summary, the curve with the crossing marker, the two halves and the 48 rings. Set the pixel size and press Measure again: 107.3 nm. Switch the split to Two files, choose the second stack and measure:
93.05 nm; Two channels on the photon stream (ch0 / ch1): 94.98 nm. Export CSV writes `frequency_1/nm,correlation,threshold,ring_pixels` (byte-equal to the Qt file).

## 9. Persistence, guide, help, docs

`export_settings`: split, criterion, pixel size, ring width, smoothing, axis order, colormap, folder (never the files or the channel; the Qt tool remembered the window geometry only). Guide: 6 steps, 2 `await`, targets `attr` names of the spec (the Qt tool still resolves them) and the FRC window. Help: `help.md` unchanged, links live (seam test).
Docs: `docs/guides/51_frc_resolution.md` (figure replaced by the emtk screenshot of the photon stream, button names without emoji, the "choosing a file does not measure" note).

## 10. Blocked / open

emtk gaps (none edited):
1. A tour card over a control cannot be pressed: `okf/plugins/emtk-ports/img_tracking/REPORT.md` section 10 (the FRC layout keeps the card clear of the form at the tested sizes).
2. The wheel does not reach a spin field or an implot in a `DockManager` window: `scripts/gap_wheel_dock.py`; strict xfails `test_the_wheel_zooms_the_curve`, `test_the_wheel_over_the_pixel_size_field_steps_it`.
3. The dataset picker's buttons share one id, so Open selected and Cancel never fire: `scripts/gap_picker_ids.py`, `okf/plugins/emtk-ports/img_drift/REPORT.md` section 10; strict xfail `test_the_open_selected_button_...`.
4. The image canvas offers 4 colormaps (the Qt docks 7); its plot tooltip talks about beads.

## 11. Self-check against the Definition of Done

D1 yes (4). D2 yes (2, 5). D3 yes (4). D4 yes (7). D5 yes (6, 8). D6 yes (9). D7 yes (9). D8 yes (9). D9 yes (6). D10: report, evidence, board.

Evidence refreshed at the end of the imaging-family stream: every screenshot, `after.json` and `compare.json` were regenerated with the final shared shell (typed numbers kept to the decimals the field shows, wrapped messages, the file chooser as a titled window, an axis refit when a plot's data changes, the pointer parked off the window). Numbers, test counts and the compare result are those stated above.
