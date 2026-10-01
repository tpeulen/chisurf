# emtk port report — `tttr_lut_tools` (upgrade of the existing emtk app)

Implementing agent (Sonnet), 2026-10-01; the agent could not write this file, so the reviewer saved its essentials and appended the review.
Commits: `3920e0c5e` Qt baseline and pre-upgrade files, `a0db448fd` emtk app at parity, `a2263cb32` help text and guide target, `32e91085e` evidence and log. Board `T-20261001-LUT`.

## What changed
* New Qt-free `gui/model.py` (`LutToolModel` over the earlier `LutWorkspace`), `gui/lut_tools_emtk.view.json` drawn by `emtk.view_form` (file, LUT and channel lists are `data_table`s,
  the channel table has an editable Show column), rewritten `gui/app.py` (the two plots, JSON window, file dialogs, `SnapshotJob` for slow work), `gui/guide.json` (7 steps, 3 await),
  `gui/help.md`, 40 new tests. The empty state now draws both plots with the Qt titles and axes (it was a text prompt).
* Raw TAC plot: draggable plateau region (`implot.drag_rect`), offset and threshold lines; corrected preview cached until an input changes.
* Numbers equal the real `TTRLutToolsWidget` for the same file (`BH_SPC132.spc` copy): raw and corrected curves, spin boxes, info line, LUTs of channels 0/1/8/9, the saved LUT,
  the exported corrected file (56499 values); region [1200, 1900) gives f=0.919861, n_mean=14.18; Add all channels equals the Qt bridge; tab-2 histograms equal `open_tttr` with the LUTs.
* Deliberate (36 entries, all explained): tab-2 widgets and the collapsed Advanced labels are not in the default drawn state, reading-routine items, row-number headers, `?` is Help;
  right-click Remove LUT is a button plus Delete; JSON preview shows 60 lines (Copy copies all); auto-detect failure is reported (Qt is silent); Qt applies the setup on close, emtk has an explicit
  "Apply to detector setup" button (only when a setup opened the tool); new strings are untranslated.

## Evidence and tests
```
compare: exit 0 / lost [] / untooltipped []   qt-free True   after: 63 controls
pytest chisurf/plugins/tttr/tttr_lut_tools: 63 passed   (23 existing, 3 updated for the new model, plus 40)
```
Breakage check by the agent (unthresholded raw plot, channel 8 dropped from Add all): 5 failed, restored. Hermetic: temporary settings and MMFDB, no network.

## Open
Below about 600 px the Add all channels button clips; `drag_rect` has no whole-body drag; the sample file is a fluorescence decay, not a real flat-light file (every code path is exercised, no
real uniform-illumination file in `test/data`); the docs guide `37_tttr_microtime_lut.md` still shows the Qt tool. Qt auto-detect fails silently on channels 0/1/9 of the sample (only ch 8 has a plateau).

## Review (reviewer, 2026-10-01)
Re-run by the reviewer: 63 passed; `compare` exit 0, lost []; no Qt imports in `gui/app.py` / `gui/model.py`. The populated 1200x800 screenshot shows both plots with the orange region,
parameter fields, status "ch 0 | Range [1200, 1900) | width=700 | f=0.919861 | n_mean=14.18" and "Loaded 1 file(s): channel(s) 0, 1, 8, 9", matching the Qt baseline's layout and numbers.
**Accepted.** `tttr_lut_tools` is removed from `emtk_preview.json`.
