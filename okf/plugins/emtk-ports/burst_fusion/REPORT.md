# emtk port report — `burst_fusion` (upgrade, audit-all row 29)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_fusion` / `chisurf/plugins/burst/burst_fusion` |
| Port type | B (run port): at HEAD the Qt `BurstFusionTool` drew `BurstFusionApp` whose buttons called the model synchronously, with its own demo loader; the stream gave the app a `FusionController` (worker, settings files, report, MMFDB picker) used by both hosts |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `ab54d527b` baseline; `a2ca536f1` emtk app at parity with the Qt tool; evidence commit "burst_fusion: evidence and report". Related: `cf90cf323` (burst_2cde axis test measures the drawn range) |
| Board | `T-20261001-EMTK1B` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `core/fusion.py` (cancel check), `gui/app.py`, `gui/tool.py` (closes the app),
`gui/view_model.py` (cancel check), `manifest.json` (emtk entrypoint), `tests/test_gui.py` (help/guide now in-emtk); untracked
`gui/controller.py`, `tests/test_native.py`. All committed with the app.

## 2. Parity checklist (`before_populated.png` vs `before_emtk_populated_*` → `after_*`)

| Qt (HEAD) | Stream's emtk | Now |
|---|---|---|
| Demo (toolbar action, progress in the status reporter); Estimate / Run synchronous | worker for all three | same; frames at 10 Hz while running (was continuous) |
| result: the form's text ("428 → 283 bursts (125 fused …)") | plus the controller repeating the model status | once |
| — | Open folder, MMFDB, load/save settings, export report (gained) | kept; one sized dialog per action (was one full-viewport "input / output" dialog with a JSON filter for the folder too) |
| drop (host → app) set any path as the folder | same | folder or container, else "Burst fusion reads a burst-analysis folder; … is not one." |
| workflow API `set_folder`, `set_channel_settings`, `output_folder`, `process_bursts` | on the app too | unchanged |

Shared drawing, fixed: the fragments histogram (log y) auto-fitted the bar tops only (20–158 on the demo: the 3-fragment bar on
the floor, the 1-fragment bar past the top). A first `COND_ONCE` limits request on an already-drawn plot is not applied by
emtk (and it switches auto-fit off), which left the axis at 1e-6–1 in the live order of events
(`after_live_1200x800.png` is that order). Now applied with `COND_ALWAYS` whenever the bars change, held otherwise; integer
fragment ticks. Guide: targets were looked up among buttons only, so `folder`, `threshold`, `max_gap_ms` (spec fields), `Load demo`
and `Summary` were never found, and the `await` steps never waited; now both rect sources, those names, `wait_for_controls`.

## 4. Automated evidence

```
after: 71 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/burst_fusion
compare: exit=0   (lost [] / stale [] / untooltipped [];  the Qt side inventories 0 controls: one canvas)
```

## 5. Deliberate differences

None in `compare.json`. Behaviour: Demo/Estimate/Run on a worker; the gained file actions.

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/burst_fusion -q -p no:cacheprovider
64 passed in 68.88s
```

`test_emtk_fusion_parity.py` (12): the plugin's demo fused by the Qt tool (subprocess, own settings folder) and by the emtk app
(own demo folder — the shared cache already holds fused folders, and the writer then names the output `…_0`) gives the same
output name, files, status and summary, and 283 bursts is nearer the declared 300 molecules than 428; stop before writing; the
result once; settings round trip, invalid settings, report; errors; per-action dialogs, folder by dialog and drop; the fragments
axis read from the drawn plot after the plot existed empty; guide targets (buttons and form fields); draws; Qt-free; tooltips.

Deliberate breakage, round 1: fragments limits removed → axis test failed; drop validation removed → errors test failed. Round 2:
controller status copy restored → status-once test failed; the Summary alias removed → guide test failed. The ONCE-only call
(the first fix) → axis test failed `(1e-06, 1.0, [158, 105, 20])`. All restored.

Measurement trap recorded: a limits test that checks only the *request* passed while the drawn axis was 1e-6–1. Read the plot's
range at `end_plot`, on a plot drawn before the data arrives.

## 7. Screenshots read

`before_populated.png` (Qt HEAD), `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,800x600}.png`,
`after_live_1200x800.png`, `after_*`.

## 9. Persistence, guide, help, docs

Settings files via the controller (gained); window geometry host's. Guide content unchanged, now walkable. Docs: none.

## 10. Blocked / open

* emtk: a first `COND_ONCE` `setup_axis_limits` on a plot that already exists is ignored but disables auto-fit — worth a look
  in emtk (recorded, not changed: emtk is out of scope for this claim).

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
