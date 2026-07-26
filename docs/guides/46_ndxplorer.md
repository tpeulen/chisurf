# Exploring & fitting multidimensional data (ndXplorer)

:::{admonition} Theory
:class: seealso
See {ref}`concept-multidimensional-exploration` for what a burst parameter space
is, why constants are fitting parameters, and how a marginal fit works;
{ref}`concept-accurate-fret` for the static FRET line this guide recovers.
:::

## What it does

ndXplorer is ChiSurf's interactive explorer for tables with many columns — burst
data (E, S, lifetime, brightness, …), imaging-derived parameters, or posterior
draws. You **project** the cloud onto one or two axes, **gate** a sub-population,
**overlay** a parameterised curve on any axis, and **fit** that curve to the
axis's marginal histogram using ChiSurf's own least-squares engine. Constants
(background, detection-efficiency ratios, Förster radius, donor-only lifetime)
are editable `FittingParameter`s that can be linked to a real ChiSurf fit, so the
calibration and the fit stay in sync.

## Launching

ndXplorer runs standalone or connected to a ChiSurf RPC server (the latter
enables the phasor / FRET-line overlays and the analysis
{ref}`bridges <concept-md-bridges>`):

```bash
python -m ndxplorer                              # standalone
python -m ndxplorer --chisurf-rpc localhost:5555 # linked to a ChiSurf server
```

Load an MFD table (a burst `.csv`/HDF5, or a ChiSurf posterior export). Each row
is one burst; each numeric column is a selectable axis.

## Constants: edit, fix/free, and link

The **parameter table** holds the calibration constants as `FittingParameter`s.
Each row has a value, a **fixed** box, and bounds — the same compact fitting-table
widget used across ChiSurf. Editing a value recomputes every derived column live.

To keep one number consistent between a fit and the explorer, **link** a constant
to a ChiSurf fit parameter (for example ndXplorer's `tauD0` to the donor-only
lifetime of a TCSPC {doc}`lifetime fit <10_lifetime_anisotropy_fitting>`). The
linked constant then tracks the fit — re-fit the lifetime and the FRET columns
update. Constants default to **fixed**, so a marginal fit never silently moves
your calibration.

## Overlay a curve and fit the marginal

1. Select an axis (e.g. `E`). Its 1-D marginal histogram is drawn.
2. **Add an overlay curve** and type an expression in `x` — a Gaussian
   `a*exp(-(x-mu)**2/(2*sig**2))`, a sum of two, or any expression the safe
   engine accepts. Undefined names become fittable parameters with sliders.
3. Press **🎯 Fit**. The equation is wrapped in a ChiSurf `ParseModel`, the
   marginal becomes a `DataCurve` with Poisson weights, and the parameters open in
   a fitting-parameter table: free the peak positions/widths/amplitudes, leave
   calibration constants fixed. The fit reports a reduced $\chi^2_r$ and redraws
   the overlay.

The same works headlessly — the button drives exactly this function:

```python
import numpy as np
from ndxplorer.analysis.marginal_fit import bin_centers, fit_equation_to_marginal

counts, edges = np.histogram(E, bins=70, range=(-0.1, 0.9))
x = bin_centers(edges)

res = fit_equation_to_marginal(
    "a1*exp(-(x-m1)**2/(2*s1**2)) + a2*exp(-(x-m2)**2/(2*s2**2))",
    initial={"a1": counts.max(), "m1": 0.05, "s1": 0.03,
             "a2": counts.max() * 0.6, "m2": 0.45, "s2": 0.06},
    x=x, counts=counts.astype(float),
    constant_names=["Bg"],   # any constant in the equation is fixed by default
)
print(res.ok, res.chi2r, res.params["m2"])   # -> FRET peak position
```

For a persistent handle you can edit and re-run (fix/free a parameter, change
bounds, fit again), build a {py:class}`~ndxplorer.analysis.marginal_fit.MarginalFit`
with `build_marginal_fit(...)` and call `.set_fixed(name, True)` / `.run()`.

## Worked example: two smFRET populations and the static FRET line

A mixture of a **no-FRET** species and a **FRET** species is the canonical test.
Simulate each burst's efficiency with binomial shot noise and place it on the
static line $\tau = \tau_0\,(1 - E)$ (see {ref}`concept-accurate-fret`):

```python
rng = np.random.default_rng(3); tau0 = 4.0
N = rng.integers(40, 200, 6000)
Etrue = np.r_[np.full(2400, 0.02), np.full(3600, 0.50)]
E = rng.binomial(N, Etrue) / N
tau = tau0 * (1 - E) + rng.normal(0, 0.05, E.size)
```

Fit the **E marginal** with two Gaussians (the snippet above) — it recovers the
no-FRET peak near $0.02$ and the FRET peak near $0.50$. Fit the **static FRET
line** through both clusters with a one-parameter model:

```python
from scipy.optimize import curve_fit
tau0_fit, _ = curve_fit(lambda t, t0: 1 - t / t0, tau, E, p0=[3.5])
print(tau0_fit)   # -> ~4.00 ns, recovered to <0.1 %
```

```{figure} figures/ndxplorer_marginal_fit.png
:name: fig-ndxplorer-marginal
:width: 100%

Left: every burst lies on the fitted static FRET line $E = 1 - \tau/\tau_0$
($\tau_0 = 4.00$ ns recovered). Right: the E marginal fitted with two Gaussians
via ndXplorer's `fit_equation_to_marginal` engine. The FRET peak (broad) is well
described; the near-zero-efficiency peak is shot-noise-discretised rather than
Gaussian, so its $\chi^2_r$ is elevated — the cue to hand that population to a
{ref}`PDA bridge <concept-md-bridges>` for a shot-noise-aware line shape.
```

## From marginal to full model: bridges

A marginal fit gives peak positions and widths. To resolve the shot-noise
distance distribution ({doc}`PDA <11_pda>`), the multi-exponential donor decay
({doc}`lifetime <10_lifetime_anisotropy_fitting>`) or the diffusion/dynamics
({doc}`FRET-FCS <16_fret_fcs>`) of a gated population, use a **bridge**: gate the
sub-cloud, and ndXplorer resolves the selection to its bursts' photons and starts
the matching ChiSurf fit over the RPC link, overlaying the result back in the
parameter space. See {ref}`concept-md-bridges`.

## See also

- Theory: {ref}`concept-multidimensional-exploration`, {ref}`concept-accurate-fret`.
- `ndxplorer/analysis/marginal_fit.py` (engine); `chisurf/core/expressions.py`
  (safe equation engine); histogram fitting alternative:
  {doc}`FRET-efficiency histogram fitting <29_fret_histogram_fitting>`.
</content>
