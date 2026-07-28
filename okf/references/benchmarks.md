---
type: Reference
title: "Benchmarks"
description: Where the performance numbers for ChiSurf's own compute cores live, what each measures, and the rule that they are regenerated in the change that touches the component.
resource: docs/development/benchmarks.md
tags: [references, performance, benchmarks, hmm, sampling]
timestamp: '2026-07-28T00:00:00Z'
---

# Benchmarks

Measured performance of the compute cores ChiSurf owns lives in
`docs/development/benchmarks.md`, and every table there is produced by a script
under `test/benchmarks/`. The page is linked from the repository README.

## The rule

**Re-run the affected section and update its table in the same change that
touches the component**, and append the change here in [the log](/log.md) like
any other material change. A benchmark page nobody refreshes becomes a claim
about code that no longer exists — worse than no page.

Timings are machine-dependent, so the environment line is restated with the
tables and numbers from different machines are never mixed in one table.

## What is covered

| Component | Script | Work unit measured |
| --- | --- | --- |
| [Gaussian HMM](/subsystems/hidden-markov-models.md) | `test/benchmarks/benchmark_hmm.py` | Seconds per Baum-Welch E-step, plus E-steps and log-likelihood at convergence |
| Ensemble samplers | `test/benchmarks/benchmark_sampling.py` | Effective samples per second and per log-probability evaluation |
| Pixel-wise MLE | `test/benchmarks/benchmark_pixel_mle.py` | Per-pixel lifetime fits, baseline vs vectorised vs threaded |

## Two rules that keep the numbers honest

* **Report the quality next to the time.** Two implementations that stop at
  different optima are not comparable on time alone; a faster fit that ends at a
  worse likelihood has not won. The HMM table therefore carries the
  log-likelihood beside every timing.
* **Measure the unit of work, not the run.** Seconds per E-step, or effective
  samples per evaluation, are comparable across machines and across
  trajectories; wall time for a whole fit is not, because it mixes
  implementation cost with how many iterations that particular run happened to
  take.

Each script also carries a `slow`-marked test asserting the property the
benchmark exists to protect, so a regression fails the suite rather than merely
looking worse in a table nobody re-ran.
