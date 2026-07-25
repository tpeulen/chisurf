---
name: batch-fitting
description: >-
  Fit many measurements the same way and produce a comparable table of
  results. Use when the user asks to fit a whole folder, a series, all their
  samples, or to compare conditions.
triggers:
  - batch
  - all files
  - every file
  - whole folder
  - each file
  - series
  - all of them
  - compare
  - titration
tools:
  - list_files
  - load_data
  - create_fit
  - run_fit
  - set_parameter
  - export_fit_results
  - fit_report
---

# Fitting a series

The point of a batch is **comparability**: results only mean something
against each other if every measurement was fitted the same way.

## The procedure

1. **Get one fit right first.** Load a single representative measurement and
   fit it properly — including the instrument response and the number of
   components if it is a decay. That settled configuration is the template
   for the rest. Fitting twenty files with a model you have not validated
   produces twenty wrong numbers.
2. **Load the rest** with `load_data` on the directory. Exclude reference
   measurements (IRFs) from the list of things to fit.
3. **Create one fit per dataset** — `create_fit` does that by default — using
   the same model name.
4. **Apply the same configuration** to every fit: `set_parameter` takes
   `all_fits=true` for exactly this, and the IRF and component count must be
   set on each fit.
5. **Run them** with `run_fit` (no argument runs all of them).
6. **Check every one**, not just the first. The result of `run_fit` carries a
   per-fit assessment; list the ones that came out poor rather than reporting
   an average that hides them.
7. **Export** with `export_fit_results` to a CSV the user can open.

## What to fix, what to free

If a parameter is a property of the instrument or the sample family rather
than of the individual measurement — a background level, a colour-shift, an
IRF shift — consider fixing it to the value from the validated fit
(`set_parameter` with `fixed=true`). Fewer free parameters make a series far
more comparable, and it stops one noisy measurement from wandering off into a
different minimum.

## Reporting a series

Report the spread, not just the mean: a lifetime of 4.0 ± 0.1 ns across ten
samples is a different result from 4.0 ± 1.5 ns. Name the measurements that
did not fit well and say what is different about them. If the user is
comparing conditions, group the table by condition — the comparison is the
result they actually want.
