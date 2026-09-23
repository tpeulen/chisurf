---
type: Guide
title: Fluorescence lifetime from photon bursts
description: Beyond photon counts, each burst carries the donor and acceptor micro-times — so a fluorescence lifetime can be fitted per burst.
tags: [guides, tcspc, lifetime, bursts, photons, fret]
---

# Fluorescence lifetime from photon bursts

:::{admonition} Theory
:class: seealso
See {ref}`concept-tcspc-lifetime` for the multi-exponential decay model and Poisson-MLE lifetime fitting.
:::

## What it does

Beyond photon *counts*, each burst carries the donor and acceptor **micro-times**
— so a fluorescence **lifetime** can be fitted per burst. The lifetime is an
independent FRET observable (a shorter donor lifetime = higher FRET), and the
lifetime-vs-efficiency relation separates static FRET (on the static-FRET line
$\tau = \tau_0(1-E)$) from dynamic averaging (off the line) — the second axis of
multi-parameter fluorescence detection.

Because a burst has few photons, the fit is done by **Poisson maximum
likelihood** rather than least squares.

## In ChiSurf

The `burst_mle_analysis` plugin fits a single lifetime + anisotropy per burst per
detector using tttrlib's C++ maximum-likelihood estimator (the Maus-2001 `2I*`
`Fit23`, and `Fit24`/`Fit25` variants), wrapped by one Qt-free harness:

```python
from chisurf.core.fluorescence.mle import Fit2x, Fit2xSettings, assemble_vv_vh

# the IRF and background belong to the *settings* — they are properties of the
# setup, reused across every burst
settings = Fit2xSettings(dt=micro_resolution_ns, period=laser_period_ns,
                         irf=irf_vv_vh, background=background_vv_vh)
fit = Fit2x(settings)                              # Fit23 by default

# one burst: stack the parallel/perpendicular micro-time histograms
data = assemble_vv_vh(burst_vv, burst_vh)
res = fit.fit(data, initial_values=[2.0, 0.02, 0.38, 1.0])

res.as_dict()              # {'tau': ..., 'gamma': ..., 'r0': ..., 'rho': ...}
res.twoIstar               # the 2I* statistic (lower is better; ~1 per d.o.f. is good)
```

`fit.parameter_names` gives the parameter order for the chosen estimator, and
`res.x` holds exactly those free parameters (four for `fit23`). Derived
quantities are named result columns: `res.r_scatter`, `res.r_experimental`,
`res.converged`, or `res.result(name)` for any column in `res.result_names`.
`res.as_dict()` maps names to values.

The estimator variants differ in what they solve for: **Fit23** (`tau`, `gamma`,
`r0`, `rho`) is the single-lifetime + anisotropy workhorse, **Fit24** fits a
two-exponential decay (`tau1`, `gamma`, `tau2`, `A2`, `offset`), and **Fit25**
selects among four fixed lifetimes. Pass `Fit2xModel.FIT24` / `FIT25` as the
second argument to `Fit2x` to switch; `fit.parameter_names` always reports the
matching parameter order, and `fixed=` pins individual parameters.

The IRF and background can come directly from the non-burst photons (see
[Background rates](15_background_rates.md)); the same harness drives the
pixel-wise image MLE. Batch fits run off the UI thread and export per-burst
tables that open in ndxplorer.

### The Burst MLE tool

**Spectroscopy ▸ Single-Molecule ▸ Burst MLE**, or step *6. Burst MLE* of
**Spectroscopy ▸ Burst Analysis**. Tabs: **Detector Definition**, **Burst
Files** (`.bur` tables), **IRF Files**, **Background Files** and
**Burst-MLE**. The Burst-MLE tab holds the file and **Detector**, the fit
**Range** (micro-time channels after binning), **Min photons**, the collapsed
*IRF (shift · threshold · range)* and *Shift · scatter · G/l1/l2* groups, and
*Fit parameters*: the **Model** (Fit23/24/25, tail fit), **Split by H2MM
state** with its own **min ph.**, **BIFL scatter**, **2I\*: P+2S**, **Save
VV/VHs**, and per parameter an initial value, a fix box **F** and the fitted
value. **⚡ Auto** picks the micro-time binning and fit window, **✨ Auto IRF**
estimates a Gaussian IRF and background from the non-burst photons; **🎯 Opt**
optimises; **▶** runs the batch over all bursts.

```{figure} figures/21_burst_mle.png
:name: fig-21-burst-mle
:width: 100%

Burst MLE on `m000.bur` of the BH SPC-132 sample folder (green = routing
0/8, red = 1/9), after **Auto IRF**: binning 32, window 15–116, and a Fit23 of
all selected green photons at τ = 2.103 ns (γ, r₀, ρ fixed). Right: the VV|VH
decays (white), the Gaussian IRF (red), the non-burst background (blue) and the
model (green); top, the weighted residuals.
```

The status line says what the Auto IRF did and that a measured IRF/background
gives better lifetimes: the Gaussian stand-in leaves the systematic residual on
the rising edge seen here.

## Result

A single burst carries only ~10³ photons, so its decay is sparse — which is
exactly why the fit is done by maximum likelihood rather than least squares. Read
against the donor-only lifetime $\tau_0$, the per-burst lifetimes separate static
from dynamic molecules.

```{figure} figures/burst_lifetime.png
:name: fig-burst-lifetime
:width: 95%

**Left:** the VV/VH micro-time histograms of one ~2000-photon burst with the IRF
and the reconvolved MLE model. **Right:** the E–$\tau$ plot. Static populations
sit *on* the static FRET line $E = 1-\tau/\tau_0$; a species exchanging between
two states falls on the **dynamic line**, which bows to the right because the
decay reports the intensity-weighted lifetime while $E$ follows the
species-weighted one.
```

## Splitting a burst by H2MM state

A burst that changes conformation part-way through has no single lifetime: fit
all its photons together and you get a blend that belongs to neither state. On
synthetic bursts holding a 3.6 ns and a 1.0 ns population, the all-photon fit
lands at 2.2 ns — a number nothing in the sample has.

Tick **Split by H2MM state** and each burst is additionally fitted once per
Viterbi state, using the same IRF, background and model as the ordinary fit. It
needs a segmentation in the same analysis folder (step 7, *Burst segmentation
(H2MM)*); without one the option says so and the batch proceeds normally.

In the burst workflow this is step 8, **Burst segment MLE**: the same wizard as
step 6 with the box already ticked, placed *after* the segmentation it consumes.
The control is shown only there — on step 6 it offered an option whose input did
not exist yet. Run standalone, the checkbox is always available.

The results are extra **columns on the same burst row** — `Tau S0 (green)`,
`Tau S1 (green)`, … beside the all-photon `Tau (green)`. That is deliberate and
it is the only shape that works: a burst table has one row per burst, every
companion is merged onto it by position, and the number of dwells varies from
burst to burst. **A sub-population is a column, not a row.** The burst stays the
unit of observation; the state is a label on the photons inside it.

Two practical points:

* A burst split by colour *and* state holds far fewer photons than the whole
  burst, so the per-state passes have their own **min ph.** floor. Below it the
  row is still written, with the photon counts and an empty fit — never omitted,
  because a missing row would shift every later burst against the `.bur` grid.
* Photons H2MM did not assign to any state (outside a burst, or dropped by its
  stream definitions) take part in the all-photon fit only.

## The lifetime of a state, not of a burst

A single burst's state holds tens of photons, so its per-burst lifetime is a
noisy number — useful as a distribution, not as a value to quote. The run
therefore starts by pooling: every burst's photons of state *i*, over the whole
measurement, added into one decay per detector, fitted once with the same model,
IRF and background. That is **the** lifetime of the state, and it is written to
`Info/state_lifetimes.csv` beside the analysis:

| Detector | Colour | State | Photons (parallel) | Photons (perpendicular) | Photons | Tau | 2I* | … |
|---|---|---|---|---|---|---|---|---|

One row per *state* — which is why it is a plain CSV in `Info/` and not a `…4`
companion. A companion carries one row per burst and is merged onto the burst
table by position; this table would misalign every burst after the first.

The pooled fit also runs **first**, and each state's fitted lifetime becomes the
start value for that state's per-burst fits. Started instead from the panel's
single guess, every state is pulled toward the same answer — the thing the split
exists to tell apart.

```{note}
Pooling only helps when the model describes the data. The pooled decay has tens
of thousands of counts, so a systematic mismatch that a 300-photon burst cannot
see — a shifted IRF, a decay that does not wrap into the excitation period —
shows up as a biased τ rather than as noise. If the pooled τ and the median
per-burst τ disagree strongly, look at the IRF before believing either.
```

## See also

- `chisurf/plugins/burst/burst_mle_analysis/`, `chisurf/core/fluorescence/mle/`.
- The ensemble decay fit: [Lifetime & anisotropy](10_lifetime_anisotropy_fitting.md).
- The same estimator per pixel: [confocal scan images](24_scan_images.md).
- Where the IRF and background come from: [background rates](15_background_rates.md).
- Concept: {ref}`concept-tcspc-lifetime`.
