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
from chisurf.plugins.burst.burst_h2mm.api.models import H2mmSettings, StreamSettings
from chisurf.plugins.burst.burst_h2mm.backend.services import run_analysis

settings = H2mmSettings(
    streams=[StreamSettings("green", [0, 8]), StreamSettings("red", [1, 9])],
    min_states=1, max_states=4,       # scan state counts
    criterion="bic",                  # or "icl"
    engine="em",                      # or "em-float32", "surrogate", ...
    file_type="SPC-130",
)
summary, bundle = run_analysis(settings, "burstwise_All 0.1000#15")
result = bundle.analysis              # the full H2mmAnalysis

result.best.n_states                  # selected number of states
[(f.n_states, f.bic, f.icl) for f in result.scan]   # BIC/ICL vs state count
result.fret, result.populations       # per-state apparent E and photon fraction
result.trans_rates                    # transition-rate matrix (1/s)
result.dwells                         # Viterbi dwells: state, photons, duration, E (and S)
result.transitions                    # every state change, with its burst
result.dwell_time_arrays()            # per-state dwell durations, burst-edge dwells dropped
```

`run_analysis` reads the `.bur` files of a burst folder and the photons they
index; `summary` is the JSON-serialisable result the CLI writes as
`h2mm_result.json`. On the 2980 bursts (228 338 photons) of the double-labelled
DNA fixture (`burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15`)
this selects four states with E = 0.03, 0.22, 0.62 and 0.88 in about a minute.
The same run from the shell is `h2mm compute <folder> --file-type SPC-130
--donor-channels 0,8 --acceptor-channels 1,9 --max-states 4`. From the guided
facade it is `bursts.h2mm(states=(1, 2, 3))`, which returns the same
`H2mmAnalysis` as `.analysis`.

The GUI (**Spectroscopy → Single-Molecule → H2MM**, or step 7 of Burst
Analysis) runs the fit off the UI thread and redraws the model-selection and
FRET plots after each state count.

## The results dashboard

The `burst_h2mm` window shows its results as tabs — **Dwell FRET**,
**Selection**, **Decays**, **LL scan**, **TDP**, **Dwell times** and **State
path** — and the *Rates and states* tables, beside the *H2MM settings* and
*Detector setup* tabs. The four essential ones are:

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
written to `h2mm_dwells.csv`, and **Dwells in ndX** opens exactly that table
in ndX (**Export dwells** writes it as CSV). Gate on state and duration, drop the censored dwells with `Is Edge`, and
plot any pair of columns against each other; it is the same builder the CSV
comes from, so what you explore is what a later reader gets.

```{figure} figures/30_h2mm_results.png
:name: fig-30-h2mm-results
:width: 100%

The H2MM window after a 2–3-state scan of the BH SPC-132 sample's 2980 DNA
bursts (donor detector 0/1, acceptor 8/9, no acceptor-excitation stream), with
the *LL scan* and *Dwell times* tabs showing. *Rates and states* gives the fitted
exchange, S0 ⇄ S1 at ~8·10³ s⁻¹ in both directions, and the per-state E of
0.48 and 0.54; the dwell-time distributions leave out the burst-edge dwells.
```

```{figure} figures/h2mm_dashboard.png
:name: fig-h2mm-dashboard
:width: 90%

The same dashboard panels drawn from a simulated fit (script figure).
```

:::{admonition} Known defects
:class: warning
Rates at the numerical floor of the transition matrix (1e-12 per tick, here
7.4e-05 s⁻¹) are printed in *Transition rates* as if measured, and neighbouring
floor labels run into each other (`7.4e-057.4e-05`). The *State path* axis reads
*Time in burst (ms) (x0.001)* — the unit and an SI-prefix factor at once.
:::

## See also

- `chisurf/plugins/burst/burst_h2mm/` (`core/analysis.py`, `gui/tool.py`); theory in {ref}`concept-h2mm`.
- Uncertainty & simulation validation: [tutorial 31](31_h2mm_simulation_validation.md).
