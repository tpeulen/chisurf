# Exploring & fitting multidimensional data (ndX)

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
**overlay** a parameterised curve, and **fit** that curve to the data on screen
— the two-dimensional distribution or an axis's marginal histogram — using
ChiSurf's own least-squares engine. Constants
(background, detection-efficiency ratios, Förster radius, donor-only lifetime)
are editable `FittingParameter`s that can be linked to a real ChiSurf fit, so the
calibration and the fit stay in sync.

## Launching

ndX runs standalone or connected to a ChiSurf RPC server (the latter
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
to a ChiSurf fit parameter (for example ndX's `tauD0` to the donor-only
lifetime of a TCSPC {doc}`lifetime fit <10_lifetime_anisotropy_fitting>`). The
linked constant then tracks the fit — re-fit the lifetime and the FRET columns
update. Constants default to **fixed**, so fitting a curve never silently moves
your calibration.

## Overlay a curve and fit it to the data

1. Select the axes. The 2-D distribution is drawn, with a marginal per axis.
2. **Add an overlay curve** and type an expression in `x` — a static FRET line
   `1 - x/tau0`, a Gaussian `a*exp(-(x-mu)**2/(2*sig**2))`, or any expression
   the safe engine accepts. Undefined names become the curve's parameters.
3. They appear in the **same fitting-parameter table** as the constants and as a
   fit's parameters: a value, a **fixed** box and bounds per row, editable with
   the wheel, and a right-click **link** menu. Linking a curve parameter to a fit
   (a FRET line's `tau_d0` to a measured donor lifetime) makes the drawn line
   follow that fit.
4. Press **🎯 Fit** and choose what to fit against: the **displayed data**
   (each populated x column of the 2-D histogram contributes its count-weighted
   mean y, weighted by its standard error) or an axis **marginal** (bin counts
   with Poisson weights). Free parameters are optimised, fixed ones held —
   including constants and linked parameters, whose values belong elsewhere. The
   fit reports a reduced $\chi^2_r$ and redraws the overlay.

The same works headlessly. Fit a curve to the displayed distribution:

```python
from ndxplorer.analysis.curve_fit import fit_equation_to_histogram

counts, x_edges, y_edges = np.histogram2d(tau, E, bins=(60, 60))
res = fit_equation_to_histogram(
    "1 - x/tau0", {"tau0": 3.5}, counts, x_edges, y_edges,
)
print(res.ok, res.chi2r, res.params["tau0"])   # -> the static-line lifetime
```

...or to a marginal, which is the same engine over 1-D counting data:

```python
import numpy as np
from ndxplorer.analysis.curve_fit import bin_centers, fit_equation_to_marginal

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

### Curves that trace a line rather than evaluate one

The predefined FRET lines are not `y = f(x)`: they sweep a mean distance and
return the `(tau, E)` pair of arrays they trace out. Those have no `ParseModel`,
so they are optimised through the function itself — for a trial set of
parameters the line is traced, sorted by x and interpolated onto the data, giving
one residual per point the line spans. Parameters named `num_points` (and the
like) set the curve's *resolution*, not its shape, and start fixed.

Two warnings that fall out of this, and are the reason the **fixed** box matters:

- A traced line can be **degenerate**. The Gaussian-distribution static line
  depends on the Förster radius and the distribution width only through their
  *ratio* (the distance axis scales with $R_0$), so fitting both recovers the
  ratio and an arbitrary pair — $R_0 = 29\,\text{Å}, \sigma = 4.2\,\text{Å}$
  fits a line generated with $55$ and $8$ just as well. Fix $R_0$ at the value
  your dye pair gives and the width comes back right ($\sigma = 7.96$ for a
  truth of $8$, with $\tau_{D0} = 3.50$ for $3.5$).
- The line only constrains where it *is*. Data beyond the traced span
  contributes nothing, which is a feature — but a start so far off that the line
  misses the cloud entirely has no gradient to follow. Drag the parameters until
  the overlay is near the data, then fit.

For a persistent handle you can edit and re-run (fix/free a parameter, change
bounds, fit again), build a {py:class}`~ndxplorer.analysis.curve_fit.CurveFit`
with `build_marginal_fit(...)` / `build_histogram_fit(...)` and call
`.set_fixed(name, True)` / `.run()`. `seed_from_group(curve.parameter_group)`
takes the values, bounds and fix/free straight from the curve's own table, and
`write_back(...)` returns the result to it.

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
line** through both clusters with a one-parameter model — the overlay's own
**🎯 Fit**, against the displayed data:

```python
counts, x_edges, y_edges = np.histogram2d(tau, E, bins=(60, 60))
res = fit_equation_to_histogram("1 - x/tau0", {"tau0": 3.5},
                                counts, x_edges, y_edges)
print(res.params["tau0"])   # -> ~4.00 ns, recovered to <0.1 %
```

```{figure} figures/ndxplorer_marginal_fit.png
:name: fig-ndxplorer-marginal
:width: 100%

Left: every burst lies on the fitted static FRET line $E = 1 - \tau/\tau_0$
($\tau_0 = 4.00$ ns recovered). Right: the E marginal fitted with two Gaussians
via ndX's `fit_equation_to_marginal` engine. The FRET peak (broad) is well
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
- `ndxplorer/analysis/curve_fit.py` (engine); `chisurf/core/expressions.py`
  (safe equation engine); histogram fitting alternative:
  {doc}`FRET-efficiency histogram fitting <29_fret_histogram_fitting>`.
</content>
