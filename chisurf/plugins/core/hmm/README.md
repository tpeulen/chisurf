# Hidden Markov model

Gaussian hidden Markov models for **binned time traces** — the shared HMM tool
of ChiSurf.

## What it does

Given one or more binned traces (rows = time bins, columns = detection
channels) it fits, by Baum-Welch:

- the **emission** of every state (mean and covariance per channel),
- the **transition matrix**, converted to rates once a bin width is given,
- the **state path**, by Viterbi decoding, and from it the **dwell times**,
- an **AIC/BIC scan** over the number of states, which is how the state count
  is chosen — the likelihood alone always prefers more states.

States are always relabelled dimmest-first, so "state 0" means the same thing
in every fit, table and figure.

## Where to use it

| Surface | How |
| --- | --- |
| GUI | *Analysis → Kinetics → Hidden Markov model* |
| CLI | `csc hmm fit trace.csv --states 3 --time-step 1e-3 -o fit.json` |
| RPC | `hmm.fit`, `hmm.scan` (JSON in, JSON out) |
| Python | `from chisurf.plugins.core.hmm.core import fit_traces, scan_state_counts` |

Another plugin that already holds a trace in memory hands it straight over:

```python
from chisurf.plugins.core.hmm.api import HmmSettings
from chisurf.plugins.core.hmm.core import fit_traces

fit = fit_traces(counts, HmmSettings(n_states=3, time_step=1e-3))
fit.summaries[0].mean_dwell     # seconds
fit.transition_rates            # 1/s
```

The GUI tool takes the same shortcut through `HmmTool.set_traces(...)`.

## Layout

```
api/       transport-agnostic dataclasses (settings, fit, scan)
core/      Qt-free analysis — the seam other plugins call
backend/   ZMQ/JSON-RPC handlers
cli/       csc hmm entrypoint
gui/       AutoForm view-model + hmm.view.json (plots via chiplot)
```

The estimator itself is `chisurf.core.math.hmm.GaussianHMM`; its performance is
tracked in [docs/development/benchmarks.md](../../../../docs/development/benchmarks.md).

## Related

- **H2MM** — photon-by-photon kinetics, no binning.
- **ebFRET** — empirical-Bayes HMM over many short FRET traces.
- **Intensity trace** — bins TTTR data into the traces this tool consumes.
