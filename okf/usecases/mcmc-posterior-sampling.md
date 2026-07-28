---
type: Reference
title: Use case — how certain is that lifetime? (posterior sampling of a fit)
description: Fit a TCSPC decay, then press Sample to sample the posterior of its free parameters, and read the credible intervals, the chains and the convergence verdict.
tags: [usecase, fitting, sampling, mcmc, uncertainty, tcspc, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: posterior sampling — how certain is that lifetime?

**Goal:** a fit has converged and printed `τ₂ = 4.2198 ns ± 0.0036`. That `±` is
the curvature of χ² at the optimum — a Gaussian approximation that is wrong
whenever a parameter is bounded, weakly determined, or correlated with another.
The user wants the honest answer: sample the posterior of every free parameter,
get credible intervals that need no Gaussian assumption, and keep the chains for
later (they open in nDXplorer). This is the **Sample** button next to **Fit**, and
the ⚙ button beside it that configures the run.

**Data:** `test/data/tcspc/ibh_sample/Decay_577D.txt` (decay) and
`Prompt.txt` (IRF), IBH text, `dt = 0.0141` ns/ch, 10 MHz — the same pair as the
[TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md).

## Steps

1. Load the decay and the prompt as in the
   [TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md) (steps 1–4), select the
   decay, pick the `Lifetime ` model and click **Add fit**.
2. Assign `Prompt.txt` as IRF in the *Convolve* section, add a second lifetime
   component with the green **add** button, and click **▶ Fit**.
3. Read χ²ᵣ and the parameters on the *Info* tab — these are the covariance
   (`cov`) error bars.
4. Click **⚙** beside **Sample**. The *Sampling and fitting settings* dialog
   opens: *Sampler* (Blocked / Collapsed / Differential evolution / Ensemble /
   Ensemble slice / Metropolis), the chosen sampler's own knobs (Step size,
   Temperature, Thin, χ² max, N adapt), the run settings (Runs, Steps, Chunk),
   the chain format (Text `.er4` or HDF5) and the optimiser tolerances.
5. Click **Sample**. A folder chooser asks where the run goes.
6. Wait for the run. When it ends, the log dock reports either
   *"Sampling finished; no convergence problems detected"* or
   *"Sampling finished, but the chain is not usable:"* followed by the R̂ /
   effective-sample-size verdict.
7. Open the *Info* tab and scroll to **Parameter likelihood intervals**,
   **Derived quantities** and the sampling verdict at the bottom.
8. Inspect the output folder: one timestamped directory per run holding
   `chains/*.er4` (one file per run), `diagnostics.json`, `parameters.json` and
   `project.csp` — the project state that produced the chain.

## Expected

- Step 2 reaches **χ²ᵣ = 1.1340** (DW = 1.8141) with τ₁ = 1.6575 ns,
  τ₂ = 4.2198 ns, x₂ = 0.9415 over range 522…3793.
- Step 5 runs the sampler on the six free parameters (`sc`, `bg`, `xL2`, `tL1`,
  `tL2`, `ts`) and writes the folder of step 8. Every chain file starts
  `# chi2r lnprior sc bg xL2 tL1 tL2 ts`, one row per draw.
- Step 7 shows credible intervals derived **from the chain** for every parameter
  whose chain converged, and says so in the *Method* column.
- A run that has not mixed says so, and does not quietly pass its quantiles off
  as an answer.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, private RPC port
8900/8901, scratch `CHISURF_SETTINGS_DIR`) through the real main window and the
real `FittingControllerWidget` — `onRunFit`, `onErrorEstimate` (the **Sample**
button), `OptimizationSettingsModel` (the ⚙ dialog's view-model) and the server
job API. Thirteen sampling runs. Screenshots at each step, inspected.

**The engine underneath is excellent.** The blocked sampler runs 10 chains ×
1000 draws over a 4094-channel two-exponential fit in **2–5 s**; the ensemble
sampler 140 walkers × 5000 draws in 223 s. The output folder is exactly right:
one timestamped directory per run, ten `.er4` chain files, a `diagnostics.json`
carrying per-parameter mean/sd/quantiles/R̂/ESS/MCSE/τ, `parameters.json`, and
the `project.csp` that produced them, so a chain is never orphaned from its fit.
The diagnostics themselves are modern and honest — rank-normalised split-R̂,
bulk *and* tail ESS, automatic burn-in — and the *Info* tab refuses to quote an
unconverged chain, saying in words why (*"the chain on this fit did not converge
and was not used; these are linear propagation"*). Posterior sd where the chain
was healthy: `sc` 0.0045, `bg` 0.17, `xL2` 0.041, `tL1` 0.083, `tL2` 0.0040,
`ts` 0.33 — stable to two digits across independent runs.

**But almost nothing of that reaches the user.**

*Opening the settings dialog breaks the sampler.* The ⚙ form shows **N adapt =
0** — because `n_adapt`'s real default is `None` ("adapt automatically") and a
setting with no default is rendered as `0`. Pressing **OK without changing
anything** persists `n_adapt: 0`, which means *never adapt the proposal*, for
every run from then on. Measured A/B through the same GUI path, same fit, same
seeded state: pristine R̂ 1.190 / 1.205 and ESS 89–352 → after one OK, R̂ **2.967
and 10.913** with ESS 10–13 and the posterior sd of `ts` blown from 0.31 to
**41.4** (133×). Setting `n_adapt: 200` restores it. RF-840.

*The two plots built to judge a chain cannot be opened.* The fit window's tabs
are Fit / Data table / Info / Parameter scan / Distribution / Residuals. The
`Chain diagnostics` (rank plot + ESS evolution) and `Posterior graph`
(structure / dependence / junction tree) plots exist, are finished and are
documented — and are listed only in the abstract `ModelWidget.plot_classes`,
which every registered model overrides, while not being registered as AutoForm
plot types either, so no view-spec model can ask for them. RF-841.

*The Sample button never says it is busy.* Through a 260 s run: button enabled,
label unchanged, no progress bar, no busy cursor; the status bar shows the
*previous* run's message. A second click starts a **second concurrent job on the
same fit** — both ran, both logged
`frozen_structure: the parameter structure changed during a run that declared it
fixed`, and the two racing chains came back at R̂ 3.107 and 1.709 where a single
run of the same length gives 1.02. RF-842, RF-843.

*The shipped defaults cannot produce a usable answer.* Blocked / 1000 steps /
10 runs never converged in five independent runs (worst R̂ 1.14–1.39, ESS down
to 52). Nor did 20 000 steps with adaptation (36.6 s, R̂ ≤ 1.049) or ensemble
with 5000 draws × 140 walkers (223 s, R̂ ≤ 1.021, **ESS ≈ 7000 per parameter**) —
because the gate is per-parameter R̂ ≤ 1.01 *and* ESS ≥ 400, all or nothing. So
the chain is discarded, the *Info* tab quotes the covariance interval it would
have quoted anyway, and the user has spent four minutes to be told to "sample
longer" with no indication of how much longer or which knob does it. RF-844.

*The covariance interval it falls back to ignores the parameter's own bounds.*
`sc` is declared on `(0, 100)` and is printed as `±1.47 (32765.6 %)` with the
interval `[-1.4635, 1.4724]`; the chain measures it at `0.0067 +0.0055 -0.0048`.
`ts` is printed as `±104 (55485.9 %)` against a chain sd of 0.33. Worse, the
`posterior_summary()` rows behind those lines already carry
`warning: posterior is skewed (0.00662 +0.00554 -0.00475)` and a numeric
`asymmetry` — measured from the chain the tab has in hand — and the tab prints
neither. RF-845.

## UX / UI suggestions

- **Put the sampling verdict where the run ends, not 40 lines down the *Info*
  tab.** After a run the user is looking at the fit window; the verdict is
  below 25 fixed nuisance parameters and needs scrolling to reach. A line in
  the fit annotation ("chain: R̂ 1.02, ESS 6800 — not usable") or a coloured
  strip on the controller would land where the eye is.
- **Show the numbers next to the thresholds.** The warnings are prose ("worst:
  `tL1` at 1.709"); what a user needs to decide *how much* longer to run is the
  table that is already in `diagnostics.json`: per parameter, R̂ and ESS against
  1.01 and 400. Print it in the *Info* tab.
- **Say what "Steps" buys.** With ESS growing roughly linearly, the run that
  reached R̂ 1.02 needed ~5× more draws. A one-line estimate after a failed run
  ("this chain would need ≈ 25 000 draws") turns an unbounded retry loop into
  one decision.
- **`N adapt`, `Chunk`, `Thin`, `Stretch`, `Initial spread`, `Temperature`,
  `χ² max`** are bare numbers with no units and no visible explanation (the
  descriptions exist, but only as hover tooltips). `χ² max` renders as
  `1000000000.0000` — four decimals on a cutoff of a billion.
- **Don't offer a knob the chosen sampler ignores.** Every blocked run logs
  `blocked does not take substeps; ignoring` while the *Run* box shows
  **Chunk = 100**. Hide (or grey) the settings the selected sampler does not
  accept — the form already knows which those are.
- **Name the run.** The output folder is a bare timestamp; a run is otherwise
  indistinguishable from the next. Offering `<fit name>_<timestamp>` (or
  writing the fit name into `diagnostics.json`'s top level) would make a folder
  of thirteen runs navigable.
- **The chain never comes back into the session.** After sampling, nothing in
  the GUI lets the user look at a marginal, a pair correlation, or a trace —
  the only route is to find the `.er4` files on disk and open them elsewhere.
  Even without the missing plot tabs (RF-841), a "show last chain" entry would
  close the loop.
- **The *Parameter scan* tab is still an empty black plot** on a −0.5…0.5 axis
  with no visible control (its controller lives in the *Plot settings* dock) —
  the same dead-end noted in the
  [TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md) use case. It is the one
  tab a user hunting for uncertainty would click first.

## Bugs filed

- RF-840 — the ⚙ settings dialog writes `n_adapt: 0` on OK, permanently
  disabling proposal adaptation (R̂ 1.2 → 10.9).
- RF-841 — `SamplingDiagnosticsPlot` and `PosteriorGraphPlot` are unreachable
  from every registered model.
- RF-842 — **Sample** stays enabled during a run and a second click starts a
  concurrent job on the same fit, corrupting both chains.
- RF-843 — a multi-minute sampling run shows no progress of any kind.
- RF-844 — the shipped sampling defaults cannot pass the convergence gate, so
  the chain is always discarded.
- RF-845 — the fallback covariance interval ignores the parameter's bounds and
  drops the skew warning the chain already measured.
