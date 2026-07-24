---
type: Reference
title: Recurrence Analysis of Single Particles (RASP) theory and chisurf mapping
description: The RASP same-molecule probability P_same(tau) = 1 - 1/G(tau), the conditional recurrence FRET histogram, and how the theory maps onto the chisurf implementation.
resource: chisurf/core/fluorescence/burst/recurrence.py
tags: [burst, smfret, dynamics, recurrence, rasp, proximity-ratio, autocorrelation, hoffmann, schuler]
timestamp: '2026-07-24T00:00:00Z'
---

# Purpose

This note records the theory behind **Recurrence Analysis of Single Particles
(RASP)** and how it maps onto the chisurf implementation in
`chisurf/core/fluorescence/burst/recurrence.py`. The user-facing concept page is
`docs/concepts/recurrence.md`; the workflow guide is
`docs/guides/02_recurrence_rasp.md`.

# The problem RASP solves

In confocal single-molecule FRET on freely-diffusing molecules, a molecule
transits the detection volume in ~1 ms and produces one burst. Burst-integrated
FRET histograms therefore cannot resolve conformational kinetics on the ms–s
timescale, and — critically — they cannot distinguish **dynamic interconversion**
(one molecule switching state) from **static heterogeneity** (a mixture of
molecules frozen in different states): both broaden or split the histogram in the
same way.

RASP (Hoffmann, Nettels, Gopich, Schuler, *Phys. Chem. Chem. Phys.* 2011)
recovers the slow timescale without immobilization by exploiting **recurrence**:
a molecule that produced a burst remains near the focus and, by diffusion, is
likely to re-enter it and emit a second burst within a short **recurrence time**.
Within that window the recurring burst is, with high probability, the *same*
molecule, so conditioning on the initial burst's FRET value and inspecting the
recurring bursts exposes how the molecule evolved between the two visits.

# The two RASP quantities

## Same-molecule probability

Let $G(\tau)$ be the normalized autocorrelation of the burst arrival times. For a
Poisson (uncorrelated) burst stream $G=1$; recurrence enriches short-lag burst
pairs, giving $G(\tau)>1$. The **same-molecule probability** is

$$
P_\text{same}(\tau) = 1 - \frac{1}{G(\tau)} .
$$

- Short lag: recurrences dominate, $G\gg1$, $P_\text{same}\to1$.
- Long lag: the molecule has diffused away and is replaced by fresh molecules,
  $G\to1$, $P_\text{same}\to0$ (random coincidence).

The lag at which $P_\text{same}$ crosses a threshold defines the usable
**recurrence-time window** for the conditional histogram.

## Recurrence FRET histogram

1. Select an *initial* sub-population by efficiency window $[E_1,E_2]$.
2. For each initial burst at $t_i$, collect efficiencies of bursts arriving at
   $t_i+\Delta t$ with $\Delta t\in[t_1,t_2]$ (the recurrence window, chosen where
   $P_\text{same}$ is high).
3. Histogram those recurrence efficiencies; compare against the overall
   burst-efficiency histogram.

$$
H_\text{rec}(E \mid E_1{\le}E_i{\le}E_2,\; t_1{\le}\Delta t{\le}t_2)
$$

Static molecules reproduce the selected sub-population in the recurrence
histogram; interconverting molecules leak probability toward the other state.
Scanning $t_2$ across the $P_\text{same}$ range converts the leakage into a
relaxation curve whose rate is the interconversion rate.

# Mapping onto the chisurf implementation

`chisurf/core/fluorescence/burst/recurrence.py` operates purely on the per-burst
table (arrival time + efficiency/proximity ratio); no photon-level access.

- `same_molecule_probability(burst_times_s, tau_min_s, tau_max_s, n_bins,
  edge_correction)` — sorts burst times, bins the lag range log-spaced, counts
  ordered pairs $(i,j{>}i)$ with separation in each bin via `np.searchsorted`,
  divides by the Poisson expectation $\text{rate}^2\,\Delta\tau\,(T-\bar\tau)$
  (the `edge_correction` subtracts the mean lag from the acquisition span $T$),
  forming $G(\tau)$, then returns `p_same = clip(1 - 1/G, 0, 1)`. Returns
  `(tau, p_same, g)` with `tau` the geometric bin centres.
- `recurrence_efficiencies(burst_times_s, efficiency, e_range, dt_range_s)` — for
  each initial burst with efficiency in `e_range`, uses `searchsorted` on the
  shifted times to gather bursts within the `dt_range_s` recurrence window
  (excluding self), returning the flat array of recurring efficiencies.
- `recurrence_histogram(...)` — wraps the above and returns
  `(centers, recurrence, overall)` as unit-area (density) histograms for the
  recurrence sub-population and all bursts.

# Relationship to other dynamics probes

- BVA (`bva-theory.md`, `chisurf/core/fluorescence/burst/bva.py`) — intra-burst
  sub-window FRET variance vs binomial shot noise; sensitive to dynamics faster
  than a burst.
- 2CDE (`burst-2cde-theory.md`) — photon-stream asymmetry within a burst
  (sub-ms).
- RASP — interconversion slower than a burst but faster than the recurrence /
  diffusion time (ms–s), the regime the intra-burst methods cannot reach.

All three condition on FRET value rather than only reporting marginal histograms;
together they span sub-burst to seconds.

# Citation

Hoffmann, A., Nettels, D., Gopich, I. V., Schuler, B. (2011). Quantifying
heterogeneity and dynamics in single-molecule FRET via recurrence analysis of
single particles (RASP). *Physical Chemistry Chemical Physics*, 13, 1857–1871.
