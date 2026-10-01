# emtk port report — `burst_background` (swap-candidate backfill, audit-all row 21)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_background` / `chisurf/plugins/burst/burst_background` |
| Port type | B (run port): the Qt `BurstBackgroundEstimator` already draws `BurstBackgroundApp` in a `ControlHost`, estimating synchronously on files the workflow shell pushes in (`_add_tttr_files`); the emtk app runs the same drawing with the stream's `BackgroundController` (own file inputs, emtk channel editor, worker) |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `995d3c3d0` emtk app at parity with the Qt tool; `448fc124f` baseline (committed after the app by mistake of order — the captures were taken before any code change, see below); evidence commit "burst_background: evidence and report". Core fix found here: `8e2c1f892` |
| Board | `T-20261001-EMTK1` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py` (lazy export; widget moved to `gui/tool.py`), `gui/__init__.py`,
`gui/app.py`, `manifest.json` (emtk entrypoint), `view_model.py` (cancel check, `tttr_provider`, window reset on clear);
untracked `gui/controller.py`, `gui/tool.py`, `test/test_native.py`. All committed with the app.

Capture order: the emtk "before" was drawn before any change (22:35); the Qt "before" failed then because someone was rebuilding
IMP (`IMP.bff` wrapper and binary out of step; `chisurf.core.data` imports it) and was taken at 22:39 after the build, from
HEAD sources only (`sections.py` unmodified). Both baselines already include the core fit fix `8e2c1f892`.

## 2. Science: a bias in the shared estimator (fixed in core, `8e2c1f892`)

On the demo measurement (2 kHz green / 1 kHz red background + 200 bursts, 20 s) the tool reported 2.41 / 1.64 kHz. An exact
tail estimate of the same photons gives 2.00 / 1.02. Cause: the tail fit anchored its amplitude at dt = 0, started from the
histogram's first bin; for the 1.96–3.31 ms window the tool seeds, A and λ are almost collinear and L-BFGS-B stopped near its
start while reporting success. Now anchored at the window's first bin: 2.09 / 1.06. Guard
`test/plugins/burst/test_background_diagnostics.py::test_a_window_far_out_in_the_tail_recovers_the_rate` (1.34 before).

## 3. Parity checklist (`before_populated.png` vs `before_emtk_populated_*` → `after_populated_*`)

| Qt widget | Stream's emtk | Now |
|---|---|---|
| files from the workflow shell only (`_add_tttr_files`) | Open files / Add folder / MMFDB / Clear / Remove | kept (gained) |
| detectors: Qt DetectorWizardPage; with no saved setup its blank defaults (green, red and a **yellow placeholder with red's channels**, which estimates 0 and warns) | emtk channel editor, green [0,8] / red [1,9] | unchanged — deliberate: no placeholder detector, same green/red rates |
| estimate synchronous | worker | worker, 10 Hz frames while running |
| — | file dialog over the whole viewport | sized dialog, per-action title/filter |
| — | folder drop added the `.pto` container beside the photons too (one measurement read twice) | container skipped |
| — | status shown twice | once |
| workflow API `tttr_files`, `_add_tttr_files`, `detector_wizard_page` | on the Qt widget | unchanged (Qt widget, used by the burst_analysis shell) |

Shared drawing (both hosts), fixed: "Series" legend entries for the unnamed fitted tails; "Fit from:"/"Fit to:" tags covering each
other (one range tag); numeric x axis under the rate bars (detector names); 🌑 on Estimate drawn as a white disc (removed). Guide
targets `files`, `bg_channels`, `bg_run`, `bg_rate_plot` were never drawn in emtk (written for the Qt AutoForm keys); now
remembered, the Run step waits for Estimate.

## 4. Automated evidence

```
after: 28 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/burst_background
compare: exit=0   (lost [] / stale_explanations [] / untooltipped [];  the Qt side inventories 1 control: one canvas)
```

## 5. Deliberate differences

None in `compare.json`. Behaviour: default detectors green/red without the Qt page's yellow placeholder; estimate on a worker;
own file inputs (gained).

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/burst_background -q -p no:cacheprovider
26 passed in 30.58s
$ python -m pytest test/plugins/burst/test_background_diagnostics.py ... (11 background-related files)
212 passed
```

`test/demo_data.py`: SPC-130, 12.5 ns ticks, known background. `test_emtk_background_parity.py` (13): rates equal the Qt widget's
(subprocess) and the known background within 10 %, same fit window; Open TTTR files and Estimate pressed where drawn (pixel
painter), the Run step's await released, results by frames alone; folder drop without the container; frames while estimating;
per-action dialogs; remove / clear / setup save-load / invalid detectors; an unreadable file reported; every guide target drawn;
draws at both sizes (no "Series", one window tag, named bars, status once); Qt-free; tooltips; the Qt workflow API.

Deliberate breakage, round 1: container dedupe removed → drop test failed; fitted tails named "Series" again → draws test failed.
Round 2: bar tick labels removed → draws test failed; `bg_run` not remembered → guide-target test failed. All restored.
(Measurement trap: `-k "... and 1200"` selects nothing for a test parametrised as `size0`; the first try printed no result.)

## 7. Screenshots read

`before_populated.png` (Qt: yellow placeholder, warning), `before_emtk_populated_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_*`.

## 9. Persistence, guide, help, docs

Window geometry (manifest) on the Qt side, host's in emtk; detector setups through the shared setup store (emtk editor).
Guide: shared `gui/guide.json`, targets now drawn. Docs: none edited (the estimator's documented method is unchanged; the fix
removes a bias).

## 10. Blocked / open

* The Qt DetectorWizardPage's blank default carries a "yellow" detector with red's channels (a .ui placeholder) — Qt legacy,
  not changed.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
