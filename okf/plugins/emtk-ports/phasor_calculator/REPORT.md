# emtk port report — `phasor_calculator` (upgrade, audit-all row 33)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `phasor_calculator` / `chisurf/plugins/calculator/phasor_calculator` |
| Port type | A (view port): the committed Qt `PhasorCalculatorTool` rendered `phasor.view.json` with AutoForm over an inline model; the stream moved the model unchanged to `gui/model.py`, wrote an emtk app (hand-drawn controls, docks, a τ/g/s table, the plot) and made the Qt window host it |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `d74a0a821` baseline; `f55fad3e1` emtk app at parity with the Qt tool; `545baaece` guide 77; evidence commit "phasor_calculator: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `gui/guide.json` (last step targets the plot), `gui/tool.py` (hosts the emtk app),
`manifest.json` (emtk entrypoint); untracked `gui/app.py`, `gui/model.py`, `tests/test_emtk_app.py`. All committed with the app.
`model.py` equals HEAD's inline `_PhasorCalcModel` line for line.

## 2. Parity checklist (`before_populated*.png` (Qt HEAD, both tabs) vs `before_emtk_populated_*` → `after_*`)

| Qt (HEAD) | Stream's emtk | Now |
|---|---|---|
| spec fields, flowed two per row (each (g, s) pair split) | hand-drawn, grouped in four collapsible sections the spec lacked | the groups are in the spec (sub-panels, three folded); the form is drawn from it; descriptions are the tooltips |
| Results panel (HTML table, folded) | τ/g/s table in its own dock | same (the emtk rendering of Results) |
| Phasor plot tab: no legend, ticks labelled; aspect close to round | legend of ~30 contour items over the plot; unequal axes (ellipses) | short legend (the seven named references), equal scale |
| Guide unreachable (doc'd known defect), ? | Guide, Help | same; a guide step into a folded group unfolds it |
| geometry: shared `build_overlays` | same | same, equal to the model's overlays |

## 4. Automated evidence

```
after: 53 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/phasor_calculator
compare: exit=0   (lost [] / stale [] / untooltipped [];  the HEAD Qt side inventories 0: AutoForm widgets)
```

## 5. Deliberate differences

None in `compare.json`. Layout: three docks instead of two tabs; equal-scale plot (the y range then spans the dock's height);
the spec's groups now also define the order.

## 6. Tests

```
$ python -m pytest chisurf/plugins/calculator/phasor_calculator -q -p no:cacheprovider
22 passed in 13.34s
```

`test_emtk_phasor_parity.py` (11): overlays and results equal the Qt window's model (subprocess; it hosts this app on that
model), the τ table against g = 1/(1+(ωτ)²), s = ωτ/(1+(ωτ)²); every spec field drawn with its description; groups folded as
declared; a form edit reaching the table; equal scale and a legend without contour items; draws at both sizes; every guide target
reachable; Qt-free; tooltips.

Deliberate breakage, round 1: legend filter off → plot test failed; equal-scale flag removed → plot test failed. Round 2: the
unfold-on-step removed → guide test failed; the spec form not drawn → description test failed. All restored.

## 7. Screenshots read

`before_populated.png`, `before_populated_plot_tab.png` (Qt HEAD), `before_emtk_populated_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, guide figures `docs/guides/figures/phasor_calculator*.png`.

## 9. Persistence, guide, help, docs

Dock layout via `native_layouts`; window geometry (manifest). Guide/help shared. Docs: guide 77 rewritten for the window and its
figures regenerated (`545baaece`; another agent's uncommitted tag edit in that file left alone).

## 10. Blocked / open

* No readout for the mixture point or the cursor centre (kept in guide 77's known defects).

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
