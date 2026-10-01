# emtk port report — `tttr_time_windows` (swap-candidate upgrade, audit-all row 7)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `tttr_time_windows` / `chisurf/plugins/tttr/tttr_time_windows` |
| Port type | B → existing emtk app; the committed Qt `TTTRTimeWindowTool` (toolbar, DockArea: Settings / Files / Preview / Summary); the stream rewrote `gui/tool.py` to host the emtk app |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Effort (hours) | ~1.5 |
| Commits | `af03166a4` baseline; `892ab2c3b` emtk app at parity with the Qt tool; evidence commit "tttr_time_windows: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

Modified `gui/tool.py`, `manifest.json`, `tests/test_construction_smoke.py`; untracked `gui/app.py`, `gui/controller.py`,
`gui/guide.json`, `gui/help.md`, `tests/test_emtk_controller.py` (`pre-upgrade/`). Baseline from HEAD `tool.py`
(`scripts/qt_head.py`): 14 controls. Incident: the first Qt populated run wrote its output next to the test file
(`test/data/clsm/Leica_SP5_TW_10000ms/`, the script set the wrong output field); the folder (mine, untracked, created that minute)
was moved to the scratchpad and the script fixed.

## 2. Control checklist

| Qt (committed) | emtk | Present? |
|---|---|---|
| Toolbar Process / Clear / Help; menu File ▸ Exit, Help ▸ About | Process, Clear, Help (twice), Guide; window close is the host's | yes (menus: host level) |
| Settings: Time window (ms suffix), Output folder + Browse… | Time window (ms), Output folder + Browse… | yes |
| Files: path list, add files/folder/database, remove, drop | Files, Folder, Database, Remove, drop, list | yes |
| Preview: Preview file combo, intensity trace with window boundaries | click a file in the list → trace with boundaries | yes (deliberate) |
| Summary: log | Processing log | yes |
| Status bar ("Ready", "Preview: …", "Processing complete") | status line in the Settings pane | **fixed** (was a full-viewport window) |

Output: Leica_SP5.ptu, 10 000 ms → 16 windows, `Leica_SP5.bst` 246 bytes, sha256 `4e4d0add2e46ce4f…` from both tools.

## 3. Files

| File | Change |
|---|---|
| `gui/controller.py` | status window removed; job / file dialogs in `DialogWindow`s; `process_pending` queues Process behind a preview load; dock `LayoutStore` (saved on close only if changed) |
| `gui/app.py` | labels without pictograms, plain Process, `Time window (ms):`, status line, unused colour constants removed, boundaries capped at `MAX_BOUNDARY_LINES` |
| `tests/test_emtk_time_windows_parity.py` | new, 10 tests |
| `tests/test_emtk_controller.py` | stream's; photon_table parts removed (its controller no longer exists after the photon_table port) |
| `test/prd_mention_allowlist.txt` | struck `tests/test_construction_smoke.py` (no longer names a PRD) |

## 4. Automated evidence

```
after: 35 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/tttr_time_windows
compare: exit=0   (lost [] / stale_explanations [] / untooltipped [])
```

## 5. Deliberate differences (`deliberate.json`)

| Item | Why / replacement |
|---|---|
| `droptttrfileshere` | longer caption with the extensions |
| `previewfile` | the Preview-file combo became "click a file in the list" |
| `selectafiletopreviewitsintensitytrace.` | hint now in the empty plot |
| `timewindow` | unit moved from the spin-box suffix into the label |

## 6. Tests

```
$ python -m pytest chisurf/plugins/tttr/tttr_time_windows -q -p no:cacheprovider
27 passed in 11.72s
```

| Required | Test | Asserts |
|---|---|---|
| 1 / 5 | `test_process_writes_the_qt_tools_bst` | Process pressed while the preview loads; through app frames the `.bst` equals the Qt tool's (size, sha256), 16 windows |
| 2 | `test_a_status_message_does_not_cover_the_tool`, `test_the_job_and_file_windows_are_sized` | message drawn with the tool around it; file window smaller than the viewport |
| 4 | `test_labels_have_no_pictograms_and_draw_at_both_sizes[...]`, `test_process_is_a_plain_button` | |
| 6 / 7 | `test_port_is_qt_free`, `test_every_control_has_a_tooltip` | |
| 8 | `test_dock_layout_is_kept_only_when_changed` | nothing written on open/close; saved when changed |
| extra | `test_window_boundaries_are_drawn_only_when_they_can_be_told_apart` | 15 014 → none, 15 → drawn |

Deliberate breakage: not re-running the queued Process → bst test failed (`AssertionError: []`); status line removed → status test
failed. Restored.

Pre-existing failures found and fixed: `test_emtk_controller.py::test_pure_apps_render_with_file_choosers` and
`::test_photon_load_publishes_only_when_polled` imported `photon_table.gui.controller`, removed by the photon_table port (0ad96ee1f).

## 7. Screenshots read

| File | Observation / fix |
|---|---|
| `before_emtk_populated_preview_*`, `before_emtk_populated_processed_1200x800.png` | the whole window replaced by "Preview: …" / "Processing complete" on black → fixed |
| `after_populated_processed_1200x800.png` | files, settings with status, 16 windows, log |
| `after_populated_preview_*` | first grab: the 10 ms preview drew 15 014 boundary lines (`len(bounds)`), filling the plot and hiding the trace (same in Qt, `before_populated_preview.png`) → boundaries drawn only up to 300 (`MAX_BOUNDARY_LINES`); re-grab shows the trace |

## 9. Persistence, guide, help, docs

Dock layout as Qt (settings folder instead of QSettings); geometry is the host's. Guide/help: stream's files. Docs: none changed.

## 10. Blocked / open

* none open for this plugin (the boundary-line flood is fixed here; the Qt tool keeps it).

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
