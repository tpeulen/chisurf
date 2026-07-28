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

`fit.parameter_names` gives the parameter order for the chosen estimator. Note
that `res.x` is the *full* tttrlib vector: its leading entries follow those
names, while trailing entries carry derived quantities (for `fit23`, `x[6]` is
the scatter anisotropy and `x[7]` the experimental anisotropy). Use
`res.as_dict()` when you just want the named parameters.

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
needs an H2MM run in the same analysis folder (step 6); without one the option
says so and the batch proceeds normally.

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

## See also

- `chisurf/plugins/burst/burst_mle_analysis/`, `chisurf/core/fluorescence/mle/`.
- The ensemble decay fit: [Lifetime & anisotropy](10_lifetime_anisotropy_fitting.md).
- The same estimator per pixel: [confocal scan images](24_scan_images.md).
- Where the IRF and background come from: [background rates](15_background_rates.md).
- Concept: {ref}`concept-tcspc-lifetime`.
