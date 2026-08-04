---
type: Reference
title: "2D-MFD forward models: the three that were tried and removed"
description: What a ground-truth benchmark said about the alternatives to the 2D-MFD forward model — donor weighting by occupancy, the burst span as the averaging window, and a transcribed Sim2D photon Monte Carlo. Each was built, measured against a known exchange rate and removed. Keeps the numbers, the reason each lost, and enough of the Monte Carlo's construction to rebuild it.
resource: chisurf/core/fluorescence/mfd/fit.py
tags: [reference, mfd, smfret, kinetics, benchmark, retired]
timestamp: '2026-08-04T00:00:00Z'
---

# 2D-MFD forward models: the three that were tried and removed

ChiSurf's 2D-MFD fitting was written from memory — a reconstruction of how the
method should work. `Sim2D` (Seidel lab, C#, 2015) was the implementation proven
in practice, and its physics core is about a hundred lines. The question was not
which is prettier but **why the old one worked better**, and neither
implementation can answer that about itself.

So three alternatives were built alongside the existing model and scored against
known ground truth: photons from a confocal simulator, through the same burst
tables, reader and response estimation a measurement uses, with everything but
the exchange rate pinned at truth. All three lost. Their code is gone; this page
is the record, so the next person does not rebuild them to find out.

## The measurements

Rate recovery, three regimes, three seeds. Bias is the median recovered rate
against the generating one.

| rate (Hz) | engine | weighting | window | bias | RMSE | s/fit |
|---|---|---|---|---|---|---|
| 200 | analytic | green | photons | +0.4% | 7.1% | 13.3 |
| 200 | analytic | green | **span** | −18.3% | 20.4% | 12.5 |
| 200 | analytic | **occupancy** | photons | +19.9% | 20.7% | 12.9 |
| 200 | **montecarlo** | green | photons | +4.1% | 6.3% | 7.3 |
| 1000 | analytic | green | photons | −7.8% | 8.6% | 19.0 |
| 1000 | analytic | green | **span** | −27.1% | 26.4% | 14.5 |
| 1000 | analytic | **occupancy** | photons | −0.5% | 9.8% | 18.7 |
| 1000 | **montecarlo** | green | photons | −10.2% | 11.2% | 25.5 |
| 5000 | analytic | green | photons | −2.6% | 3.3% | 20.2 |
| 5000 | analytic | green | **span** | −33.4% | 33.6% | 16.0 |
| 5000 | analytic | **occupancy** | photons | +1.2% | 2.5% | 17.3 |
| 5000 | **montecarlo** | green | photons | +15.3% | 14.6% | 45.8 |

Three seeds, so a few percent of RMSE is not resolvable and the ordering inside
that was never claimed.

## 1. The burst span as the averaging window

**What it was.** The occupation-time law took a burst's first-to-last-photon span
as the window over which its conformational state averaged.

**Why it lost.** It is wrong, not merely worse: a molecule is brightest at the
centre of its transit, so its photons over-sample whichever state it held then
and carry information about a shorter stretch of the trajectory. Costs 18–33%,
growing with the rate, and is the only error with the same sign in every regime.

**What replaced it.** The exact photon-weighted variance,
`Var(f) = π₀π₁ (1/N²) ΣᵢΣⱼ exp(−k|tᵢ−tⱼ|)`, inverted to an effective window —
`occupation.photon_weighted_occupation_variance` and `effective_window_scale`. It
reproduces the measured variance to 0.4% (1 kHz) and 0.1% (5 kHz) where the span
assumption is 9.5% and 32.4% out.

**Kept as a switch until now** so the benchmark could price it. It has been
priced; a knob whose only setting is "wrong" is a trap.

## 2. Donor weighting by occupancy

**What it was.** `donor_weighting="occupancy"` weighted the micro-time mixture by
the fraction of the burst each state occupied, `f_s` — what the model did before
the green weighting was derived.

**Why it lost, and the trap in the table.** It *beats* green weighting at 1 kHz
(−0.5% against −7.8%) and ties at 5 kHz. Taken at face value you would adopt it.
It then fails at 200 Hz (+19.9%).

Green weighting is **provably** exact: conditioned on being a donor photon, a
state's share is `f_s(1 − p_s)` normalised, because a high-FRET state can occupy
most of a burst while contributing almost none of the photons whose mean delay is
plotted. So the 1 kHz result is two errors cancelling at one timescale, not a
better model — and compensation that holds at one rate is worth less than
correctness at all of them. This is the clearest case in the whole exercise of
why a benchmark number must not outvote a proof.

## 3. The Sim2D photon Monte Carlo

**What it was.** A faithful transcription of Sim2D's forward model, in
`mfd/montecarlo.py`: draw a burst's photon budget from the measured distribution,
walk the kinetic scheme through its duration, hand the photons out over the
states by occupancy, let each choose a channel and a delay, histogram the result.
It approximated none of the three things the closed-form path approximates — the
nested Poisson/binomial sum, the Gaussian ⟨t⟩ moment kernel, the transfer-matrix
propagator — which is exactly what made it useful.

Construction notes, if it is ever rebuilt: it shared `species_properties` and the
IRF-convolved micro-time patterns with the analytic path, so the two could not
disagree about photophysics, only about burst treatment. It kept Sim2D's
multinomial-over-states followed by a per-state binomial even though thinning a
multinomial is provably an ordinary binomial, because a second implementation
that assumes the first one's algebra is not a second implementation. It needed
**common random numbers** — a fixed seed across the optimiser's iterations — or
the objective is not a deterministic function of the rate and the optimiser
differentiates sampling scatter. It did *not* carry over Sim2D's LFSR generator,
its `log(u+1)` exponential offset, its roulette wheel walking off the end of a
probability vector summing to `1 − ε`, or its dimensionless rate matrix (only the
product `k·T` was ever defined there).

**Why it lost.** It does not dominate the RMSE-vs-time front: faster where
exchange is slow (7.3 s against 13.3 at 200 Hz), both slower and more biased
where it is fast (45.8 s, +15.3% at 5 kHz). The plan this work followed
anticipated that if the Monte Carlo won, the occupation grid, moment kernel and
nested sum could be deleted. The opposite happened.

**What it was worth anyway, and the cost of removing it.** It carried the *same*
window bias as the analytic path — which is how the bias was found. Five
explanations were eliminated by measurement before it (the instrument, the
duration binning, the occupation-node coarsening, the pinned optics, and the
analytic approximations as a class); it was the Monte Carlo agreeing that proved
the error lived in an assumption the two **shared** rather than in either
implementation. Deleting it removes that diagnostic. The lesson generalises and
is the thing actually worth keeping:

> Two implementations agreeing is not evidence when they share an assumption.
> The donor-weighting defect and the window defect were both present in both
> scoring sources for as long as they existed, and the sources agreed with each
> other throughout.

## What the exercise concluded

Sim2D was not better because it was simpler. Its transcription carries the
identical window bias. Two separate things were actually true:

* **The instrument estimation was broken** — an instrument response 3.5 ns late
  and a fabricated background, absorbed invisibly on real data by a donor
  lifetime of 1.57 ns where a dye on DNA has ~2.8. Sim2D was immune to this
  structurally rather than by design insight: its lifetime axis is `tac/N_G`,
  with no IRF term to get wrong.
* **A physical assumption was shared and wrong** — the burst span as the
  averaging window.

Both are fixed. See [MFD fitting](../../docs/concepts/mfd_fitting.md) for the
model as it now stands and [benchmarks](../../docs/development/benchmarks.md) for
the surviving recovery numbers.
