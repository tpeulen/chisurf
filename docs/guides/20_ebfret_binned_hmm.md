---
type: Guide
title: Hidden Markov analysis of binned FRET traces (ebFRET)
description: 'Wide-field / TIRF-camera FRET gives binned intensity-vs-time traces rather than confocal photon streams. ebFRET fits these with an empirical-Bayes Gaussian-emission HMM: an inner per-trace variational Bayes EM…'
tags: [guides, kinetics, hmm, fret]
---

# Hidden Markov analysis of binned FRET traces (ebFRET)

:::{admonition} Theory
:class: seealso
The Gaussian-emission HMM on binned traces, the empirical-Bayes shared prior,
variational inference (the ELBO as the state-count score), and the trade-off
against photon-by-photon H2MM are explained in the concept page
{ref}`concept-ebfret`.
:::

## What it does

Wide-field / TIRF-camera FRET gives **binned intensity-vs-time** traces rather
than confocal photon streams. **ebFRET** ({cite}`vandemeent2014`) fits these
with an empirical-Bayes Gaussian-emission HMM: an inner per-trace variational
Bayes EM, and an outer loop that re-estimates a **shared prior** across all
traces, so information is pooled and state counts are selected by evidence. It is
the binned-data complement to the photon-by-photon [H2MM](19_h2mm_hidden_markov.md),
covering the family of TIRF smFRET tools.

## In ChiSurf

```python
from chisurf.plugins.burst.burst_ebfret.core.analysis import analyse

ana = analyse(traces, min_states=2, max_states=4)   # ebFRET "stacked" .dat traces

ana.n_states                       # evidence-selected number of states
[s.mean for s in ana.states]       # per-state FRET means (StateFit.mean/std/occupancy)
ana.transition_counts              # Viterbi transition-count matrix
ana.dwells                         # per-state dwell times
ana.evidence                       # variational lower bound of the winning model
ana.scan                           # evidence vs state count (the model-selection curve)
```

`analyse` runs the empirical-Bayes loop over the whole trace set, scans
`min_states..max_states`, and returns the highest-evidence model already decoded
by Viterbi. Because the lower bound penalises complexity, the winning `n_states`
falls out of the scan — no separate BIC step is needed.

Exposed as the `burst_ebfret.jobs.compute` RPC service and an `ebfret compute`
CLI; validated against ebFRET's own `simulated-K04-N350` dataset.

## Result

Twelve simulated 300-bin traces exchanging between three FRET states
(E = 0.25, 0.55, 0.80) analysed by the real `analyse()`. The empirical-Bayes fit
recovers the state means to two decimals and the evidence scan selects K = 3 —
note that K = 4 does **not** score higher, because the variational lower bound
already penalises the extra state.

```{figure} figures/ebfret.png
:name: fig-ebfret
:width: 95%

**Left:** one of the twelve traces (grey) with the decoded Viterbi state path
(red) and the fitted state means (dotted). **Right:** the model-selection curve —
evidence against state count, maximal at the true K = 3.
```

## See also

- `chisurf/plugins/burst/burst_ebfret/`; photon-by-photon HMM: [H2MM](19_h2mm_hidden_markov.md).
- Binning the photon stream that feeds this: [binned photon traces](22_binned_photon_traces.md).
- Concept: {ref}`concept-ebfret`.
