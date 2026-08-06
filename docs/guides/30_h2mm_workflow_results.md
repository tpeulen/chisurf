---
type: Guide
title: 'H2MM: complete workflow and results'
description: 'Building on tutorial 19, this walks the full photon-by-photon hidden-Markov workflow the way a dedicated H2MM analysis is structured: optimise models for a range of state counts, select by BIC/ICL…'
tags: [guides, photons, h2mm, workflow, results]
---

# H2MM: complete workflow and results

:::{admonition} Theory
:class: seealso
See {ref}`concept-h2mm` for the photon-by-photon hidden Markov model behind these results.
:::

Building on [tutorial 19](19_h2mm_hidden_markov.md), this walks the full
photon-by-photon hidden-Markov workflow the way a dedicated H2MM analysis is
structured: **optimise** models for a range of state counts, **select** by
BIC/ICL, then **access the results** and produce the standard plots.

## The steps

```python
from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze

result = analyze(bundle,
                 states=(1, 2, 3, 4),      # scan state counts
                 engine="em",              # or em-float32 / surrogate
                 criterion="bic")          # model selection

# results access
result.n_states                # selected number of states
result.scan                    # BIC/ICL vs state count
result.dwells                  # per-dwell measured E (and S with an Aex stream)
result.transitions             # Viterbi transition-count matrix
result.state_lifetimes         # per-state dwell-time distributions
```

From the guided facade this is simply `bursts.h2mm(states=(1, 2, 3))`. The GUI
runs the fit off the UI thread and updates the plots live after each state-count
fit.

## The results dashboard

The `burst_h2mm` GUI presents six coupled panels; the four essential ones are:

- **Dwell E histogram** — the FRET efficiencies of the Viterbi dwells, peaking at
  the recovered state efficiencies (an E–S scatter when an Aex stream is present).
- **Transition-density plot** — E *before* vs E *after* each transition, showing
  which states inter-convert.
- **Model selection** — BIC/ICL vs number of states; the minimum is the selected
  model.
- **Per-state dwell-time distributions** — the residence times, giving the rates.
  **Burst-edge dwells are left out.** A dwell that touches its burst's first or
  last photon did not end — the burst did — so its duration is a lower bound set
  by the photon selection rather than by the kinetics. Including them bends every
  distribution toward the burst-duration distribution, and a state slower than a
  burst has *nothing else*: its "dwell times" would be burst lengths. When that
  happens the panel says so (*S1: no dwell ended within a burst*) instead of
  drawing a confident wrong answer — read it as "this state is slower than your
  bursts", which is a result about the sample, not a failure.

## Exploring the dwells

The per-dwell table — one row per Viterbi dwell, with its state, photon count,
duration, measured E/S, per-colour mean micro time and the `Is Edge` flag — is
written to `h2mm_dwells.csv`, and the toolbar's **🔬** opens exactly that table
in ndX. Gate on state and duration, drop the censored dwells with `Is Edge`, and
plot any pair of columns against each other; it is the same builder the CSV
comes from, so what you explore is what a later reader gets.

```{figure} figures/h2mm_dashboard.png
:name: fig-h2mm-dashboard
:width: 90%

H2MM results dashboard.
```

## See also

- `chisurf/plugins/burst/burst_h2mm/` (`core/analysis.py`, `gui/tool.py`); theory in {ref}`concept-h2mm`.
- Uncertainty & simulation validation: [tutorial 31](31_h2mm_simulation_validation.md).
