---
name: report-results
description: >-
  Turn finished fits into something the user can keep: a saved project, a CSV
  table, plots, or a written summary. Use when the user asks to save, export,
  plot, write up or summarise results.
triggers:
  - export
  - save
  - csv
  - table
  - plot
  - figure
  - report
  - write up
  - summarise
  - summarize
  - results
tools:
  - export_fit_results
  - save_project
  - plot_fit
  - fit_report
  - write_file
---

# Delivering results

## Pick the right artefact

* **`save_project`** — the whole session (data, fits, parameters) in one file
  the user can reopen in ChiSurf. This is what to produce when they will
  continue working.
* **`export_fit_results`** — a CSV with one row per fit: every parameter plus
  the reduced chi-square. This is the deliverable after a batch.
* **`plot_fit`** — a PNG of data, fit and weighted residuals. Produce one
  whenever a fit is being presented as a result; a reader judges a fit by its
  residuals, not by a number.
* **`write_file`** — a short markdown summary, or a script that reproduces
  the analysis.

Ask before overwriting a file that exists, and put outputs next to the data
unless the user says otherwise.

## Writing the summary

State what was measured, what model was used, and what came out, in that
order. Then:

* Give **uncertainties** with every fitted value. A lifetime of 4.19 ns means
  nothing without ± 0.004.
* Give the **reduced chi-square** and say whether it is acceptable. Never
  present a number from a fit you have not judged.
* Name the **assumptions**: which parameters were fixed, which IRF was paired
  with which sample, which measurements were excluded and why.
* Keep it short. A scientist reading a summary wants the numbers and the
  caveats, not a description of which buttons were pressed.

## Honesty rules

Report the fit you actually got. If chi-square is poor, say so in the summary
rather than burying it — a bad fit that is labelled as such is useful, and one
presented as a result is not. If you excluded a measurement, it goes in the
report, not just in your reasoning.
