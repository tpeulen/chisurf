---
type: Reference
title: Use case — rates from a binned trace with a hidden Markov model
description: Fit a Gaussian HMM to a binned intensity trace — choose the state count by BIC, decode the state path, and read the emissions, dwell times and transition rates in per-second units.
tags: [usecase, hmm, kinetics, trace, single-molecule, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: rates from a binned trace — the hidden Markov model

**Goal:** a trace that steps between levels — a molecule folding, a dye blinking,
a complex binding, a burst crossing the focus — carries kinetics that no
histogram of its intensities can recover. Thresholding by eye gives a state path
with no error bars and no defensible number of states. The user wants, from one
binned trace (or several repeats of one experiment): **how many states** there
are, **how bright** each one is, **how long** it lives, and the **rate** of every
transition between them. This is the binned-trace counterpart of
[H2MM](/usecases/h2mm-burst-dynamics.md) (which works photon by photon inside
bursts) and of [Gopich–Szabo](/usecases/photon-by-photon-kinetics.md).

**Tool:** `chisurf.plugins.core.hmm` (`HmmTool`, ribbon **Analysis ▸ Kinetics ▸
Hidden Markov model**) — an AutoForm over `hmm.view.json`: a *Model* settings
dock, a *Trace* dock (trace + decoded path, intensity histogram) and a *States*
dock (state table, transition matrix, dwell times, state-count scan). It is the
declared **shared HMM seam**: the same `chisurf.plugins.core.hmm.core` is used by
the CLI (`csc hmm fit|scan`), the `hmm.fit` / `hmm.scan` RPC methods and by the
Trace Browser's own *Perform HMM*, all over `chisurf.core.math.hmm`.

**Data:** two traces were driven this run.

- **Ground truth** — a three-state simulated trace built with the shipped
  example's numbers (`examples/notebooks/HMM_Binned_Traces.py`): 30 000 bins of
  1 ms, emissions 12 / 34 / 60 counts per bin at σ = 4, rate matrix
  20, 2 / 15, 25 / 1, 30 s⁻¹, occupancy 0.268 / 0.408 / 0.324. Also split into
  three 10 000-bin "repeats" to exercise the joint fit.
- **Real photons** — `chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m005.spc`
  (Becker & Hickl SPC-132 single-molecule DNA, 179 151 photons over 64.08 s,
  routing channels 0, 1, 8, 9) binned at 1 ms into a one-column total-counts
  trace and into a two-column green (8, 0, 3) / red (9, 1, 2) trace.

## Steps

1. Open **Analysis ▸ Kinetics ▸ Hidden Markov model**. Three docks come up side
   by side: *Model* with an empty file list, *Trace* and *States* with empty
   plots and *No fit yet.*
2. Press **▶ Fit** before loading anything — the status line answers
   *"No traces loaded."* (no dialog, no traceback).
3. Drag the trace file onto the **Traces** list (or **➕ Files** / **🗄️
   Database**). Rows are time bins, columns are detection channels; several
   files are fitted jointly as separate sequences. *Nothing is drawn yet — see
   RF-853.*
4. Set **Bin width (s)** to the bin the trace was made with (`0.001` here).
   Leaving it at 1 reports dwells in bins and suppresses the rate column.
5. Press **?** for the theory: why the likelihood cannot choose the state count,
   what overlapping emission densities and curved dwell histograms mean.
6. Expand **State scan**, set **From** 1 and **To** 6, and press
   **⇄ Scan states**. On the simulated trace this took 7.4 s and ended
   *"BIC prefers 3 states, AIC 3."*; the *State-count scan* plot shows both
   criteria dropping from 261 568 (1 state) to 177 213 (3) and rising again.
7. Set **States** to the winner (3) and press **▶ Fit** (0.7 s). The status line
   reads `3 states · log L = -88,534.2 · BIC = 177,212.8 · 2 iterations`.
8. Read the **States** table: mean, std, occupancy, visits and mean dwell per
   state, each row tagged with the colour used in the plots.
9. Read the **transition matrix** below it: per-bin probabilities with the
   derived rate under each off-diagonal cell, shaded so the sticky diagonal
   reads at a glance.
10. Check the **Trace** dock: the binned trace with the decoded state path over
    it, and the intensity histogram with each state's emission density scaled by
    its occupancy.
11. Check the **Dwell times** plot (log y): a Markov state gives a straight
    line; curvature means the state hides substructure.
12. Optionally raise **Fitting ▸ Max EM maps**, switch **Covariance** to `diag`
    or `tied` for a short trace, or change the **Seed** and refit to confirm the
    optimum is not a local one.

Headless (identical numbers, verified this run):
`csc hmm fit trace.csv --states 3 --time-step 0.001 -o fit.json`, or the
`hmm.fit` / `hmm.scan` RPC methods.

## Expected

- The scan picks the generating state count and the fit returns the generating
  parameters.
- Every time-dimensioned number (dwell, rate) is in the unit implied by **Bin
  width**.
- A file the tool cannot read is named, with the reason.
- A binned trace produced elsewhere in ChiSurf can be loaded.

## Observed (last run: 2026-07-28)

**The estimator is exact and fast.** On the simulated trace with 3 states the fit
returned means **12.02 / 33.91 / 59.98** (truth 12 / 34 / 60), std 3.98 / 4.01 /
4.00 (truth 4), occupancy **0.268 / 0.408 / 0.324** (truth identical to three
decimals), mean dwells 47.3 / 28.3 / 33.2 ms (truth 45.5 / 25.0 / 32.3) and rates

| from → to | fitted (s⁻¹) | true (s⁻¹) |
|---|---|---|
| 0 → 1 | 19.4 | 20 |
| 0 → 2 | 1.87 | 2 |
| 1 → 0 | 12.6 | 15 |
| 1 → 2 | 22.7 | 25 |
| 2 → 0 | 1.62 | 1 |
| 2 → 1 | 28.5 | 30 |

in **0.7 s** (2 EM maps with SQUAREM). The state-count scan over 1…6 took 7.4 s
and both criteria minimise at 3; at 12 states BIC correctly rises again
(178 676 against 177 213). The three 10 000-bin repeats fitted **jointly** return
the same answer (means 12.02 / 33.91 / 59.98) rather than being concatenated into
one sequence. The CLI reproduced the GUI's numbers digit for digit.

**On the real photon stream** the 1 ms trace fits as background + burst: 2 states
at **2.25 and 18.74** counts per ms, occupancy 0.969 / 0.031, burst dwell
**3.58 ms**, 546 visits over 64 s — the right order of magnitude for freely
diffusing single molecules. The two-channel green/red version gives
1.51 / 0.72 and 12.53 / 5.32 counts per ms with a burst dwell of 2.4 ms.

**What a user runs into.**

- **Loading a file shows nothing at all.** After the drop the path sits in the
  list, but both plots stay empty and the status line still reads *"No traces
  loaded."* — the plot sources read the unpopulated private list rather than the
  lazy loader, so the trace first appears *after* a fit (RF-853). Screenshot
  `03_file_dropped.png`.
- **A file that cannot be read is reported as no file.** A raw `.spc` dropped in
  by mistake produces *"No traces loaded."*; the real diagnosis
  (`'utf-8' codec can't decode byte 0x87`) is composed by the loader and then
  overwritten before the user sees it (RF-854).
- **The only binned-trace file ChiSurf itself writes cannot be loaded.** The
  Trace Browser's *Perform HMM* writes `<stem>_HMM#N_XXms/traces/<stem>_traces.csv`
  with the header `time_s,Ch0,HMM_State`; dropping it into this tool fails on the
  header, and with the header removed the time column is fitted as a third
  detection channel (state means came back as *32.03 / 32.49* "counts") — a
  plausible number that is really the mean elapsed time (RF-855).
- **A bin width below 1 µs cannot be typed and silently becomes 10⁻¹² s.** The
  spin box has 6 decimals and a minimum of 0, so `1e-7` rounds to `0.000000`,
  which the model clamps to 1e-12: the tables then report dwells of
  **4.7×10⁻¹¹ s** and rates of **1.9×10¹⁰ s⁻¹** with no warning, and the trace
  axis reads `time (x1e-09)` (RF-856). Screenshot `10_binwidth_zero.png`.
- **A reversed scan range answers "BIC prefers 0 states".** From 5, To 2 returns
  an empty scan in 0.2 s and reports a state count of zero as a result (RF-857).
- **Long runs are silent.** A 12-state fit took **59.8 s** with no progress, no
  disabled button and the previous run's message still in the status line; a
  second **▶ Fit** click during the run is dropped without a word (RF-858).
- **The transition matrix is illegible past ~6 states.** At 12 states (the
  control allows 32) the header wraps to one character per line — `fro m \ to` —
  and every cell breaks into stacked digit groups (`0.` / `20` / `73` / `264`).
  The dwell-time legend clips at 6 of 12 entries and the state colours repeat
  after 8 (RF-859). Screenshot `09_overfit.png`.
- **The four plot titles authored in `hmm.view.json`** (*Trace and decoded
  states*, *Intensity histogram*, *Dwell times*, *State-count scan*) **are not
  rendered**: a plot nested in a panel loses its title, so each dock shows two
  captionless plots (RF-860).
- **The result cannot leave the window.** There is no Save/Export button; the
  view model has `save_result()` and nothing calls it, so the states, rates,
  dwell times and the decoded path are reachable only from the CLI or RPC
  (RF-861).
- **Building the trace exposed a Trace Browser defect.** With no detector setup
  configured it offers routing-channel boxes **0–7**, ticks them all, and then
  processes only `selected_detectors[0]` — channel 0 alone, 50 896 of 179 151
  photons — while channels 8 and 9 (101 134 photons, 56 % of the file) are not
  offered at all (RF-862).

Screenshots this run: `01_open.png`, `03_file_dropped.png` (empty after load),
`05_fit3.png` (the good three-state result), `07_real_gr.png` (real photons,
two channels), `08_bad_file.png`, `09_overfit.png`, `10_binwidth_zero.png`,
`11_help.png` (the help modal, which renders correctly), `14_chain_result.png`.

## UX / UI suggestions

- **Draw the trace on load and say what was read.** "3 files · 30 000 bins ·
  1 channel" in the status line, and the trace plotted, is the confirmation the
  drop currently withholds.
- **The trace plot is unreadable at full length.** 30 000 bins (decimated to
  5 000) over ~380 px is a solid block in which the decoded state path — the
  whole point of the panel — is invisible. Show a window (the shipped example
  plots the first 3 s) with a start/length control or a scrollbar, the way every
  trace viewer does; the legend also sits on top of the data.
- **Label the time axes with their unit.** `time` and `dwell time (x0.001)`
  should read `time / s` and `dwell time / s` once **Bin width** is set, and
  `time / bins` when it is not.
- **Give the bin width a sane spin step and a realistic minimum.** The step is
  1 s on a control whose useful range is 10⁻⁵…10⁻¹ s, so one arrow click from
  1 ms lands on 1.001 s. Scientific notation (or µs units) would also let a
  sub-microsecond bin be typed at all.
- **Offer a log y on the intensity histogram.** On the real trace the background
  peak (15 000 counts) flattens the burst state's density to the axis; the
  fitted emission of the state the user cares about is invisible.
- **Warn when a Gaussian emission is implausible for counts.** The real
  two-channel fit returned state 1 with mean 12.5 and std 17.4 — a Gaussian
  whose mass is largely at negative counts. A note in the state table (or the
  help) that a Gaussian HMM approximates Poisson counts poorly at low rates
  would save a misread.
- **Wire the hand-off that already exists.** `HmmTool.set_traces()` is documented
  as "the seam other plugins use" and no caller exists in the application (only
  the docs screenshot script); the Trace Browser, which already bins a trace and
  fits it with the same core, has no "open this in the HMM tool" action.
- **Agree one trace-file format.** `load_trace` accepts "rows = bins, columns =
  channels" with no header and no time column, while the in-tree producer writes
  both. Skipping a header row and offering a "first column is time" tick would
  make the two halves of ChiSurf's own HMM story connect.

## Bugs filed

- RF-853 — trace and histogram plots stay empty until a fit is run.
- RF-854 — the read error is discarded and reported as "No traces loaded."
- RF-855 — ChiSurf's own exported trace CSV cannot be loaded, and its time
  column is fitted as a detection channel.
- RF-856 — bin widths below 1 µs collapse to 10⁻¹² s and are reported as rates
  of 10¹⁰ s⁻¹.
- RF-857 — a reversed state-scan range reports "BIC prefers 0 states".
- RF-858 — no progress or busy state on a minute-long fit; a second click is
  silently dropped.
- RF-859 — the transition matrix is illegible beyond ~6 states.
- RF-860 — `plot` section titles are dropped when the plot is nested in a panel
  (AutoForm, 6 plots in 3 shipped specs).
- RF-861 — the fit cannot be saved or exported from the GUI.
- RF-862 — Trace Browser: only the first routing channel is processed and
  channels above 7 are not offered.
