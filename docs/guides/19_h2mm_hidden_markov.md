# Photon-by-photon hidden Markov models (H2MM)

:::{admonition} Theory
:class: seealso
The hidden-Markov model for photon streams — emission/transition matrices, the
$A^{\Delta t}$ propagator, Baum-Welch optimization, and state-number selection by
BIC/ICL — is explained in the concept page {ref}`concept-h2mm`.
:::

## What it does

**H2MM** (Pirchi et al. 2016; Harris et al. 2022) fits a hidden Markov model
directly to the **photon stream** — not to binned intensities — so it resolves
sub-burst FRET-state dynamics down to the microsecond scale, well below the bin
sizes an intensity-trace HMM needs. It maximises the photon-by-photon likelihood
over the state emission rates and the transition-rate matrix, selecting the
number of states by BIC/ICL, and recovers the most-likely state path (Viterbi),
per-state dwell times and the transition-density map.

## In ChiSurf

The `burst_h2mm` plugin is a Qt-free numba engine (with an equivalent C++
`tttrlib.H2MM`) under an RPC service and GUI, embedded in the burst workflow:

```python
from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze

result = analyze(bundle, states=(1, 2, 3), criterion="bic")
result.dwells        # per-dwell measured E (and S with an acceptor-excitation stream)
result.transitions   # Viterbi transition-count matrix
```

From the guided workflow: `bursts.h2mm(states=(1, 2, 3))`. Optional ALEX/PIE
stoichiometry, nanotime divisors (lifetime-resolved states) and bootstrap
uncertainties are supported.

In the burst workflow, **step 6 starts fitting as soon as you open it**. A state
scan with restarts runs for minutes, so it runs off the GUI thread and **Stop**
in the toolbar ends it — a stopped scan is discarded rather than reported as the
answer. Opening the step again does not refit; see
[53 — Reusing results](53_reusing_results.md).

## Result

A two-state Viterbi state path and the resulting per-dwell FRET-efficiency
histogram — two states cleanly separated (dashed lines mark the true state
efficiencies).

```{figure} figures/h2mm.png
:name: fig-h2mm
:width: 90%

H2MM state path and dwell E histogram.
```

## See also

- `chisurf/plugins/burst/burst_h2mm/`; the binned-trace complement below.
- HMM of binned traces: [ebFRET](20_ebfret_binned_hmm.md).
