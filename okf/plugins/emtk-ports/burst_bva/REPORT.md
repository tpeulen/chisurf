# emtk port report — `burst_bva` (upgrade, audit-all row 28)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_bva` / `chisurf/plugins/burst/burst_bva` |
| Port type | B (run port): the Qt `BVATool` draws `BurstBvaApp` in a `ControlHost` and owns the run (ChiSurfProgress worker, result cache, stamp, auto update, reuse of the read burst table, Save plot as a host grab, INI defaults); the emtk app runs the same drawing with the stream's `BvaController` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | (second pass, real-input: see section 6a) `e8d85062b` baseline; `4cfbadc96` core fix (compute_bva); `dbb92e9fd` emtk app at parity with the Qt tool; evidence commit "burst_bva: evidence and report" |
| Board | `T-20261001-EMTK1B` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `gui/app.py` (Clear / Save plot / Save defaults row, tooltips), `gui/tool.py`
(wires those, drops `file_type` before `compute_bva`), `manifest.json` (emtk entrypoint); untracked `gui/controller.py`,
`tests/test_emtk_actions.py`. All committed with the app.

**Committed Qt regression:** HEAD's `BVATool._analysis_worker` passed `bva_settings()` — which carries `file_type` — to
`compute_bva`, so every Qt run raised `TypeError`. The Qt baseline is therefore the stream's working-tree `tool.py` (it
filters `file_type`), now committed.

## 2. Two defects in shared code (both hosts)

* `compute_bva` appended its result columns to its input table in place (`4cfbadc96`). Both runs keep the burst table they read
  and recompute on it, so the second computation failed — "both stores have a column 'Proximity Ratio Mean'". In the Qt tool
  that is every auto update after the first. Now a copy is returned; guard `tests/test_compute_bva_leaves_input.py`.
* `BvaViewModel.set_folder` kept the previous folder's burst table; the next run computed the new folder on the old bursts.
  Now a folder or file-type change (`set_file_type`) drops it (`test_a_new_folder_is_computed_on_its_own_bursts`, Qt subprocess
  included).

## 3. Parity checklist (Qt run → emtk run)

| Qt `BVATool` | Stream's controller | Now |
|---|---|---|
| Run/Restart: `allow()`, write bv4 + `bva_settings.json` + stamp | no allow; wrote | same as Qt |
| auto update on a parameter change: recompute, **no write** | wrote bv4 on every change | no write |
| reuse the read burst table | re-read every run | reused (dropped on folder/file-type change) |
| unchanged: "Unchanged — kept the previous BVA result (🔁 Restart recomputes it)" + Restart flagged | other words | Qt words, Restart orange |
| bv4 write failure logged, result kept | result lost | result kept, status says why |
| drop: folder or container, else "BVA reads a burst-analysis folder; … is not one." | dirs only, controller method never reached (no app hook) | `files_dropped` → Qt behaviour |
| Save plot: PNG grab of the host | matplotlib re-plot | `emtk.export.save_png` of the window |
| Save defaults: QSettings INI (plugin settings path) | same path/keys | same |
| progress dialog | status text | status text; 10 Hz frames while running |
| folder picker | full-viewport window | sized dialog |

Shared drawing, fixed: the action row cut off Help in a narrow pane (wraps); unselected tabs had no tooltip (the audit's
"2 controls without tooltip").

## 4. Automated evidence

```
after: 45 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/burst_bva
compare: exit=0   (lost ['?'] explained in deliberate.json / stale [] / untooltipped [])
```

## 5. Deliberate differences

`deliberate.json`: `?` — the help button of the Qt toolbar the tool removes and hides; both hosts draw "❓ Help". Behaviour:
status text instead of a modal progress dialog.

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/burst_bva -q -p no:cacheprovider
29 passed in 38.29s   (first pass; second pass: 69 passed, section 6a)
```

`test_emtk_bva_parity.py` (13), on the 2CDE demo burst folder (static bursts on the static line, dynamic ones far above it):
the Qt worker (subprocess) gives the same Std per burst, companions and status; a second folder is computed on its own bursts in
both hosts; auto update recomputes without writing and reads once, Run writes, unchanged → Restart; stop then Run; a failed write
keeps the result; errors; drops; the folder dialog and Save plot (a PNG by frames alone); guide targets; draws at both sizes with
the action row inside the pane; Qt-free; tooltips. The stream's `test_emtk_actions.py` follows the window-picture export and
gives its mocked `im` real sizes.

Deliberate breakage, round 1: burst table kept across folders → new-folder test failed; auto update writing → auto-update test
failed. Round 2: drop message changed → drop test failed; a tab tooltip removed → tooltip test failed. Core guard: fails on the
old `compute_bva`. All restored.

## 6a. Real-input coverage (second pass) -- every control -> the test that operates it

`tests/test_emtk_bva_clicks.py` (40 tests) presses and releases the pointer at the rectangle a control was drawn in (`app.item_rects`, or the
text a dialog button drew), types with `key`, drags with `pointer_move` / `press` / `drag` / `release`, wheels with `wheel`, and delivers a host
drop with `files_dropped`. Nothing calls a model or controller method to "click"; the assertions read the visible outcome (model, status line,
drawn strings, files). Plugin total: `69 passed` (`python -m pytest chisurf/plugins/burst/burst_bva`).

| Control (checklist item) | Test |
|---|---|
| Run (computes, writes bv4 + stamp, Std equals the Qt worker's, status = Qt's) | `test_run_click_computes_bva_as_the_qt_tool_did_and_writes_the_companions` (Qt subprocess) |
| Run without a folder | `test_run_without_a_folder_says_so_in_the_window` |
| Run again unchanged -> "Unchanged ..." + Restart flagged; Restart recomputes | `test_a_second_run_is_unchanged_and_points_at_restart_whose_click_recomputes` |
| Stop (running: cancels, "BVA cancelled."; later Run computes) | `test_stop_click_cancels_the_running_computation_and_run_then_computes` |
| Stop idle; Run / Restart ignored while running | `test_stop_does_nothing_when_idle_and_run_and_restart_do_nothing_while_running` |
| error path of a run | `test_a_failed_run_shows_its_error_in_the_window` |
| Clear | `test_clear_click_removes_the_result_and_the_scatter` |
| Save defaults (INI) and restore in a new window | `test_save_defaults_click_writes_the_ini_and_a_new_window_restores_it` |
| Folder field: typed path (incl. "/"), Backspace | `test_the_folder_field_takes_typed_text_and_backspace_clears_it` |
| Folder button: dialog, click folder, Choose; Cancel and the window's close button | `test_folder_click_opens_the_dialog_and_choosing_a_folder_by_clicks_sets_it`, `test_the_folder_dialog_cancel_and_close_buttons_change_nothing` |
| file drop (folder, stray file, empty drop) | `test_a_dropped_folder_is_taken_and_a_stray_file_is_reported`, `test_an_empty_drop_is_not_taken` |
| Save plot: dialog, typed name, Save writes a PNG of the window; Cancel | `test_save_plot_click_opens_the_dialog_and_a_typed_name_writes_a_png_of_the_window`, `test_save_plot_dialog_cancel_writes_nothing` |
| Min window length, Photons per slice, Bins X, Bins Y: drag (value and drawn text), range limits | `test_each_drag_field_changes_its_value_and_the_drawn_text[4]`, `test_a_drag_stops_at_the_range_limits_of_the_qt_tool[4]` |
| bins redraw the profile without a recompute | `test_a_bins_drag_redraws_the_profile_without_a_recompute` |
| Show static line | `test_show_static_line_checkbox_toggles_the_line_in_the_plot` |
| Auto update (on: a drag / new folder recompute without writing; off: nothing) | `test_auto_update_checkbox_and_a_parameter_drag_recompute_without_writing` |
| tabs BVA Settings / Channel Definitions / Plot | `test_the_tabs_are_clickable_and_each_shows_its_own_controls`, `test_the_plot_tab_is_clickable_and_the_plot_stays_drawn` |
| Donor / Acceptor routing channels | `test_donor_and_acceptor_channels_are_typed_and_reach_the_analysis_settings` |
| Donor / Acceptor microtime ranges (valid, invalid message, cleared when valid) | `test_microtime_gates_are_typed_and_a_bad_range_is_refused_with_a_message` |
| File type (drops the read burst table) | `test_the_file_type_field_is_typed_and_drops_the_read_burst_table` |
| channel edit with auto update | `test_a_channel_edit_with_auto_update_recomputes` |
| plot: drag the region rectangle edge; pan; wheel zoom | `test_the_region_rectangle_is_dragged_by_its_edge`, `test_a_drag_in_the_plot_pans_it`, `test_the_wheel_zooms_the_plot` |
| Guide: Next, Close Tour, steps that wait for Folder and Run, walked to the end | `test_guide_click_starts_the_tour_whose_buttons_work`, `test_the_tour_waits_for_the_folder_and_run_buttons_and_is_walked_to_the_end`, `test_the_tour_next_button_is_disabled_until_the_awaited_control_is_used` |
| Help: Start Guided Tour, Close, Escape | `test_help_click_opens_the_window_whose_buttons_and_escape_close_it` |
| small window | `test_the_flow_works_in_the_small_window_too` |

Not reachable by a pointer: the plot's `BURST_REGION` drag-and-drop target (the app has no source for the payload; a drop from another
tool is the only way in; the handler is unchanged from the Qt host).

### Defects the click tests found (all in the app both hosts draw; fixed in `gui/app.py`)

1. **The four drag fields changed nothing.** emtk reports a drag that is not "live" only on release, with the value the model already had,
   so dragging Min window length / Photons per slice / Bins X / Bins Y never applied a step (the Qt host draws the same app, so it was broken
   there too). Fix: the fields are drawn under `ItemFlags.LIVE_EDIT_ON_INPUT`.
2. **No path separator could be typed in the folder field**: the field showed `str(Path(model))`, which drops a trailing "/", so every "/"
   typed was eaten on the next frame. Fix: the typed text is kept until the model's folder differs from it.
3. **No microtime range could be typed**: the field re-formatted the model's ranges every frame, reverting each half-typed (invalid)
   state ("1", "10", "10:"), so typing "10:20" appended to "0:32768". Fix as 2; the "Invalid microtime range" message is cleared once the
   value is valid.
4. **The guide did not wait.** Its Folder and Run steps carry `await`, but the tour was built without `wait_for_controls` and nothing fed
   it the control names; Run tracked `toolAction_run` while the step targets `run`. Fix: `wait_for_controls=True`, `on_used = tour.notify_used`,
   Run / Restart / Stop track their plain names too.
5. Controls without a recorded rectangle (for pointer tests) now record one (`folder_path`, the four drag fields, the two checkboxes, the
   channel / microtime / file-type fields, Clear, Save plot, Save defaults).

Deliberate breakage (second pass): round 1, the drag fields without the live flag -> 12 tests failed (all four drags, limits, bins redraw,
auto update, small window, save defaults); round 2, the folder field re-formatted from the model every frame -> the typed-folder test and the
Run test failed. Both restored (`diff` against the saved copy empty).

Evidence: `click_1 ... click_10_*.png` from `scripts/capture_clicks.py` (typed folder, Run, Bins X dragged 51 -> 15 with the profile
recomputed, static line off, typed microtime gates, folder dialog, save dialog, guide waiting on Folder, help), all read at full size;
`after_populated_*` regenerated. `compare` exit 0, stale [] , untooltipped [].

### emtk gaps seen (not edited; for the emtk owner)

* `drag_float` / `drag_int` without `LIVE_EDIT_ON_INPUT` return the model's own value on the release frame (so no drag ever applies), and
  there is no typed entry (double click / Ctrl+click) as in ImGui. Repro: `v = 51; ch, v = im.drag_float("##a", v, 1.0, 10.0, 500.0, "%.0f")`
  in a window; press on it, `app.drag` 40 px over 5 frames, release; `ch` is True only on the release frame and `v == 51`.
* The help window shows its markdown literally (`*was the FRET efficiency constant*`, `**static line**`): `chisurf/emtk/help_guide.py`.
* A text field keeps the keyboard (selection highlight, `want_capture_keyboard`) after the pointer pressed a different widget.
* A frame drawn with `PixelPainter` between two `RecordingPainter` frames makes the next typed text miss its field (observed only in the
  capture script; the capture script now lets the layout settle).

## 7. Screenshots read

`before_populated.png` (Qt, stream's tool), `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,
800x600}.png` (Help wraps at 800), `after_*`.

## 9. Persistence, guide, help, docs

INI defaults shared with the Qt tool; window geometry host's. Guide/help unchanged, every target drawn. Docs: none (behaviour of
the analysis unchanged; the fixes remove failures).

## 10. Blocked / open

none.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
