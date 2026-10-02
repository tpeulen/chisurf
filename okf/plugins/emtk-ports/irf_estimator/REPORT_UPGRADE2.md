# irf_estimator: layout, real-input and docs upgrade (T-20261002-EMTKUP5)

Builds on REPORT.md (parity, EMTK-1D). Qt baseline: `before_populated.png` (unchanged tool). Emtk before: `before_layout_*.png` (= the accepted `after_populated_*`); after: `layout_*.png` (idle, loaded, estimated with range, auto-update, file dialog, guide, help; script `scripts/capture_layout.py`). All read at full size.

## Defects found and fixed
- Parameter fields were stretched across the dock and had no spin arrows (Qt spin boxes do) -> spin fields, one caption column (`LabelColumn`), capped width.
- Pictograms touched their captions on every button and toggle -> two spaces.
- Idle plot: log axis from 1e-4 to 1 -> 0-1000 ns, 1-1000 counts.
- Found by the click test: nothing wrong with the controls themselves; the edges of the green range region drag (fields follow), its body does not (emtk gap, strict xfail).

## Control -> test (test_emtk_irf_estimator_clicks.py, 28 incl. 2 xfail; layout 11 cases; parity 17 unchanged apart from captions)
Guide/Help/Next/Prev/Close; Load Decay dialog (filter, empty Open, Cancel, x, select+Open); drop of a decay and of a foreign file (error line); Time/Channel typed + clamped; SG Window, Poly Order, RL Iterations, Regularization, Manual Background: typed, clamped to the Qt ranges, arrows, wheel; Use Range Selection shows/hides the channel fields; First/Last channel typed and bounded; range region edges dragged in the plot (left and right); Estimate on the worker (greyed parameters while it runs, results, curve names); Auto-Update re-estimates; Save IRF (dialog ways out, typed name, VV file read back); Transfer (sink gets the VV/VH group); Load from Dataset (list, choice, Load selected); crosshair text and wheel zoom; idle state greyed; real ~/.chisurf untouched; Qt-free. Layout at both sizes: every control inside the dock and window, one caption column, short fields, no overlapping texts, pictograms clear, plot >= 60 % of the width with axes and legend, results complete, idle state.

## Gaps
- strict xfail: tour card `Close Tour` dead on step 2 (card over a field; shared gap, emtk_gaps_repro.py #3).
- strict xfail (emtk): implot `drag_rect` moves by edges and corners only; Qt's `LinearRegionItem` also moves as a whole.

## Deliberate breakage (13 mutations, two rounds)
Round 1: 12 of 13 caught; missed "crosshair text dropped" (equivalent: the same text is also drawn in the results window). Round 2 (12 mutations): 12/12 caught. Folder tests: 66 passed, 2 xfailed (compare exit 0, 0 lost). Mutations (spin arrows, label column, auto-update, drop, range edge drag, RL maximum, dataset load, transfer sink, icon spacing, estimate enabled without data, crosshair, results, swallowed errors).

## Reuse
Shared: `draw_form` spec forms, `emtk_layout` (`LabelColumn`, `layout_spec`), `FileDialog`/`DialogWindow`, help/tour; the estimator core. No local duplicates found.

## Docs
`docs/guides/irf_estimation.md`: figure `irf_estimator.png` regenerated from the emtk app on the simulated decay of the guide (script `scripts/capture_docs_figure.py`), caption corrected (fitted lifetime 3.6 ns vs true 4.0), range-drag sentence.
