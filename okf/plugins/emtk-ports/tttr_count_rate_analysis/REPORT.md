# emtk port report — `tttr_count_rate_analysis` (swap-candidate upgrade, audit-all row 6)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `tttr_count_rate_analysis` / `chisurf/plugins/tttr/tttr_count_rate_analysis` |
| Port type | B → existing emtk app: the committed Qt `CountRateAnalyzer` is an AutoForm on `count_rate.view.json`; the earlier stream wrote an emtk app and rewrote `gui/tool.py` to host it |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Effort (hours) | ~1.5 |
| Commits | `93bc73867` baseline; `160534bd7` emtk app at parity with the Qt tool; evidence commit "tttr_count_rate_analysis: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `cli.py`, `gui/tool.py`, `gui/view_model.py`, `manifest.json`,
`test/test_widgets.py`, `test_cli.py`; untracked `gui/app.py`, `gui/controller.py`, `gui/guide.json`, `gui/help.md`, `tests/`.
All committed with the app. **Audit correction:** the audit's "Qt side is a single canvas" measured the rewritten `tool.py`; the
baseline is the committed AutoForm tool (`scripts/qt_head.py`: HEAD `tool.py` + `view_model.py`), 92 controls.

## 2. Control checklist

| Qt (committed) | emtk | Present? |
|---|---|---|
| Channel Definition tab (setup, reading routine, PIE, detectors table, LUT handling, Optical Setup…) | "Detector channels" window: the shared channel editor, one section at a time | yes, with the shared editor's gaps (section 5) |
| Files tab: list, + Files, Folder, Database, Remove, Clear; drop | "TTTR files": Add files, Folder…, Database…, Clear, **Remove** (added), drop | fixed |
| Calculate, Save | Calculate (plain now), Save | yes |
| Count Rates tab: rate vs file per channel | "Count rate per file" plot | yes |
| Results tab: Channel / Mean (kHz) / Std (kHz) / #Photons / Time (s) | declared `data_table`, same columns and formats (was hand-drawn) | fixed |
| — | Help, Guide (`help.md`, `guide.json`) | added by the stream |

Numbers (`scripts/capture_populated.py`, `Leica_SP5.ptu`, one channel `all`): Qt and emtk both
`{'channel': 'all', 'mean_khz': 44.72292671613037, 'std_khz': 0.0, 'photons': 6714549, 'time_s': 150.13661879999998}`.

## 3. Files

| File | Change |
|---|---|
| `gui/app.py` | selection + Remove, `remove_file` → `model.update()`, `RESULTS_TABLE` data_table via `draw_form`, no button colours |
| `tests/test_emtk_count_rate_parity.py` | new, 9 tests |
| stream's files | committed (section 1) |

## 4. Automated evidence

```
after: 43 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/tttr_count_rate_analysis
compare: exit=0   (lost [] / stale_explanations [] / untooltipped [])
```

`after_all_sections.json` (`scripts/cr_union.py`): the inventory over all six editor sections, 94 controls, 0 untooltipped.

## 5. Deliberate differences and inherited gaps (`deliberate.json`, 76 entries)

* Combo-popup entries and row numbers (binning values, file types, `—none—`): inventory artefacts.
* Populated-state controls (result columns, Remove): drawn once files/results exist.
* Renames in the shared editor (Read → Read TTTR header and decay, File Type → TTTR format, Macrotime res. → Macro-time tick, …)
  and controls in other editor sections (Detectors, PIE windows, Optical setup, TAC corrections).
* Default data: Qt's default setup has a `yellow` detector and `prompt`/`delayed` PIE windows; the shared editor's default has
  green/red and no windows.
* **NOT PORTED (shared editor, `chisurf/emtk/channel_definition.py`, another stream's file):** `Configure LUTs`, `Adjust shifts`,
  `Edit JSON`; detectors and PIE windows are stacked blocks, not tables. Recorded in known issue "Setup:Channel Definition … shared-editor
  gaps" and `okf/plugins/emtk-ports/setup_channel_definition/REPORT.md`; this plugin cannot fix them.

## 6. Tests

```
$ python -m pytest chisurf/plugins/tttr/tttr_count_rate_analysis -q -p no:cacheprovider
29 passed in 16.34s
```

| Required | Test | Asserts |
|---|---|---|
| 1 | `test_calculate_gives_the_qt_tools_row` | Calculate path on Leica_SP5.ptu reproduces the Qt row; cells drawn as `44.72`, `6714549`, `150.137` |
| 2 | `test_remove_selected_file`, `test_calculate_is_a_plain_button` | removal + refresh event, unknown path ignored; no style colours |
| 3 | `test_results_table_is_declared_with_the_qt_columns` | data_table, Qt column titles, descriptions |
| 4 | `test_draws_empty_and_populated[1200x800, 800x600]` | |
| 6 | `test_port_is_qt_free` | |
| 7 | `test_every_control_has_a_tooltip` | inventory empty in every editor section |
| 8 | `test_settings_round_trip` | queue survives export/restore |

Deliberate breakage: removing `model.update()` → `test_remove_selected_file` failed (`'files' in []`); Mean format `%.1f` →
`test_calculate_gives_the_qt_tools_row` failed (`'44.72' in [...]`). Restored. Pre-existing failures: none.

## 7. Screenshots read

`before_populated_tab_*.png` (Qt: the Files list stays empty after `add_files` — the AutoForm path_list does not refresh on
`notify`, a Qt-side defect, not ported), `before_emtk_populated_*`, `after_populated_1200x800.png` / `_800x600` (queue with Remove,
plot point at 44.7 kHz, table), `after_1200x800.png` / `after_800x600.png`. Nothing clipped.

## 9. Persistence, guide, help, docs

`export_settings()`: files, selected setup, setups path, setup definition (stream's). Guide/help: stream's files (allow-list checked by
the seam test). Docs: none changed.

## 10. Blocked / open

Shared channel-editor gaps (section 5).

## 11. Self-check

- [x] D1 · [x] D2 (shared-editor gaps declared) · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
