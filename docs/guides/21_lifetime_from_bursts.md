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
from chisurf.core.fluorescence.mle import Fit2x, Fit2xSettings

fit = Fit2x(Fit2xSettings(dt=micro_resolution_ns, period=laser_period_ns))
tau, r_scatter, info = fit.fit(green_vv_vh_decay, irf, background)
```

The IRF and background can come directly from the non-burst photons (see
[Background rates](15_background_rates.md)); the same harness drives the
pixel-wise image MLE. Batch fits run off the UI thread and export per-burst
tables that open in ndxplorer.

## See also

- `chisurf/plugins/burst/burst_mle_analysis/`, `chisurf/core/fluorescence/mle/`.
- The ensemble decay fit: [Lifetime & anisotropy](10_lifetime_anisotropy_fitting.md).
