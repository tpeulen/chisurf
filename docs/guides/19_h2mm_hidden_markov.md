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
answer, and coming back to the step does not restart it. Opening the step again
does not refit either; see [53 — Reusing results](53_reusing_results.md).

## Reproducing a scan

The restarts are **seeded**, so the same bursts and the same options give the
same answer every time. The seed is an ordinary fit option (*Seed*, default 0),
it is recorded in the result alongside the settings it was fitted with, and the
status line reports it: `Selected 3 states (BIC) from 2495 bursts / 275973
photons (seed 0)`.

This matters more than it looks. Model selection over state counts is not always
decisive — with few bursts, or states that overlap in E, two independent sets of
restarts can prefer different state counts. Reporting a state count without the
seed that produced it is therefore not reproducible. To find out whether your
result is robust rather than lucky, change the seed and refit: an answer that
survives several seeds is one you can report. Pressing **🔁 Restart** does *not*
do this — it reproduces the same fit, by design.

## Per-state decays

Once every photon carries a state, each state has a fluorescence decay — but
**only within one detection colour**. Donor and acceptor photons have different
instrument responses and different meaning, and the ratio in which they arrive
*is* the FRET efficiency. Histogramming all of a state's photons together
therefore produces a curve whose shape is set by the efficiency rather than by
any lifetime: two states with identical lifetimes but different E would show
different "decays". It is not a decay of anything.

The *Per-state decay* panel splits photons by stream and merges only within a
colour: one curve per (colour, state), drawn in the colour of the light that
produced it, with the line style giving the state (solid S0, dashed S1, …).

Splitting by *stream* rather than by detector matters under PIE/ALEX, where the
acceptor-excitation stream shares its detectors with the acceptor stream and is
separated only by a micro-time window. In the panel below you can see it
directly: the red curve stops at ~6.8 ns and the yellow one begins there.

```{figure} figures/h2mm_state_decays.png
:name: fig-h2mm-state-decays
:width: 90%

Per-state decays of a two-state fit, one curve per detection colour. Green is
the donor, red the sensitised acceptor, yellow the directly excited acceptor —
red and yellow share the same detectors and are separated by the PIE window at
~6.8 ns. Solid is S0 (low FRET: little red), dashed is S1 (high FRET).
```

The underlying histograms are written to **`h2mm_state_decays.csv`**, at the
finest key that is physically meaningful:

| Column | Meaning |
|---|---|
| `State` | Viterbi state |
| `Stream` | stream index (what separates red from yellow on one detector) |
| `Channel` | TCSPC routing channel — the physical detector |
| `Micro Time`, `Micro Time (ns)` | bin centre |
| `Counts` | photons in that bin |

Per detector, not per colour, so the merge stays yours to make and to check.
Summing several detectors of one colour assumes their responses are aligned; two
detectors of the same colour can still differ by an IRF shift, and this table is
what you look at to find out. (ChiSurf can correct such a shift when the data is
read — see the per-channel micro-time shifts in the channel-definition editor.)

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
