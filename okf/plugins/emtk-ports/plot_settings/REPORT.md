# emtk port report — `plot_settings` (settings plugin upgrade)

Upgrade of the earlier stream's deficient emtk app (one long list with all sections open, hex text for colours, an empty Preview header) by
the implementing agent (Sonnet), 2026-10-01; the agent could not write this file, so the reviewer saved its essentials and appended the
review. Commits: `2f2567bb1` Qt baseline with `pre-upgrade/`, `a792e9518` emtk app at parity (with the earlier stream's lazy
`gui/__init__.py`, manifest, `tool.py` node-graph section, `strings.py`, `translations.py`), `b25a1fce7` Apply / Save / Reset bar in its own docked
window (workaround for an emtk hit-testing gap, below), `448c4a44c` evidence. Board entry `T-20261001-PS`.

## What changed

* `gui/model.py` (new, Qt-free `PlotSettingsModel`): the 31 settings with the Qt defaults and ranges, loaded and collected in the Qt `gui.plot`
  layout; edits are pending (`dirty`) until Apply; `apply()` writes the live settings and refreshes open node graphs; `save()` applies and writes
  `settings_chisurf.yaml` (creating it when missing; failures go to the status line); `reset()` reloads; `preview_series()` returns the Qt sample curves.
* `gui/plot_settings_emtk.view.json`: five collapsible panels in the Qt fold state (Rendering Backend and Colors open, the rest folded), six
  `kind: color` fields (swatch, editable hex, picker), the sliders and spins with the Qt ranges, the backend choice with its hint.
* `gui/app.py` rewritten as three docked windows: the settings form (Help, Guide), an "Apply / Save / Reset" bar with a status line, and
  "Preview (sample curves)": an `emtk.implot` plot of data / model (dashed) / IRF with log y, the chosen colours and widths, grid, labels, legend and
  background, following pending edits live. The preview shows styling with sample curves, not analysis data.
* Guide of 6 steps with awaits, help rewritten. The old app offered a non-existent `matplotlib` backend and wrote region alpha and the
  transparencies at the wrong level of `gui.plot`; both are corrected.
* **Deliberate differences:** edits are **pending until Apply** (the Qt tool applied every edit live; Reset therefore drops unapplied edits);
  the preview is an always-visible window (in Qt it scrolls out of view when sections are open); Save creates a missing settings file (Qt showed a
  "Save failed" dialog); 24 `deliberate.json` entries are inventory artefacts (21 labels inside sections that start folded, the Qt hex label that never
  updates after load, a slider readout, `?`, the Qt `preview` header).

## Evidence and tests

```
$ python -m pytest chisurf/plugins/core/plot_settings -q -p no:cacheprovider
54 passed in 40.84s        (re-run by the reviewer; 16 existing + 38 new)
compare: exit 0 / lost [] / stale_explanations [] / explained 24 / untooltipped []   qt-free True      after: 63 controls
```

38 new hermetic tests (temporary settings folder, a private copy of `gui.plot`; Save verified by reading the temporary `settings_chisurf.yaml`):
model defaults, ranges and backend choices equal to the Qt widget's; `collect()` equals the Qt `_collect_settings()`; the fold state equals the Qt boxes;
pointer clicks drive swatches, folds and Apply / Save / Reset; the preview colours in the submitted series and in the drawn pixels; clamping; both
sizes and a narrow 420x700; a click on Apply does not toggle a scrolled-out checkbox; guide and help. Deliberate breakage (data series coloured with
the model colour; `apply()` leaving the dirty baseline stale) failed 7 tests; restored. The real `~/.chisurf` settings file is untouched by the run.

## emtk gap found (worked around, then fixed by the reviewer)

A scrolling `begin_child` did not clip hit-testing: rows scrolled out of the child still took clicks at their hidden position (a click on Apply toggled
the hidden "Grid on data panel" checkbox). The agent worked around it with the separate Apply window; the reviewer fixed the root cause in emtk (see
the log). No docs guide page exists for this plugin.

## Review (reviewer, 2026-10-01)

Verified, not taken from the hand-over: 54 tests pass; `compare` exit 0 with `lost` `[]`; no Qt imports in `gui/app.py` / `gui/model.py`; the real settings
file and database are untouched; the populated screenshot read next to `before_populated_colour_changed.png`: same sections, colour swatches with hex
text, and the preview following a changed colour (green data, cyan model) with the same legend, log axis and labels. **Accepted.** `plot_settings` is
removed from `emtk_preview.json`: its emtk window is now the default. The one behaviour change to know about is pending-until-Apply edits.
