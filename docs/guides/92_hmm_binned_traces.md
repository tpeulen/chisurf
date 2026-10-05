---
type: Guide
title: States and rates from a binned trace (Hidden Markov model)
description: Fitting a Gaussian hidden Markov model to binned time traces with the Hidden Markov model tool, choosing the number of states with the AIC/BIC scan, and reading emissions, dwell times and transition rates.
tags: [guides, kinetics, hmm, traces]
---

# States and rates from a binned trace (Hidden Markov model)

**What you get:** the number of discrete states in an intensity or FRET trace that already arrives on a
fixed time grid, how bright each state is, how long it lasts and how often it jumps to each of the others.
For confocal photons, where the arrival times carry the timing, use photon-by-photon H2MM
({doc}`19_h2mm_hidden_markov`): binning those throws the information away. For many short FRET traces
see {doc}`20_ebfret_binned_hmm`.

## Theory

A hidden Markov model describes the trace as a path through $K$ hidden states with a transition
probability matrix $A$ per bin and a Gaussian emission (mean and covariance over the channels) per state.
Baum-Welch (EM, optionally accelerated by SQUAREM) fits $A$ and the emissions, Viterbi decodes the most
probable state path, and the dwell times follow from that path; with a bin width the off-diagonal
probabilities become rates, $k_{ij} \approx A_{ij}/\Delta t$. The likelihood always improves with more states,
so the number of states is chosen by the minimum of AIC or BIC. See {ref}`concept-hidden-markov-models`.

## 1. Open the tool and load a trace

*Spectroscopy → Kinetics → Hidden Markov model*. A trace file has one row per time bin and one column per
detection channel (`.csv`, `.txt`, `.dat` or `.npy`). Press **Add files...** and click one or more files in
the dialog, or drop them on the window; several files are fitted jointly as separate sequences.
**Demo trace** loads a generated three-state trace with known means and dwell times, to try the tool.

```{figure} figures/hmm_window.png
:name: fig-hmm-window
:width: 100%

A two-channel trace with three states (mean counts per bin 20 / 60 / 110 in channel 1), fitted with three
states and scanned from one to five. **Top right**, the trace with the decoded state path drawn at each
state's emission mean; **bottom left**, the fitted states and the transition matrix with rates; **bottom
right**, the intensity histogram with the fitted emission densities (tabs: dwell times, state scan).
```

## 2. Set the model

*States* is the state count and *Covariance* the shape of the emission noise (`full`, `diag`, `spherical`
or `tied`: fewer parameters are more stable on short traces). **Bin width (s)** turns probabilities into
rates; leave it at 1 to report dwell times in bins. The **Fitting** section holds the maximum number of EM
maps, the tolerance, the decoder (`viterbi` is the single most probable path, `map` decides every bin on
its own), the seed of the k-means start and the SQUAREM switch; **State scan range** holds the range
the scan scores.

## 3. Fit, scan, check

**Fit** fits the chosen number of states and decodes the path; the status line reports log L, BIC and the
iterations. **Scan states** fits every count in the range and plots AIC and BIC against it: take the
minimum of BIC. If BIC keeps falling to the end of the range, the trace has structure the model does not
describe (bleaching, drift, a continuum): look at the trace, do not raise the maximum.

Three checks refute a fit: **overlapping emission densities** in the intensity histogram (intensity alone
does not separate the states, the assignment leans on the transition structure), **curved dwell-time
histograms** on the log axis (a Markov state predicts a straight line), and a **transition matrix with a
large off-diagonal element between states of the same brightness**. The mouse wheel zooms every plot.

## 4. Save and reuse

**Save fit...** writes the states, transition matrix, rates and dwell times as JSON. The same analysis is
available as `csc hmm` and as the `hmm.fit` / `hmm.scan` RPC methods, and other tools hand a trace over in
memory with `set_traces`.

```python
import numpy as np
from chisurf.plugins.core.hmm.gui.view_model import HmmViewModel

m = HmmViewModel(); m.set_traces([np.loadtxt("trace.csv", delimiter=",")])
m.n_states = 3; m.time_step = 0.001; m.run(); m.run_scan()
print(m.status)                      # e.g. "3 states · log L = ... · BIC = ..."
print(m.fit.transition_rates)
```

## See also

- Concept: {ref}`concept-hidden-markov-models`; related: {doc}`19_h2mm_hidden_markov`, {doc}`20_ebfret_binned_hmm`.
