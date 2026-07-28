# Hidden Markov models of binned traces

This tool turns a **binned trace** — photon counts per time bin, in one or more
detection channels — into states, dwell times and transition rates. It is the
shared HMM of ChiSurf: the same analysis is behind the GUI, the command line,
the RPC service, and the state fitting inside other tools such as the intensity
trace.

For the theory, the assumptions and their failure modes, see
{ref}`concept-hidden-markov-models`.

## When you need it

You have a time trace that steps between levels — a surface-immobilised
molecule folding, a dye blinking, a complex binding — and you want the *rates*,
not a picture. Thresholding by eye gives neither error bars nor a defensible
state count; an HMM gives both, and tells you when the data does not support
the number of states you assumed.

If the photons are too sparse to bin without losing the kinetics, use
{doc}`H2MM <19_h2mm_hidden_markov>` instead: it works photon by photon. If you
have many short FRET traces that are individually too short to fit,
{doc}`ebFRET <20_ebfret_binned_hmm>` shares a prior across them.

## Open the tool

**Analysis → Kinetics → Hidden Markov model**.

The window has three panels: **Model** (the settings), **Trace** (the data and
what the model made of it) and **States** (the numbers).

```{figure} figures/hmm_workspace.png
:name: fig-hmm-workspace
:width: 100%

Fitted on a simulated two-state trace with 1 ms bins — states at 18 and 55
counts per bin, true rates 15 and 30 s⁻¹. The fit returns 18.0 and 55.0 counts
with 13.9 and 27.9 s⁻¹, and BIC picks two states. Left: the settings. Middle:
the trace with the decoded path, and the intensity histogram with the fitted
emissions. Right: the state table, the transition matrix with rates, the
dwell-time histograms and the state-count scan.
```

## Load a trace

Drop text or `.npy` files into **Traces**, or use **+ Files**. The layout is one
row per time bin, one column per channel:

```text
# counts per 1 ms bin, green and red
18.0, 41.0
21.0, 39.0
55.0, 12.0
```

Several files are fitted **jointly as separate sequences**: they share one set
of states and transitions, but no transition is ever counted across the seam
between two traces. That is what you want for repeats of the same experiment.

Set **Bin width (s)** to the duration of one bin — 0.001 for 1 ms bins. Dwell
times and rates are then reported in seconds; left at 1 they come back in bins.

A tool that already holds a trace in memory hands it over directly rather than
through a file — this is what the intensity-trace tool does when you ask it for
an HMM.

## Choose the number of states

Do not guess. Open **State scan**, set the range (1 to 6 is usually enough) and
press **⇄ Scan states**. The scan plot shows AIC and BIC against state count;
take the **minimum**, not the elbow of the likelihood.

:::{tip}
BIC penalises parameters more heavily than AIC and normally returns the smaller
model. When the two disagree, prefer BIC and check that every state in the
result is real: a state with almost no occupancy, or a mean dwell of a single
bin, is noise being fitted.
:::

Then set **States** to the chosen count and press **▶ Fit**.

## Read the result

**Trace panel.** The grey trace with the decoded state path drawn over it in
orange, each bin at the total emission mean of its state. The path should track
the visible steps; where it flickers between two states in a single dwell,
either the states overlap or there are too many of them.

The intensity histogram below shows the fitted emission of each state, scaled by
how much time was spent in it. Well-separated peaks mean the assignment is
driven by intensity. Overlapping peaks are not automatically wrong — the model
then separates the states through their kinetics — but the per-bin assignment is
correspondingly less certain.

**States panel.** The state table gives the emission mean and width per channel,
the fraction of time in each state, the number of visits and the mean dwell.
States are always ordered **dimmest first**, so state 0 means the same thing in
every fit and every figure.

The transition table gives the per-bin probabilities, shaded so the sticky
diagonal stands out, with the rate underneath each off-diagonal entry once a bin
width is set.

The dwell-time histogram is drawn on a logarithmic count axis, where a Markov
state is a straight line. Curvature is the most useful diagnostic this tool
offers: it says the level hides more than one state.

## Headless

Everything above is scriptable. From the command line:

```bash
csg-hmm fit trace.csv --states 3 --time-step 1e-3 -o fit.json
csg-hmm scan trace.csv --min-states 1 --max-states 6
```

From Python:

```python
from chisurf.plugins.core.hmm.api import HmmSettings
from chisurf.plugins.core.hmm.core import fit_traces, scan_state_counts

scan = scan_state_counts(trace, min_states=1, max_states=6)
fit = fit_traces(trace, HmmSettings(n_states=scan.best_bic, time_step=1e-3))

fit.summaries[1].mean_dwell   # seconds in state 1 per visit
fit.transition_rates          # 1/s, rows summing to zero
fit.state_array               # decoded state per bin
```

Over RPC, the same result comes back as JSON from `hmm.fit` and `hmm.scan`.

## Settings reference

| Setting | What it does |
| --- | --- |
| **States** | Number of hidden states to fit. |
| **Covariance** | `full` (unrestricted matrix per state), `diag` (one variance per channel), `spherical` (one per state), `tied` (shared). Fewer parameters are more stable on short traces. |
| **Bin width (s)** | Duration of one bin; sets the units of dwell times and rates. |
| **Max EM maps** | Upper bound on Baum-Welch iterations. |
| **Tolerance** | Stop when the log-likelihood gain per iteration falls below this. |
| **Accelerate (SQUAREM)** | Extrapolates the EM iteration to the same optimum in fewer maps. Leave on. |
| **Decoder** | `viterbi` (most probable path — use this) or `map` (most probable state per bin). |
| **Seed** | Initialisation seed; fixing it makes a fit reproducible. |

## Related

- {ref}`concept-hidden-markov-models` — the theory and the assumptions.
- {doc}`Photon-by-photon HMM (H2MM) <19_h2mm_hidden_markov>` — no binning.
- {doc}`HMM of binned traces (ebFRET) <20_ebfret_binned_hmm>` — empirical Bayes over many traces.
- [Benchmarks](../development/benchmarks.md) — what the fit costs and why.
