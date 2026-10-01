# emtk port report — `burst_gs` (upgrade, audit-all row 30)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_gs` / `chisurf/plugins/burst/burst_gs` |
| Port type | B (run port): the Qt `BurstGsTool` draws `BurstGsApp` in a `ControlHost`, fits through ChiSurfProgress and reports in its status bar; the emtk app fits with the stream's `BurstGsController` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `6c499df76` baseline; `d4972bba0` emtk app at parity with the Qt tool; evidence commit "burst_gs: evidence and report" |
| Board | `T-20261001-EMTK1B` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `gui/app.py` (docks, report tables, the remaining parameters, emtk help/guide),
`manifest.json` (emtk entrypoint); untracked `gui/controller.py`, `test/test_native.py`. All committed with the app.

## 2. Parity checklist (Qt run → emtk run; `before_populated.png` vs `before_emtk_populated_*` → `after_*`)

| Qt `BurstGsTool` | Stream's controller | Now |
|---|---|---|
| fit off the UI thread, progress fraction + message, Cancel | worker; fraction dropped | progress bar with the optimiser's message; Stop |
| after a fit: "logL = …, k(1→2) = … /s, k(2→1) = … /s" | "Kinetics fit completed." | Qt line |
| no result: "The fit did not produce a result — see the report."; failure "The fit failed: …" | report text / "Error: …" | Qt messages |
| Export CSV: "Run a fit first." before a fit; suggests `<first table>.gs.csv` | always; `kinetics.csv` | Qt behaviour |
| drop: `.bur` paths added | `.bur` paths and folders (gained) | same, and says when nothing was added |
| — | one full-viewport chooser | sized dialog per action |
| — | continuous rendering | 10 Hz while fitting |

Shared drawing, fixed: the kinetics plot ("Parameter / Time" vs "Rate / Likelihood", numeric x, a draggable "Rate: 1000 s⁻¹"
line and a region drop target that fed nothing — `threshold_y`/`_last_dropped_region` were never read) is now one named bar per
transition k(i→j) (= `K[j, i]`, as the Qt status line reads the matrix), the simulated rates as markers in simulation mode, y room
above both (limits applied on change — see burst_fusion's emtk COND_ONCE issue); with the transition-time scan, the model's
scan series with real labels. HEAD's Qt plot was a placeholder "Expected Exchange Profile". Guide: only `guide`/`help` were drawn
targets of nine steps and nothing waited; now every target is recorded (spec-style attribute names, `Fit`, `Rates`, `bur_files`)
and the Simulate and Fit steps wait.

## 4. Automated evidence

```
after: 68 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/burst_gs
compare: exit=0   (lost [] / stale [] / untooltipped [];  the Qt side inventories 0 controls: one canvas)
```

## 5. Deliberate differences

None in `compare.json`. Behaviour: progress bar in the window instead of a modal dialog; status line in the controls pane instead
of the status bar; folder drops (gained).

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/burst_gs -q -p no:cacheprovider
40 passed in 43.62s
```

`test_emtk_gs_parity.py` (13), on the tool's own simulation (k 3000 / 1000 /s, E 0.25 / 0.75): the same rate matrix, logL, status
line and report as the Qt tool (subprocess), both rates within 15 % of the simulated ones (2879 / 1017); the rates plot's labels,
truth markers and drawn y range; progress and frames while fitting, stop; errors, no result, failure; export refused before a fit,
the Qt file name after; drops; every guide target drawn; the Simulate and Fit awaits released by pointer presses; draws at both
sizes; Qt-free; tooltips.

Deliberate breakage, round 1: the old "Kinetics fit completed." → status test failed; `K[i, j]` instead of `K[j, i]` → rates-plot
test failed. Round 2: export guard removed → errors test failed; Fit press not tracked → await test failed. All restored.

## 7. Screenshots read

`before_populated.png` (Qt HEAD: placeholder plot), `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,
800x600}.png`, `after_*`.

## 9. Persistence, guide, help, docs

Window geometry (Qt) / host's; no settings persisted by either. Guide content unchanged, now walkable. Docs: none.

## 10. Blocked / open

none.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
