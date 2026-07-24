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
than confocal photon streams. **ebFRET** (van de Meent et al. 2014) fits these
with an empirical-Bayes Gaussian-emission HMM: an inner per-trace variational
Bayes EM, and an outer loop that re-estimates a **shared prior** across all
traces, so information is pooled and state counts are selected by evidence. It is
the binned-data complement to the photon-by-photon [H2MM](19_h2mm_hidden_markov.md),
covering the family of TIRF smFRET tools.

## In ChiSurf

```python
from chisurf.plugins.burst.burst_ebfret.core.analysis import analyze

result = analyze(traces, states=(2, 3, 4))     # ebFRET "stacked" .dat traces
result.emission_means      # per-state FRET means
result.transitions         # Viterbi transition-count matrix
```

Exposed as the `burst_ebfret.jobs.compute` RPC service and an `ebfret compute`
CLI; validated against ebFRET's own `simulated-K04-N350` dataset.

## See also

- `chisurf/plugins/burst/burst_ebfret/`; photon-by-photon HMM: [H2MM](19_h2mm_hidden_markov.md).
