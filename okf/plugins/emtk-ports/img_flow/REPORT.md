# emtk port report - `img_flow` (port-incomplete upgrade, audit-all row 86, imaging family 4 of 4)

Agent: claude (Sonnet), 2026-10-02, per `UPGRADE_BRIEF.md`; board entry `T-20261002-IMGFAM`. Type **B** (the Qt tool is an AutoForm `ImgFlowTool`; `gui/view_model.py` is already Qt-free and is reused, `gui/model.py` adds the emtk side). The earlier stream's app
(`pre-upgrade/app.py.txt`, 97 lines) is replaced; **the demo workflow is kept** (Load demo -> Map flow, and the guided tour that presses neither for the user). Verdict: **accept**, with one open defect that is not the port's: the demo reads back as zeros with the installed tttrlib (section 0).

Commits: `cc2353319` Qt baseline and the stream's emtk state (incl. the stream's `demo.py` tag edit), then the app commit (code, tests, shared-shell changes) and the evidence commit (this report, screenshots, docs, the known-issues entry).

## 0. Defects found

1. **The demo yields no arrows in this environment, in the Qt tool and in the port alike** (known issue 5 of `okf/references/known-issues.md`; the plugin's own `test_the_demo_is_a_readable_ptu_whose_flow_comes_back` fails: 25 of 25 tiles escaped). Measured here: the demo PTU
   (722 194 records, 50 frame markers, 3200 line markers, 715 744 photons) reconstructs with tttrlib 0.27.0 into an **all-zero stack** (49 frames at HEAD's loader, 50 with the stream's uncommitted padding edit in `core/fluorescence/imaging/image_source.py`): `CLSMImage.get_line_duration()` is 0.0 and each
   line's record range holds 2-3 records. The same photons with the tag `ImgHdr_Frame` written as 4 instead of 3 reconstruct (as one 64-line frame) with every count. The frame count (29 of 30) was never the cause. Repro `scripts/gap_demo_ptu_zero.py` (seconds); entry extended in `okf/references/known-issues.md`.
   It sits in tttrlib / the shared loader, outside this port; `Load demo` and `Map flow` work and say what happened ("No arrows: All 25 tile(s) were refused..."), the profile still draws the simulated truth, and every other path (TIFF stacks) is verified against the Qt window and a known speed. A strict xfail
   (`test_the_demo_gives_arrows_along_plus_x_with_a_parabolic_profile`) flips the moment the reader is fixed.
2. In the stream's app (`before_emtk_populated_1200x800.png`): the scanner timing was not settable (every measurement used the defaults: wrong velocities for any real scan), the tile table was hand drawn and its columns drew over each other, there were no arrows at all (a profile only), no channel, no quality display,
   no summary, no Export dialog (a typed path), the demo did not set the timing.
3. In the Qt tool: the flow-field image looks transposed. Flow along +x smears each molecule into a horizontal streak in the time-averaged image, but `before_populated_tiff_stics.png` shows vertical stripes (the section draws `data.T` into an image view that is already row-major); the emtk field draws the image the right way up
   (`after_populated_Profile_1200x800.png`). The arrows are the same in both.

## 1. State at start

```
 M chisurf/plugins/microscopy/img_flow/demo.py
 M chisurf/plugins/microscopy/img_flow/manifest.json
?? chisurf/plugins/microscopy/img_flow/app.py
?? chisurf/plugins/microscopy/img_flow/strings.py
```

Copied to `pre-upgrade/` (`app.py.txt`, `strings.py.txt`, `demo.py.txt`, `manifest_and_demo.diff`) and committed with the baseline. `demo.py` carries one added header tag (`ChiSurf_DemoFrames`, the stream's, paired with its loader edit); it is committed unchanged. Files edited that I did not write: `manifest.json` (entrypoint path),
`gui/guide.json` and `gui/help.md` (emtk wording). `app.py` and `strings.py` removed (the Qt tool had no translations). Qt baseline: `before.png`, `before.json` (35 controls), mine `before_populated_{empty_map_pressed,demo_loaded,demo_mapped,tiff_loaded,tiff_stics,no_arrows,escaped,pcf,corrupt_file,two_frames}.png`,
`before_tab_{Flow,Flow_field,Profile,Profile_selected,Tiles,Profile_and_tiles}.png`, `qt_values.json`, `qt_flow.csv`. Data: the demo (simulated by the plugin, about 20 s) and a TIFF with a known speed (`scripts/make_data.py`: the plugin tests' own stack, 0.5 px/frame along +x, 48 lines of 0.32 ms, 100 nm pixels: 3.25 um/s).

## 2. What the Qt tool offered - control checklist

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Toolbar Map flow (background run; "Load an image first."; the model's status incl. the diagnosis of an empty map) | `button_row` `map_flow`, `SnapshotJob`, status line | yes |
| 2 | Toolbar Load demo (simulates once, selects the file and sets the scanner timing) | `demo` button, worker, status line; the tour waits for its outcome | yes |
| 3 | Toolbar Export CSV ("Nothing to export yet", `flow_map.csv`, "Wrote ...") | `request_export` -> FileDialog | yes |
| 4 | Guide, `?` | `Guide`, `Help` | yes |
| 5 | Image: path field, Browse, Database, drop | `value` `filename`, `Browse`, `Database`, `files_dropped`; the worker reads the channels | yes |
| 6 | Channel (names of the file) | `choice` | yes |
| 7 | Estimator: STICS / Pair correlation | `choice` with the Qt labels | yes |
| 8 | Tile [px], Frame lags, Pair distance [px], Min. quality | spin fields, Qt ranges | yes |
| 9 | Scanner fold: Pixel dwell, Frame time, Line time, Pixel size | folding panel, four spin fields | yes |
| 10 | Display and estimator fold: Arrow scale, Tile step, Background (frame / stack) | folding panel, two spin fields, `choice` | yes |
| 11 | Flow (HTML summary: mean speed, mean vector, coherence, refusals, the demo note) | `info` section | yes |
| 12 | Flow field: arrows over the time-averaged image, colour by speed, caption, scale shown | `quiver` view (image texture + arrows) | yes (image orientation, section 0.3) |
| 13 | Profile: speed and v_x against y, the simulated truth for the demo | `series_plot` | yes |
| 14 | Tiles table (x, y, vx, vy, Speed, Angle, Quality, tooltips) | spec `data_table`, numeric cells, `%.4g` as the Qt text | yes |
| 15 | Status bar, hub adapters, geometry, tooltips | status line, `apply_setup_settings` / `apply_pipeline_context`, `export_settings`, spec descriptions | yes |

## 3. Files

| File | Change |
|---|---|
| `gui/model.py` | new: `FlowModel(EmtkModelMixin, FlowViewModel)`: actions (`map_flow`, `demo`, `request_export`, ...), status line, dialogs, numeric tile rows, the pipeline adapter on the worker |
| `gui/flow_emtk.view.json` | new: settings form and five windows |
| `gui/app.py` | new: `ImgFlowApp` with its own four-region layout, `make_app(coordinator=None)` |
| `gui/guide.json`, `gui/help.md` | changed: 10 steps (2 waiting: the demo, the map) with `name` targets for the emtk window and the Qt `action` kept (the plugin's own spec test still passes); the help names the Guide button |
| `test/test_emtk_img_flow_parity.py` | new: 76 tests (4 strict xfails) |
| `manifest.json` | `entrypoints.emtk` -> `gui.app:make_app` |
| `../imaging_emtk/*` | shared shell (see the other three reports); this plugin added the `quiver` view's exact Qt caption strings |

Qt files untouched: `gui/tool.py`, `gui/view_model.py`, `gui/flow.view.json`, `core.py`, `demo.py` (beyond the stream's tag), `backend/`, `cli/`, `client.py`, `api/`.

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity compare img_flow --out okf/plugins/emtk-ports/img_flow; echo exit=$?
{ "lost": [], "untooltipped": [] }
qt-free: True
exit=0          (explained 2, stale_explanations [], before 35 controls, after 215)
```

`after.json` is the populated app (both diagnostics tabs, every list opened, `scripts/capture_emtk_after.py`); the stock `after` draws the empty app: kept as `after_empty.json`, `after_1200x800.png`, `after_800x600.png`. `controls_without_tooltip` is `[]`, `qt_free` is `{"ok": true}`.

## 5. Deliberate differences

| Lost / changed item | Why | What replaces it |
|---|---|---|
| `?` | Qt toolbar glyph | `Help` |
| the caption "No arrows - nothing passed the quality threshold, or the field is empty." | wrapped over several lines in the narrow field window | the same words (the test joins the lines) |
| Flow-field image orientation | the Qt section shows the time-average transposed (section 0.3) | the image the right way up under the same arrows |
| Failed run / status messages | Qt cleared them after seconds | the status line holds the last message |
| Reading the file; the demo | Qt read it on the GUI thread (the demo simulation on a pool thread) | worker; the form and actions are greyed meanwhile |
| Drops | Qt's data-source field took a drop on the field; an emtk drop has no position | the first dropped file is the image |
| Table cells | strings | numbers; a header click sorts by value |
| Caption separator | none: the strings are the Qt ones (" - " is not used) | |

## 6. Tests

```
$ python -m pytest chisurf/plugins/microscopy/img_flow -q -p no:cacheprovider
1 failed, 86 passed, 4 xfailed in 78.04s
FAILED chisurf/plugins/microscopy/img_flow/test/test_img_flow.py::test_the_demo_is_a_readable_ptu_whose_flow_comes_back     (pre-existing: section 0.1; AssertionError: assert 25 == 0, n_escaped)
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider      -> 13 passed
$ python -m pytest test/test_plugin_help_guide_seam.py -q -k "img_flow or drawn or discoverable"; test/test_prd_mentions.py   -> passed
```

(15 earlier tests, 1 of them the pre-existing failure, and 76 new: 72 passed + 4 strict xfails. The demo is simulated once per test module into a temporary folder and `demo_path` is redirected there; a test that needs it is skipped when this tttrlib build has no simulator.)

| Required test | Test | Asserts |
|---|---|---|
| 1 reference | `test_the_map_gives_the_numbers_the_qt_window_showed`, `test_each_scenario_of_the_qt_capture_is_reproduced`, `test_the_qt_tool_and_the_emtk_app_agree_on_every_result[9 scenarios]`, `test_the_demo_is_loaded_and_mapped_as_the_qt_tool_does`, `test_the_estimator_called_without_the_view_model_...`, `test_typed_extremes_are_clamped_...[10 fields]` | vx, vy, quality, summary, vectors, extent, profile series, table cells, the status and the diagnosis equal the pinned Qt numbers (`qt_values.json`), the live Qt tool and the plugin's estimator called without the view model; the mean speed is 2.93 of the 3.25 um/s written into the stack (conservative, along +x) |
| 2 actions, errors | the errors, export, dialog, picker and drop tests | nothing loaded, corrupt / missing / two frames, escaped tiles, no tile above the threshold, busy, a failing worker, a demo that cannot be made, unwritable export |
| 3 spec | `test_every_spec_key_exists_on_the_model`, `test_every_qt_setting_is_in_the_emtk_spec_with_the_same_range_and_choices` | label, min, max, decimals, options, labels, description equal the Qt spec |
| 4 draws | `test_the_window_draws_empty_and_populated_at_both_sizes` | |
| 5 workflow | `mapped()`: type the path, Enter, press Map flow with the pointer; the demo tests press Load demo then Map flow | |
| 6, 7, 8 | `test_port_is_qt_free`, `test_every_control_has_a_tooltip`, `test_the_populated_window_has_a_tooltip_...`, `test_settings_round_trip_and_invalid_values_are_ignored` | |

Deliberate breakage (restored; 86 passed and 4 xfailed afterwards): the status line replaced by "Done" after a map AND the tile table's `vx` column filled with `vy` -> 17 failed (the numbers test, the scenario comparisons, the nine Qt comparisons, the demo comparison, the error-message tests...).
Defects the click tests found in the shared shell while writing this suite: none new. Pre-existing failure I did not cause: `test_the_demo_is_a_readable_ptu_whose_flow_comes_back` (section 0.1).

### 6a. Real-input coverage (control -> test)

Pointer press / release at the drawn rectangles, typed keys, drags, the wheel, `ControlSurface.on_files_dropped`; no model call stands in for a click.

| Control | Test |
|---|---|
| Map flow (greyed while running; nothing loaded) | the numbers tests, `test_map_flow_with_nothing_loaded_says_so`, `test_the_actions_and_the_form_are_greyed_...`, `test_changing_a_setting_does_not_re_map_by_itself_...` |
| Load demo (the worker, the timing it sets, the status, the file; a demo that cannot be made) | `test_the_demo_is_loaded_and_mapped_as_the_qt_tool_does`, `test_a_demo_that_cannot_be_made_is_reported`, the tour test |
| Image field typed + Enter / click-away; Browse (dialog, a clicked file, Cancel, x, Escape) | `test_a_typed_path_is_taken_on_enter_...`, `test_choosing_a_file_reads_its_channels_...`, `test_browse_opens_the_dialog_...`, `test_browse_cancel_the_window_close_button_and_escape_...` |
| Database: picker, a clicked dataset, accept; Open selected (xfail); the window's x | `test_the_database_button_picks_a_dataset`, `test_the_open_selected_button_...` (xfail), `test_the_database_picker_window_close_button_closes_it` |
| Drops (hook, while busy, the Qt host's `dropEvent`) | `test_a_drop_loads_the_file_...`, `test_the_qt_host_delivers_a_dropped_file_to_the_app` |
| Channel list, Estimator list (2), Background list (2): open, each entry, Escape | `test_the_channel_list_...`, `test_the_estimator_list_...`, `test_the_background_list_...`, `test_escape_closes_an_open_list_...` |
| 10 numeric fields: typed, arrows, limits, decimals; clamps against the live Qt boxes | `test_the_numeric_fields_take_typed_values_...`, `test_typed_extremes_are_clamped_...` |
| Scanner and Display folds | `test_the_scanner_and_display_panels_fold` |
| Export CSV: no result, default name + Save (bytes equal to the Qt file), typed name, Cancel, unwritable | `test_export_without_a_result_says_so`, `test_export_csv_writes_the_file_the_qt_tool_wrote`, `test_export_to_a_typed_name_cancel_and_an_unwritable_place` |
| Flow window, no-arrow diagnosis | `test_tiles_that_escape_...`, `test_nothing_above_the_quality_threshold_...` |
| Flow field: caption, arrows per tile, Arrow scale (display only), drag pan; wheel (xfail) | `test_the_quiver_draws_one_arrow_per_tile_...`, `test_the_arrow_scale_changes_the_drawn_length_...`, `test_a_drag_pans_the_flow_field_and_the_profile_...`, `test_the_wheel_zooms_the_flow_field` (xfail) |
| Profile (names, the demo's truth even with no arrow, drag pan, refit) | `test_the_profile_shows_...`, `test_the_demo_adds_its_simulated_truth_...`, `test_a_drag_pans_...` |
| Tiles table: header sort both ways, row click | `test_the_tile_table_header_sorts_by_value_...` |
| Tabs | the view tests click each tab's text |
| Wheel: settings window scroll; spin field (xfail) | `test_the_wheel_scrolls_the_settings_window_...`, `test_the_wheel_over_the_tile_field_steps_it` |
| Help, Guide, the tour walked (Load demo, then Map flow, each pressed by the user), a dialog choice not releasing the demo step, every target drawn | `test_help_button_...`, `test_guide_button_...`, `test_the_tour_is_walked_to_the_end_...`, `test_a_file_chosen_in_the_dialog_does_not_release_the_demo_step_but_the_demo_does`, `test_every_guide_target_is_a_drawn_control_or_window` |
| Settings, hub (setup payload with timing and detectors, pipeline source) | `test_settings_round_trip_...`, `test_the_imaging_hub_contract_matches_the_qt_tool` |

## 7. Screenshots I looked at (full size)

`after_populated_{Profile,Tiles}_1200x800.png`, `..._{Profile,Tiles}_800x600.png`, `..._{method_list_open,background_list_open,channel_list_open,tight_quality,tiles_escaped,pair_correlation,arrow_scale_03,map_pressed_empty,corrupt_file,export_dialog,help,guide_demo_step,demo_loaded,demo_mapped,demo_profile_with_truth}_1200x800.png`,
`after_1200x800.png`, `after_800x600.png` (empty), `docs_flow_tool.png`. Numbers equal the Qt screenshots (25/25 tiles, mean speed 2.93 um/s; the demo's "No arrows ..." diagnosis). The tile table has seven columns and scrolls sideways below about 1100 px (emtk layout; the sort test runs at 1200 px).

## 8. Workflow

Press Load demo: "Simulating the demo scan..." counts the frames (20 s the first time), then "flow_demo_poiseuille.ptu: 50 frames of 64x64, 1 channel(s). Ready." with the scanner set to 20 us / 81.92 ms / 1.28 ms / 100 nm; press Map flow: in this environment "No arrows: All 25 tile(s) were refused ..." and the profile shows the simulated truth. On the TIFF with a known speed: choose the file (the channels are read),
set the scanner and tile 16 / 4 lags, press Map flow: "25/25 tiles, mean speed 2.93 um/s", arrows along +x, coherence 1.00, the profile and 25 tile rows; Export CSV writes `x,y,vx,vy,speed,angle,quality` (byte-equal to the Qt file).

## 9. Persistence, guide, help, docs

`export_settings`: the twelve analysis settings (estimator, tile, step, lags, distance, background, quality, arrow scale, the four scanner values) and the folder (never the file or the result; the Qt tool remembered the window geometry only). Guide: 10 steps, 2 waiting (Load demo outcome, Map flow outcome); targets `attr` names (the Qt tool resolves them), `title` for the windows, `name` for the emtk buttons, and `action` kept for the Qt toolbar. Help: `help.md` (the Guide button named), links live.
Docs: `docs/guides/55_pair_correlation.md` (button names without emoji). The figure `flow_tool.png` is **not** replaced: the guide says it shows what the demo should produce, which the reader defect (section 0.1) prevents; `docs_flow_tool.png` (the emtk app on the known-speed stack) is kept as evidence.
`okf/references/known-issues.md` item 5 now carries the root-cause finding and the repro.

## 10. Blocked / open

1. **The demo reads back as zeros** (section 0.1): not fixed here (tttrlib / the shared loader; another stream has uncommitted edits in `core/fluorescence/imaging/image_source.py`, `intensity.py` for the same files). Blocks: the demo figure of guide 55, the tour's last steps showing arrows, `test_the_demo_is_a_readable_ptu_whose_flow_comes_back` and this port's strict xfail.
   Tried and not the cause: `ImgHdr_TimePerPixel` / `ImgHdr_LineFrequency` tags, `BH_UsePixelClock = 0`, explicit `CLSMImage` marker arguments, a frame tag of 4 (counts appear, frames do not), pixel markers in the simulation.
2. emtk gaps (none edited): a tour card over a control cannot be pressed (`okf/plugins/emtk-ports/img_tracking/REPORT.md`, section 10); the wheel does not reach a spin field or an implot in a `DockManager` window (`scripts/gap_wheel_dock.py` of the tracking report; strict xfails here); the dataset picker's Open selected and Cancel buttons share one id and never fire (`okf/plugins/emtk-ports/img_drift/REPORT.md`; strict xfail here); the shared
   image canvas offers 4 colormaps and a bead-pick tooltip (it is not used by this plugin's field).

## 11. Self-check against the Definition of Done

D1 yes (4). D2 yes (2, 5). D3 yes (4). D4 yes (7). D5 yes (6, 8; the demo's arrows blocked by 10.1). D6 yes (9). D7 yes (9). D8 yes (9). D9 yes (6, one pre-existing failure). D10: report, evidence, board.

Evidence refreshed at the end of the imaging-family stream: every screenshot, `after.json` and `compare.json` were regenerated with the final shared shell (typed numbers kept to the decimals the field shows, wrapped messages, the file chooser as a titled window, an axis refit when a plot's data changes, the pointer parked off the window). Numbers, test counts and the compare result are those stated above.
