# emtk port report — `fcs-lfcs-sim` (swap-candidate, audit-all row 24)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `fcs-lfcs-sim` / `chisurf/plugins/fcs/fcs_lfcs_sim` |
| Port type | A (view port): the Qt `LifetimeFcsSimWidget` = strip (Simulate + Correlate, Guide, ?) + AutoForm over `lfcs_sim.view.json` + chiplot correlation plot; the emtk app draws the same spec and plot |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `f4a8e2119` baseline; `50f9b6f6d` emtk app at parity with the Qt tool; evidence commit "fcs-lfcs-sim: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `manifest.json` (emtk entrypoint); untracked `app.py`, `strings.py`,
`test/test_native.py`, `test/capture_native.py`, `test/capture_qt.py`, `test/renders/`. Committed: manifest, app (rewritten),
strings, test_native. Left untracked: the two capture scripts and `renders/qt-populated.png` — they draw invented curves with
the old status wording and need PIL; `scripts/capture_populated.py` here replaces them.

## 2. Parity checklist (`before_populated.png` → `after_populated_*`)

| Qt widget | Stream's emtk app | Now |
|---|---|---|
| Form from `lfcs_sim.view.json`: two folding panels + Run panel (status) | seven hand-drawn input fields, no spec | the spec via `draw_form`, panels fold; the Run panel's custom section (`lfcs_sim_controls`) is the status line |
| Strip: green Simulate + Correlate, Guide, ? | button in the form; no Guide, no help | same strip |
| Plot right of a ≤320 px form | plot under the form, 300 px | form dock left (30 %), plot dock right |
| log lag axis, "lag time (ms)" / "G(τ)", legend, grid | **linear** lag axis: every curve flattened at 0..1 (`before_emtk_populated_*`), no labels | log axis, labels, legend (NE) |
| pens: species 1 #1f77b4, species 2 #d62728, cross #2ca02c | implot's cycle | the Qt pens |
| status "3 species correlation(s); filter condition number 3.3." | other wording | the Qt wording (`model.status()`, used by both) |
| error: modal "Simulation failed" dialog | type: message | "Simulation failed: …" in the status line |
| run blocks the UI (~7 s at 400 k photons) | blocked inside the button | worker thread; form and button disabled meanwhile, frames at 10 Hz |
| model in `gui/tool.py` | copied into `app.py` | `model.py`, imported by both |

## 4. Automated evidence

```
after: 40 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/fcs-lfcs-sim
compare: exit=0   (lost [] / stale_explanations [] / untooltipped [])
```

## 5. Deliberate differences

None in `compare.json`. Behaviour: the simulation no longer blocks; the failure is stated in the window, not a modal dialog;
the form/plot split is a draggable dock divider rather than a fixed 320 px column.

## 6. Tests

```
$ python -m pytest chisurf/plugins/fcs/fcs_lfcs_sim -q -p no:cacheprovider
19 passed in 34.81s
```

`test_emtk_lfcs_parity.py` (14): the Qt widget's own button slot (`_LfcsSimControls._on_click`, subprocess) and the emtk app
give the same curves (names, species pairs, x, y) and status for 60 k photons with exchange; the model equals the committed Qt
model's run written out with the core calls; the pens equal the Qt hex colours; the lag axis is log10; a second press while
running is ignored; a failure is stated; spec fields bind model attributes with descriptions; draws empty and populated at
1200×800 and 800×600; the drawn button pressed with the pixel painter runs and releases the guide step's await; every guide
target is drawn; Qt-free; tooltips.

Deliberate breakage, round 1: cross pen changed → colours test failed; log scale removed → log-axis test failed. Round 2:
`n_bins` 8→6 in the model → the reference test failed (the Qt-subprocess test passed: both hosts share the model now, which is
why the written-out reference exists); running guard removed → **passed at first** (the second job only queued), so the test
now counts runs after the worker settles → failed (`[1, 1] == [1]`). All restored.

## 7. Screenshots read

`before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png` (stream's: linear axis), `after_populated_{1200x800,
800x600}.png`, `after_*`. Same curves as the Qt grab; nothing clipped (the status wraps at 800 px).

## 9. Persistence, guide, help, docs

No statefulness on either side. Guide/help: the shared `gui/guide.json` / `gui/help.md`. Docs: behaviour unchanged, none edited.

## 10. Blocked / open

none.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
