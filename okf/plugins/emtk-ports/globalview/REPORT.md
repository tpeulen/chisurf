# emtk port report — `globalview` (swap-candidate upgrade, audit-all row 4)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `globalview` / `chisurf/plugins/core/globalview` |
| Port type | A: the Qt `GraphWizard` already hosts the emtk `GlobalViewSurface` (in HEAD); the earlier stream's factory built the bare surface |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Effort (hours) | ~1 |
| Commits | `7b073181d` globalview: Qt baseline and current emtk state; `21cc86875` globalview: emtk app at parity with the Qt tool; evidence commit "globalview: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

```
 M chisurf/plugins/core/globalview/gui/__init__.py
 M chisurf/plugins/core/globalview/gui/emtk_view.py
 M chisurf/plugins/core/globalview/gui/model.py
 M chisurf/plugins/core/globalview/manifest.json
 M chisurf/plugins/core/globalview/tests/test_model.py
?? chisurf/plugins/core/globalview/gui/app.py
```

All committed with the app (copies and diff in `pre-upgrade/`). The stream's `emtk_view.py`/`model.py` import the shared
`chisurf.emtk.node_editor` package, which is **untracked** (another stream's `?? chisurf/emtk/node_editor/`): HEAD now needs that
package to land with its stream.

## 2. Control checklist

The parity tool counts 0 Qt controls (`before.json`): the Qt window is one emtk surface. The surface (toolbar, Network, Parameters,
Selection, View docks, status line) is the same object on both hosts (`before_populated.png` vs `before_emtk_populated_*.png`:
identical). What differed is what the Qt *window* answered for the model:

| # | Qt window service | Used by | emtk app | Present? |
|---|---|---|---|---|
| 1 | `QFileDialog.getSaveFileName` | Save…, Export parameters | in-app `FileDialog` in a `DialogWindow`; the action re-runs with the path (`answer_file`) | added |
| 2 | `QFileDialog.getOpenFileName` | Load… | same, open mode | added |
| 3 | `dialogs.warning` | Link refused / cycle | in-app message window with OK; text also in the status line (as Qt) | added |
| 4 | `HelpButton.show_help` (`help.md`) | `?` | `EmTkHelpWindow(help.md)` | added |
| 5 | `GuidedTour(guide.json)` with dock reveal | Guide | `EmTkGuidedTour`, `on_step_change` → `surface.reveal`, forms' `on_used` → `notify_used` | added |
| 6 | fitting-client `fit.`/`parameter.` subscription → debounced `fits_changed` | live refresh | same subscription when the client module is loaded; flag set on the event thread, consumed next frame | added |
| 7 | dock layout in `<settings>/globalview_layout.json` | layout | same file (`_layout_store`), saved on close | fixed (stream used emtk's default path) |
| 8 | window geometry (`settings_key` `plugin_globalview`) | host | host's (unchanged) | n/a |

## 3. Files

| File | Change |
|---|---|
| `gui/app.py` | rewritten: `GlobalViewApp(GlobalViewSurface)` + `make_app(model=None, remember_layout=True)` |
| `gui/globalview.view.json` | descriptions on both `data_table` sections and their 13 untooltipped columns |
| `tests/test_emtk_globalview.py` | new, 15 tests |
| `gui/__init__.py`, `gui/emtk_view.py`, `gui/model.py`, `manifest.json`, `tests/test_model.py` | stream's edits, committed |

Qt files untouched: `gui/tool.py`.

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity after globalview --out okf/plugins/emtk-ports/globalview
after: 22 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/globalview
$ python -m test.gui.emtk_port_parity compare globalview --out okf/plugins/emtk-ports/globalview; echo "exit=$?"
exit=0      (lost [] / stale_explanations [] / untooltipped [])
```

## 5. Deliberate differences

none — `compare.json` lost = [] and explained = {}. Behavioural: the file chooser is the in-app emtk dialog, not the OS dialog.

## 6. Tests

```
$ python -m pytest chisurf/plugins/core/globalview -q -p no:cacheprovider
34 passed in 14.86s
```

| Required | Test | Asserts |
|---|---|---|
| 1 | `test_same_network_as_the_qt_window` | status line, parameter-record count and the set of answered model hooks equal `GraphWizard`'s on the same three fits (subprocess) |
| 2 | `test_export_runs_through_the_in_app_file_dialog`, `test_save_and_load_network_round_trip`, `test_a_cancelled_dialog_changes_nothing`, `test_a_warning_is_an_in_app_message`, `test_help_and_guide` | CSV rows written, GraphML saved and re-applied (a changed value restored), cancel writes nothing, warning shown and closed |
| 3 | `test_every_spec_key_exists_on_the_model` | attrs, actions, table sources |
| 4 | `test_draws_populated[1200x800, 800x600]` | summary and legend drawn |
| 5 | `test_fit_events_refresh_the_network`, `test_the_tour_waits_for_the_awaited_control`, `test_every_guide_target_is_found_on_the_surface` | event → refresh on the next frame, unsubscribe on close; tour awaits; all 11 guide targets resolve |
| 6 | `test_port_is_qt_free` | |
| 7 | `test_every_control_has_a_tooltip` | inventory empty + spec walk incl. table columns |
| 8 | `test_layout_is_kept_where_the_qt_window_keeps_it` | `globalview_layout.json` in the settings folder; `export_settings() == {}` (Qt kept only geometry and layout) |

Deliberate breakage: answering "" instead of the chosen path → export and round-trip tests failed (`FileNotFoundError ... params.csv`,
`assert (False)`); consuming the event flag without refreshing → `test_fit_events_refresh_the_network` failed (`assert [] == [1]`).
Restored.

Pre-existing failures: none in the folder.

## 7. Screenshots read

| File | Observation |
|---|---|
| `after_populated_1200x800.png`, `_800x600` | same as Qt (`before_populated.png`) |
| `after_populated_save_dialog_1200x800.png` | first capture: dialog drawn transparent over the graph → hosted in a `DialogWindow`; re-grabbed, opaque |
| `after_populated_warning_800x600.png` | message window fits its text (`fit_height`) |
| `after_1200x800.png`, `after_800x600.png` | empty state: "No fits ... nothing to draw" |

## 9. Persistence, guide, help, docs

* `export_settings() == {}`; layout file as Qt. Guide: existing `guide.json` (11 steps, 2 awaits), all targets found. Help: existing `help.md`.
* Docs: no change in what the user sees in the window.

## 10. Blocked / open

* `chisurf/emtk/node_editor/` is untracked (another stream) and now imported by committed plugin code.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
