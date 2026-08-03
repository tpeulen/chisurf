---
type: Reference
title: Use case — batch analysis (apply one template fit to many files)
description: Optimise one representative fit, then apply it to a list of datasets/files in one pass and export the consolidated CSV/DOCX/ZIP.
tags: [usecase, batch, fitting, tcspc, wizard, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: batch analysis — one template fit over many files

**Goal:** the user has fitted **one** representative measurement by hand and now
wants the same model, the same fixed/free flags and the same starting values
applied to a whole measurement series — a titration, a time course, a mutant
panel — with the per-file parameters and χ²ᵣ landing in one table they can plot.

**Data:** `test/data/tcspc/ibh_sample/Decay_577D.txt` (template, donor-only) and
`test/data/tcspc/ibh_sample/Decay_577D+577A+GTPgS.txt` (a second measurement of
the same family), IBH text format, `dt = 0.0141` ns/ch, 10 MHz.

## Steps

1. Load the representative decay and create a fit for it — see
   [TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md) steps 1–8. **Optimise it
   by hand**: the template's parameter values seed every batch item.
2. Open **Tools ▸ Batch-Analysis** (`BatchProcessingWizard`). The wizard has five
   steps in a left-hand nav: *Welcome*, *Loaded data*, *Files & fit*, *Run*,
   *Results*.
3. **Loaded data** — tick the already-loaded datasets to include (optional).
   **Refresh** re-scans ChiSurf's dataset list.
4. **Files & fit** — drag the remaining measurement files onto *Files to
   process* (or **Files** / **Folder** / **Database**), then pick the template in
   the **Template fit** combo.
5. **Run** — check the *Ready to run* summary (datasets / files / template fit),
   type or pick the **Results CSV** destination, then click **▶️ Run batch**.
   Each item is restored to the template parameters, assigned to the fit, fitted,
   and exported.
6. **Results** — read the per-parameter table; the CSV, the DOCX report and the
   ZIP of per-run numeric exports are written next to the chosen CSV path.

## Expected

- Step 5 processes both items in ~1–3 s with a progress dialog, then a *Batch
  complete* dialog listing every file written.
- The CSV has one row per (item, parameter) with `Run, Filename, Parameter,
  Fixed, Value, Chi2r`; here 23 parameters × 2 items = 46 rows, χ²ᵣ ≈ 5.22 for
  the donor-only template item and ≈ 57.4 for the D+A file (the donor-only model
  does not describe it — exactly the signal a batch is meant to surface).
- Re-running the same batch on the same inputs reproduces the same numbers.
- The template fit is left as the user optimised it.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through the real main
window and the real wizard: experiment/reader combos, `macros.add_dataset`,
`onAddFit`, `FittingControllerWidget.onRunFit`, then `BatchProcessingWizard` with
the nav list, the `LoadedDatasetSelector` check boxes, the `path_list` drag-drop
handler, the *Results CSV* line edit and the **Run batch** button. Screenshots at
every step, inspected.

**The batch itself works and is fast.** Two items fitted in 1.3 s; CSV (46 rows)
and the per-run export ZIP (534 kB, `_model` / `_IRF` / `_weighted residuals` /
`_autocorrelation` curves per item) were written; the completion dialog listed
both. The parameter restore-before-each-item is real: item 2 started from the
template's `tL1 = 4.226` and converged to 3.459.

**But the run consumes the template.** After the batch, fit 0 is still bound to
the *last* item, holding its parameters and χ²ᵣ = 57.42 — the carefully optimised
template the whole feature is built around is gone, silently. The consequence is
measurable: an immediate, identical second run changed **all 62 compared rows**
(`sc` 0.0023354 → 0.0020860, χ²ᵣ 5.2186617 → 5.2186841 on item 1), because run 2
snapshotted the state run 1 left behind. Small here, unbounded for a stiffer
model. See RF-249.

**Two clicks from an unusable fit.** The *Loaded data* list offers the
auto-created `ExperimentDataGroup` container as item 1, right next to the real
curves — the view model tries to filter it out by the name `"Global Dataset"`,
which is not its name. Ticking it and running raises `AttributeError:
ExperimentDataGroup object has no attribute 'y'`, aborts with *Batch failed*,
writes no CSV, and leaves the fit bound to the container so every later `chi2r`
read raises `ValueError: not enough values to unpack (expected 4, got 0)`. The
fit has to be deleted and rebuilt. Same leak as RF-015 in the IRF picker.
See RF-250.

**Pressing Enter walks the wizard backwards.** Typing the CSV path into *Results
CSV* and hitting Return jumps from *Run* to *Files & fit* — `‹ Back` is the
dialog's default button. Isolated in a 20-line repro with no data loaded
(index 3 → 2 on `Key_Return`); it affects every AutoForm wizard hosted in a
`QDialog`. See RF-251.

**The results are unreadable in the GUI.** The *Results* step renders 46 rows
into a ~200 px box that does not grow: at 1000×720 exactly **one** row is
visible, at 1400×1000 **two**, with ~700 px of dead space underneath. The
filename column repeats the full absolute path and wraps it over two lines, and
values print at 17 significant digits, wrapped mid-number (`5.` / newline /
`218661736149051`). The CSV is the only practical way to read the output.
See RF-253.

**The wizard's ✓ marks are noise:** on first open, with nothing loaded and
nothing run, four of five steps already show ✓ — including *Results*, whose own
panel says "No results yet". See RF-252.

**After a failure the panel still says "Done."** — the failed run above left the
previous run's green **Done.** header and its stale table on the *Results* step.
See RF-254.

No DOCX was produced (the arm64 env used here has no `python-docx`, which *is* a
declared dependency), and nothing said so: the completion dialog simply omitted
the DOCX line — `write_docx`'s reason string is discarded at the call site.
See RF-256.

Screenshots: `01_welcome`, `03_loaded_data_ticked`, `04_files_and_fit`,
`05_run_before`, `07_results`, `10_results_big_window` (scratch dir, not
committed). The run coincided with a concurrent edit of
`chisurf/gui/plots/lineplot/lineplot.py` by another instance, which briefly broke
`import chisurf.gui.plots` and blanked the fit window / truncated the model
combo; that is transient working-tree state, **not** a finding.

## UX / UI suggestions

- **Say what the batch will do to the template fit** — and offer "restore the
  template fit afterwards" (ideally: run on a clone). Today the wizard promises
  "each item starts from the same initial guess" and then quietly redefines that
  guess for the next run.
- **The template combo shows `Lifetime  - ExperimentDataCurveGroup`** — the model
  name (with a stray double space from the trailing blank in `"Lifetime "`) plus
  a class name. It should name the *dataset* the template was fitted to, which is
  the only thing that distinguishes two candidate templates.
- **Show the dataset list as basenames** with the directory as a tooltip, and add
  a per-row experiment-type/curve badge. Today every row is a full absolute path
  with an identical 45-character prefix, and the IRF (`Prompt.txt`) is offered as
  a fittable item with nothing to warn the user.
- **Add select-all / select-none** to the *Loaded data* list.
- **The empty *Files to process* box has no placeholder** — a 500 px black
  rectangle with no "drag files here" hint, although drag-drop is the intended
  primary gesture. The **Database** button is also unexplained.
- **Say which reader the files will be read with.** The runner loads batch files
  with `experiment_reader=None`, which falls back to whatever is selected in the
  main window's *Read data* dock — a hidden global that decides `dt`, `skiprows`
  and polarisation for the whole series (RF-255).
- **Offer a wide results layout** — one row per file, one column per parameter,
  with χ²ᵣ first. The long form is right for the CSV, wrong for the panel a human
  reads. Round the displayed values (4–6 significant digits).
- **Show progress that survives** — the progress dialog has no cancel button
  (`setCancelButton(None)`), so a 200-file batch cannot be stopped.
- **Re-running re-imports.** Each run adds every file to the dataset list again;
  after two runs of the same batch the same file is listed twice (RF-257).

## Bugs filed

- RF-249 — a batch run leaves the template fit bound to (and parameterised by)
  the last item, so an identical re-run gives different numbers.
- RF-250 — the auto-created `ExperimentDataGroup` is offered as a batch item and
  wrecks the fit when picked.
- RF-251 — Enter in any AutoForm wizard field triggers `‹ Back`.
- RF-252 — wizard steps with no `complete_when` always show ✓.
- RF-253 — the *Results* info panel does not expand; 2 of 46 rows visible.
- RF-254 — a failed run keeps the previous run's green "Done." status/results.
- RF-255 — `datasets_have_mixed_types` is never called; mixed-experiment batches
  are not rejected, and batch files are read with the Read-data dock's reader.
- RF-256 — the DOCX failure reason is discarded; the report goes missing silently.
- RF-257 — every run re-imports its files; duplicates accumulate in the dataset
  list.
