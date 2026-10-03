# Batch analysis — one template fit, many datasets

Runs one **pre-optimised template fit** over many datasets or files and collects
every parameter in one table. Each item starts from the template's parameter
values and fixed flags, so the results are directly comparable.

## Before you start

1. Load a representative dataset and create the fit you want to use.
2. **Optimise it by hand** — its values seed every run. A template far from some
   samples' optimum leaves those fits in a local minimum with no warning.
3. Keep to one experiment type per batch; one template cannot fit both TCSPC
   decays and FCS curves.

## The steps

The list on the left shows the five steps; a check mark means the step needs
nothing more from you. Click a step, or use **Back** and **Next**; **Finish**
(last step) closes the window.

- **Loaded data** — tick datasets already loaded in ChiSurf (optional). Hover a
  row for its file; **Refresh** re-scans the loaded datasets.
- **Files & fit** — **Files**, **Folder** (everything below it) and
  **Database** add files, and you can drop files or folders on the window;
  select a row and press **Remove** (or Delete) to drop it, **Clear** empties
  the list. Choose the **Template fit**. Loaded datasets run first, then files.
- **Run** — choose **Results CSV** (type a path or **Browse...**) and press
  **Run batch**. Each item is restored to the template, fitted and its curves
  exported; the bar shows `i/total: name`. Without a CSV path, **Run batch** asks
  for one first.
- **Results** — one row per item and parameter: Run, Filename, Parameter, Fixed,
  Value, Chi2r. Sort by a header, type in the filter box to narrow the rows.

## What is written

Beside `results.csv`: `results.docx` (the table, and a picture of each fit when
the host can capture one; needs python-docx, the window says when it is missing) and `results_fit_results.zip` (each run's curve export). Pivot the
CSV on **Parameter** for one row per sample, and filter **Fixed = No** for the
free parameters. Scan **Chi2r** first: a jump flags a sample the template does
not describe.

## Further reading

- [Model comparison and batch fits](docs/guides/78_model_comparison_and_batch.md)
  — this wizard on real decays, the outputs, and the headless runner.
- [Parameter uncertainty](docs/concepts/parameter_uncertainty.md) — a spread
  across samples measured rather than assumed.
