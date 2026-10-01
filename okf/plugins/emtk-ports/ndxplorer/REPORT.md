# emtk port report — `ndxplorer` (swap-candidate upgrade, audit-all row 8)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `ndxplorer` / `chisurf/plugins/ndxplorer` (the app itself is ndX, `modules/ndxplorer`, not edited) |
| Port type | A: both hosts run ndX's `NdxApp`; the Qt `NdxWindow` (`build_ndxplorer_window`) wraps it in a `ControlHost`, the earlier stream's `gui/app.py:make_app` builds it bare |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Effort (hours) | ~1.5 |
| Commits | `004f4e48a` baseline; `dddeb4d1f` emtk app at parity with the Qt tool; evidence commit "ndxplorer: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

```
 M chisurf/plugins/ndxplorer/manifest.json
?? chisurf/plugins/ndxplorer/gui/
?? chisurf/plugins/ndxplorer/test/
```

Committed with the app. Edited tracked plugin files: `window.py` (imports the moved helpers), `tests/test_window_routes.py`.

## 2. What differed (the UI is the same app; `before_populated.png` vs `before_emtk_populated_*.png`)

| Qt `NdxWindow` / `build_ndxplorer_window` | Earlier factory | Now |
|---|---|---|
| `app.chisurf_rpc = make_inprocess_chisurf_client()` (Send selection to) | none | same as Qt |
| `session_autosave=True` (analysis view kept in the measurement) | `False` (NdxApp default) | same as Qt; `make_app(session_autosave=False)` for tests |
| close: `app.close()` + Global View slot withdrawn | never closed by the emtk host | closes when the host detaches its callback (once) |
| File ▸ Import ▸ "From MMFDB…" (Qt picker) | "Burst selection from MMFDB…" (emtk DatasetPicker) | label restored, emtk picker kept |
| dock layout: ndX's settings file | ChiSurf native-state store (`attach_native_state`) | unchanged (deliberate: one store for every emtk app) |
| window geometry (`ChisurfDockTool`) | host's | host's |
| drop of files/folders | `NdxApp.files_dropped` | same |

## 3. Files

| File | Change |
|---|---|
| `gui/app.py` | `make_app(session_autosave=True, chisurf_rpc=None)`, RPC client, close-on-detach, close once + slot withdrawal, MMFDB label |
| `global_view_slot.py` | new: `GLOBAL_VIEW_OWNER`, `withdraw_constants`, `constants_group`, `published_group` moved out of the Qt module |
| `window.py` | re-exports them under the old names |
| `tests/test_window_routes.py` | menu route = emtk host: checks NdxApp, RPC client, autosave, slot publish/withdraw on either host |
| `test/test_emtk_ndxplorer_parity.py` | new, 8 tests |

## 4. Automated evidence

```
after: 59 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/ndxplorer
compare: exit=0   (lost [] / stale_explanations [] / untooltipped [])
```

## 5. Deliberate differences

none in `compare.json` (the Qt side inventories as 0 controls). Behaviour: the dock layout lives in ChiSurf's native-state store; the
factory widens Plot controls (split 0.44), which clips the Path hint to "Drop folder her…" at 1200 px.

## 6. Tests

```
$ python -m pytest chisurf/plugins/ndxplorer -q -p no:cacheprovider
58 passed in 36.33s
```

| Required | Test | Asserts |
|---|---|---|
| 1 | `test_the_factory_wires_what_the_qt_window_wires`, `test_same_controls_as_the_qt_window_on_the_same_table` | RPC client, autosave, layout kept; every control and menu entry of the Qt-hosted app on the same table (subprocess) |
| 2 | `test_closing_the_host_closes_the_app_once`, `test_a_never_hosted_app_is_not_closed_by_a_none_callback` | |
| 4 | `test_draws_empty_and_with_data[1200x800, 800x600]` | |
| 6 / 7 | `test_port_is_qt_free`, `test_every_control_has_a_tooltip` | |
| routes | `tests/test_window_routes.py` | menu (emtk host) and ribbon (NdxWindow) give the same wiring; slot withdrawn after close |

Deliberate breakage: no RPC client → factory test failed ("Send selection to needs ChiSurf's client"); no close-on-detach →
host-close test failed. Restored. The previously failing `test_menu_and_ribbon_host_the_emtk_app` (known issue 2026-09-29) passes.

Corrections made during the work (recorded so they are not repeated): I first read `NdxApp(layout_store=None)` as "layout not
kept", then as "kept in emtk's default file"; the measured truth is `attach_native_state` rebinding the docks to ChiSurf's store.

## 7. Screenshots read

`before.png` (tool's Qt grab), `before_populated.png`, `before_emtk_populated_*`, `after_populated_1200x800.png`,
`after_populated_800x600.png`, `after_*`. Same app; nothing clipped except the hint noted above.

## 9. Persistence, guide, help, docs

Layout and settings through `attach_native_state`; session via `session_autosave`. Guide/help are ndX's own (Help menu). Docs: none
changed.

## 10. Blocked / open

* Systemic, all emtk ports: ChiSurf's menu host never calls the app's `close()` (known issue "emtk apps opened from ChiSurf's menu
  are never closed"); ndX works around it locally.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
