# burst_ebfret — empirical-Bayes HMM for binned smFRET traces

A headless port of [ebFRET](https://github.com/ebfret/ebfret-gui) (van de Meent
et al.; a re-implementation of vbFRET, Bronson et al. 2009) into ChiSurf. It
fits a univariate Gaussian-emission hidden Markov model to **binned
FRET-efficiency time traces** (intensity-vs-time, TIRF-style), the class of data
ChiSurf previously had no analysis path for. It complements the photon-by-photon
`burst_h2mm` plugin, which handles confocal photon streams rather than binned
camera traces.

Porting one binned-trace HMM closes the functional gap behind a whole family of
TIRF tools listed on fret.community: **ebFRET, vbFRET, HaMMy, and SMACKS**.

## Method

Two nested loops (single-prior, `D = 1`):

- **Per-trace VBEM** (`core/vbem.py`) — variational-Bayes EM with conjugate
  Dirichlet priors on the initial-state and transition distributions and a
  Normal-Gamma prior on each state's `(mean, precision)`. Emission
  hyper-parameters use ebFRET's `(m, beta, a, b)` convention
  (`nu = 2a`, `W = 1/(2b)`). Forward-backward uses a linear-domain scaled
  recursion for speed.
- **Empirical Bayes** (`core/ebayes.py`) — re-estimates the shared prior from
  all trace posteriors via conjugate h-step updates (Dirichlet Newton and
  Normal-Gamma moment-matching, ported from ebFRET's
  `+dist/+dirichlet/h_step.m` and `+dist/+normgamma/h_step.m`), iterating until
  the summed variational evidence converges. Tying every trace to one prior is
  what makes state recovery robust across a heterogeneous population.

`core/viterbi.py` decodes MAP state paths; `core/analysis.py` scans a range of
state counts, selects the highest-evidence model, and reports per-state
emission summaries, a Viterbi transition-count matrix, and dwell segments.

## Validation

Validated against ebFRET's own `simulated-K04-N350` dataset (vendored under
`tests/data/`). At `K=4` the port recovers `[0.06, 0.34, 0.51, 0.62]`; the two
well-separated interior states match ebFRET's fitted `[0.33, 0.516]` within
0.05. The endpoints differ only because this port fits the **uncorrected
proximity ratio** `acceptor / (donor + acceptor)` in `[0, 1]`, whereas ebFRET
fits a background-subtracted "signal" whose donor-only level sits near zero
(so ebFRET reports `-0.006` where this port reports `~0.06`). `K=2` matches
ebFRET's `[0.30, 0.55]`.

## Usage

CLI:

```bash
ebfret compute path/to/stacked.dat --min-states 2 --max-states 4 --limit 80
```

The input is an ebFRET "stacked" `.dat`: whitespace-delimited
`[trace_id, donor, acceptor]`, traces concatenated and grouped by id. Python:

```python
from chisurf.plugins.burst.burst_ebfret.io import load_stacked_dat
from chisurf.plugins.burst.burst_ebfret.core.analysis import analyse

traces = load_stacked_dat("stacked.dat")
result = analyse(traces, min_states=2, max_states=4)
print(result.n_states, result.state_means)
```

## Scope / status

Experimental. Implemented: single-prior `D = 1` VBEM + empirical Bayes, Viterbi,
K-scan, CLI, RPC compute service. **Not yet** implemented: the prior-mixture
(subpopulation) path, VBEM restarts, SMD/session import/export, and a GUI tool.
Loader currently covers the ebFRET stacked `.dat` format; other trace importers
(SMD, generic CSV) are straightforward follow-ups.
