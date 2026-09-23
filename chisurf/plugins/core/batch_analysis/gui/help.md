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

- **Loaded data** — tick datasets already loaded in ChiSurf (optional).
- **Files & fit** — add files or a folder, and choose the **Template fit**.
  Loaded datasets run first, then files.
- **Run** — choose **Results CSV** and press **▶️ Run batch**. Each item is
  restored to the template, fitted, its curves exported and its fit window
  captured.
- **Results** — one row per item and parameter: Run, Filename, Parameter, Fixed,
  Value, Chi2r.

## What is written

Beside `results.csv`: `results.docx` (screenshots and the table; needs
python-docx) and `results_fit_results.zip` (each run's curve export). Pivot the
CSV on **Parameter** for one row per sample, and filter **Fixed = No** for the
free parameters. Scan **Chi2r** first: a jump flags a sample the template does
not describe.

## Further reading

- [Model comparison and batch fits](docs/guides/78_model_comparison_and_batch.md)
  — this wizard on real decays, the outputs, and the headless runner.
- [Parameter uncertainty](docs/concepts/parameter_uncertainty.md) — a spread
  across samples measured rather than assumed.
