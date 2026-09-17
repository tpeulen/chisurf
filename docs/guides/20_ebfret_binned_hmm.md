---
type: Guide
title: Hidden Markov analysis of binned FRET traces (ebFRET)
description: 'Wide-field / TIRF-camera FRET gives binned intensity-vs-time traces rather than confocal photon streams. ebFRET fits these with an empirical-Bayes Gaussian-emission HMM: an inner per-trace variational Bayes EM…'
tags: [guides, kinetics, hmm, fret, photons]
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

### The ebFRET window

**Spectroscopy → Single-Molecule → ebFRET** opens a port of the ebFRET GUI
itself: the same panels, menus, dialogs and defaults as the MATLAB program, drawn
with emtk and running its analysis on the ChiSurf backend. New to it? Press
**Guide** in the toolbar — the tour loads a simulated four-state dataset
(**Load demo**) and waits for you to press each control.

```{figure} figures/ebfret_gui.png
:name: fig-ebfret-gui
:width: 100%

The ebFRET window after **Run** on the simulated demo (40 traces, true levels
E = 0.10, 0.35, 0.55, 0.75). *Time Series*: series 3 with its Viterbi path over
the signal and over donor (green) and acceptor (red). *Ensemble*, for the
four-state model selected in *Select States*: the signal histogram split by
state, and the distributions of state centers, noise and dwell times.
```

The workflow, in the order the window is used:

1. **File → Load** — pick the file *type* in the dialog's filter list (a saved
   session `.mat`, a raw donor/acceptor `.dat` — stacked `[series donor
   acceptor]` or unstacked columns, the first row of each series being its
   label — an SF-Tracer `.tsv`, or an SMD `.mat`/`.json`/`.json.gz`, which asks
   which columns hold donor, acceptor or FRET). Loading with data present asks
   whether to **Keep** it (the new files become a new *group*) or **Replace** it.
2. **Analysis → Remove Photo-bleaching** crops every series where it bleaches —
   *Manual* thresholds on donor, acceptor, their sum or FRET (smoothed over 7
   frames, with optional padding), or *Auto* step detection. **Analysis → Clip
   Outliers** clips the signal to a range (default −0.2…1.2) and excludes series
   with more than 10 points outside it. Both are non-destructive and offer to
   re-guess the priors (*Auto*, *Manual*, *Keep Current*).
3. **Analysis → Set Priors** (optional) — expected state centers (spread from
   *Min* to *Max Center*), *Noise* and *Dwell*, each with a *Prior Strength* in
   equivalent observations. A low *Center* strength leaves superfluous states
   empty.
4. **Select Series** / **Crop** / **Exclude** — inspect and correct single
   series.
5. **States → Min, Max**, then **Analysis → States** *All* (every number of
   states) or *Current*, **Restarts** (default 2) and **Precision** (default
   `1e-3`; `1e-6` for publication), then **Run**. The window follows the series
   and state count being fitted; **Stop** ends the run, **Reset** discards it.
6. **Select States** switches between the models; **View** hides the Viterbi
   paths, prior (dashed) or posterior (solid) curves, or normalizes them by
   occupancy. **View → Series List** and **States Table** open the series table
   (selecting a row shows that series) and the selected model's per-state
   occupancy, center, noise and dwell time.
7. **File → Save** writes the whole session as a `.mat` ebFRET reads;
   **File → Export** writes the *Analysis Summary* (`.csv`, per number of states
   and per group, including the lower bound that decides the number of states),
   the *Traces* (`.dat`/`.mat`, chosen channels incl. Viterbi state and mean) or
   a *Single-molecule Dataset* (`.mat`/`.json`/`.json.gz`).

### Headless

The same session is available without a window, as RPC methods
(`burst_ebfret.session.load/set/run/export_*`, see the plugin manifest) and in
Python:

```python
from chisurf.plugins.burst.burst_ebfret.core.session import Session, RAW

session = Session(seed=1)
session.load_data(["stacked.dat"], RAW)            # File > Load, raw .dat
session.remove_bleaching(2)                        # Auto photobleaching removal
session.set_controls(restarts=2, run_precision=1e-4)
for event in session.run_ebayes(should_stop=lambda: False):
    pass                                           # Run (All: min..max states)
session.export_summary("summary.csv")              # File > Export > Analysis Summary
session.save_data("session.mat")                   # File > Save
```

For a quick scan without the window's state, `analyse` runs the same loop over
plain FRET traces and picks the number of states by the lower bound:

```python
from chisurf.plugins.burst.burst_ebfret.core.analysis import analyse

ana = analyse(traces, min_states=2, max_states=4)
ana.n_states, [s.mean for s in ana.states], ana.scan
```

and `ebfret compute stacked.dat --min-states 2 --max-states 4` does it from the
command line.

The numerical core is a line-by-line port of ebFRET's MATLAB code, checked
against ebFRET run under GNU Octave (forward-backward, VBEM, the empirical-Bayes
h-step and the analysis-summary report agree to ≲1e-11) and against the lower
bounds MATLAB saved in ebFRET's own session file (≤2e-8).

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
