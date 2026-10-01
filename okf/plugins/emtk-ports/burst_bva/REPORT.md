# emtk port report — `burst_bva` (upgrade, audit-all row 28)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_bva` / `chisurf/plugins/burst/burst_bva` |
| Port type | B (run port): the Qt `BVATool` draws `BurstBvaApp` in a `ControlHost` and owns the run (ChiSurfProgress worker, result cache, stamp, auto update, reuse of the read burst table, Save plot as a host grab, INI defaults); the emtk app runs the same drawing with the stream's `BvaController` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `e8d85062b` baseline; `4cfbadc96` core fix (compute_bva); `dbb92e9fd` emtk app at parity with the Qt tool; evidence commit "burst_bva: evidence and report" |
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
29 passed in 38.29s
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
