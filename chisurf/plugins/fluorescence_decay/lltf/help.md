# Lazy Lifetime Analysis

Fits **one** TCSPC decay with a sum of exponentials, reconvolved with a
measured IRF, and makes the choices around the fit by rule rather than by
hand. That is what "lazy" means — there is no special algorithm underneath.

Press **Guide** for the walk-through.

## What it decides for you

1. **Fit range** — from where the rise crosses `start_fraction` of the peak to
   where the counts reach `area` of the total (then back to the last channel
   with `count_threshold` counts).
2. **Background** — the mean of the last `average_window` channels, as a start.
3. **IRF shift** — a grid scan over `irf_time_shift_scan_range`, refined by the
   fit.
4. **Number of components** — only with *Find Optimal Number of Lifetimes*.

Everything except the four fitting options on the panel lives in the **Config
File**; **Edit…** opens it.

## What it reports

Species fractions (they sum to 1 — not intensity fractions) and lifetimes, the
IRF shift, two backgrounds and χ². No uncertainties. The results are written as
`<decay>_fit.json` and `<decay>_fit.png` to the output directory.

## Before you believe it

- **Change the fit range** (`start_fraction`, `area`). On the example decay a
  short component moves from 0.78 to 1.35 ns between two reasonable ranges.
- **Do not take the automatic component count as a verdict.** Its test needs a
  14 % drop in reduced χ² at the default threshold regardless of photon count,
  and a failed fit with more components can make it count wrong. Read the
  χ²ᵣ of every model in the JSON (`optimal_fitting`) and decide yourself.
- **Test it on a synthetic decay** made with your IRF, window and photon count
  (Synthetic Decay Generator, `csc synth-decay`).

## Further reading

- [Decay Analysis, Lazy Lifetime Analysis and synthetic decays](docs/guides/76_decay_analysis_tools.md)
  — every setting, the CLI, the ground-truth test and the known defects.
- [TCSPC: fluorescence-lifetime fitting](docs/concepts/tcspc_lifetime.md) —
  reconvolution, and how many components a decay supports.
- [Fitting objectives](docs/concepts/fitting_objectives.md) — why weighting by
  the data biases a fit at low counts.
- [Maximum-entropy decay analysis](docs/guides/62_maxent_decay.md) — the
  distribution view, without a component count.
