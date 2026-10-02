# emtk port report — `fcs_merger` (upgrade, audit-all row 51)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `fcs_merger` / `chisurf/plugins/fcs/fcs_merger` (Qt page: `chisurf/gui/widgets/wizard/fcs_merger/`) |
| Port type | A+B: the Qt `ChisurfWizard` around `WizardFcsMerger` (help toggle, folder field taking drops, clear, Target field and save, Use / File / CR A / CR B / Duration table, FCS and FCS Merged plots, Guide and ?) → a Qt-free `gui/model.py` and `gui/fcs_merger_emtk.view.json` drawn by emtk's `view_form` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `1b416dcec` baseline; `b65422a8b` the Qt page reads .cor count rates as the core does; `8207f1424` emtk app at parity; `85df4c555` the error line wraps; evidence commit "fcs_merger: evidence and report" |
| Board | `T-20261002-EMTK1D` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `manifest.json` (emtk entrypoint); untracked `gui/app.py` and
`test/test_emtk.py`, both committed with the app.

The data is real: `test/data/tttr/BH/132/BH_SPC132.spc` cut into six 10 s chunks, each cross-correlated over
channels 0+1 × 8+9 with tttrlib (`scripts/make_chunks.py`).

**A Qt defect, fixed on the way.** The Qt page had its own `.cor` reader. It split `count_rate * duration` over
the channels, a factor 2000 short of the kHz per-channel convention the core reader documents. As a result:
- every `.cor` folder showed 0.00 kHz in both rate columns (`before_populated.png`, HEAD page through a module
  overlay);
- it merged, and saved, 0.00075 kHz instead of 1.503 kHz.

The page now uses the core reader and the core writer (`b65422a8b`, guardrail `test_qt_cor_rates.py`, red on the
old page). `after_qt_populated.png` shows the real rates.

The stream's app had these gaps:
- it rendered every frame;
- its docks could be closed;
- its tour had no target lookup;
- the curve list was hand-drawn;
- errors were not red.

## 2. Parity checklist

| Qt page | Now |
|---|---|
| folder field: a dropped folder is read | Folder field (Enter reads it) + 📂 Open folder…; a dropped folder or one of its files reads that folder |
| table Use ✓ / File (stem; path tooltip) / CR A (kHz) / CR B (kHz) / Duration (s), `%.2f` | `data_table` with the same columns and values (units in the column tooltips), path as the row tooltip, unused rows dimmed |
| click Use toggles; double click toggles; click highlights | same; Delete removes a row from the list (the Qt `onRemoveRow` was never wired) |
| no row ticked → merge of all | same, with a note under the table |
| Target `<parent>/<folder>.cor` + save | Target (editable; Qt ignored edits) + 💾 Save, Save as…, 🚀 Add to ChiSurf (the Qt `add_to_chisurf` had no button) |
| FCS plot: palette colours, highlighted 3 px, unused grey dashed; FCS Merged | same pens; legend "Merge of n" |
| help (toggles an empty text box), clear (unconnected) | ❓ Help (the help page), 🧹 Clear (works) |
| Guide, ? | 📖 Guide, ❓ Help; tour on the folder field, table and save button; the folder step waits for a loaded folder, the save step for the button |
| — | worker thread for reading and saving, Stop, frames only while it runs, red error line |

## 3. Automated evidence

```
after: 37 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/fcs_merger
compare: exit=0
```

## 4. Deliberate differences

`deliberate.json`:
- the QWizard frame (Back / Next / Commit / Finish / Cancel, and the title "Correlation merging") around a single
  page;
- "?" is ❓ Help;
- the units moved from the rate and duration headers into their tooltips, so the five columns fit an 800 px window.

## 5. Tests

```
$ python -m pytest chisurf/plugins/fcs/fcs_merger -q -p no:cacheprovider
25 passed
```

`test_emtk_fcs_merger_parity.py` (11), against the Qt page in a subprocess on the real chunks:
- **Same state, same result:** the same rows (texts), file names, target name and target folder. Chunk 3 is left
  out by a pointer press on its Use check box, and the merge matches (x, y, ey at rtol 1e-12, count rate,
  duration 50 s). The saved file is **byte-identical**.
- **Table input:** a click highlights, a double click toggles, Delete removes.
- **Plot pens:** the highlighted curve is 3 px; unused curves are grey and dashed.
- **Nothing ticked:** the merge of all, with the note shown.
- **Errors:** a failed read keeps the list and shows a red line; a missing target is refused.
- **Buttons:** disabled until there are curves; disabled while the worker runs. No frames at rest, frames while a
  folder is read.
- **Actions:** Clear; a dropped chunk file reads its folder; Open folder, Save as, Add to ChiSurf; Enter in the
  folder field.
- **Guide:** every target is drawn. A typed path does not release the folder step; a loaded folder does; Save
  releases the last step.
- Help opens.
- Draws inside the window at both sizes.
- Qt-free, and tooltips on the inventory, sections, buttons and columns.

`test_qt_cor_rates.py` (1): the Qt page's rates and saved count rate. The stream's `test_emtk.py` is still green
on the new app.

## 6. Breakage check (14 faults, run twice: 14/14 caught both times)

The first runs missed "no frames while busy": the base `ImApp.animating()` is true before the first frames. The
test now draws first and asserts the app is at rest before it drops a folder.

The other faults:
- nothing ticked merges nothing;
- the File column shows the name, not the stem;
- rates not in kHz;
- the target inside the folder;
- unused rows not muted;
- a Use edit not rebuilt;
- a double click ignored;
- controls live while busy;
- the highlighted curve not thicker;
- unused curves not dashed;
- a typed folder releasing the tour step;
- the error line not drawn;
- a dropped file not reading its folder.

## 7. Screenshots read

- `before.png`, `before_populated.png` (HEAD Qt: 0.00 kHz);
- `before_emtk_populated_*` (stream);
- `after_qt_populated.png` (fixed Qt);
- `after_*` (empty);
- `after_populated_*` (chunk 3 dimmed, chunk 2 highlighted, merge of 5);
- `after_guide_*` (step 2 on the folder field);
- `after_error_*` (the wrapped red line).

Fixed on the way:
- cut table columns at 800 px (`fit_columns`, units moved to tooltips, a wider dock);
- the error line running off the dock (`85df4c555`).

The Qt page's own plots are a narrow strip beside the table (its layout); the emtk docks give them half the window
each.

Docs: guide 75 gains the standalone window's table, drop and target.
