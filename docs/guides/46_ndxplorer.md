---
type: Guide
title: Exploring & fitting multidimensional data (ndX)
description: NdX (the ndxplorer package, formerly written out as ndXplorer) is ChiSurf's interactive explorer for tables with many columns — burst data (E, S, lifetime, brightness, …), imaging-derived parameters, or posterior draws.
tags: [guides, fitting, bursts, tcspc, lifetime, imaging]
---

# Exploring & fitting multidimensional data (ndX)

:::{admonition} Theory
:class: seealso
See {ref}`concept-multidimensional-exploration` for what a burst parameter space
is, why constants are fitting parameters, and how a marginal fit works;
{ref}`concept-accurate-fret` for the static FRET line this guide recovers.
:::

## What it does

ndX (the `ndxplorer` package, formerly written out as *ndXplorer*) is ChiSurf's
interactive explorer for tables with many columns — burst
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

(guide-ndx-playback)=
## Play the measurement back

:::{admonition} Theory
:class: seealso
See {ref}`concept-md-playback` for why a static plot cannot tell a drifting
sample from a stable one with broader populations.
:::

Every burst carries the macro time at which it was detected, so a burst table is
a time series and the plot you open is an integral over the whole acquisition.
The **Playback** panel at the top of the plot controls gates the plot on a slice
of one column and steps it. It starts folded — click the header to open it.

Every block of the plot controls folds the same way (**Playback**,
**Histogram**, **z axis**, **Draw Mask**, **Selection**), so the settings you set
once can be put away while you scrub. The panels themselves are drag-and-drop
dock tabs: drop one on an edge of the window to split the layout, or onto another
tab to stack them.

The axis is chosen from the data when a file is loaded — `Mean Macro Time (s)`
for a burst folder, the frame index for an image stack — and any other numeric
column can be picked in the **Axis** combo.

| Control | What it does |
| --- | --- |
| **Steps** | How many slices the range is cut into. The slice width is the range divided by this, so a one-hour and a one-minute measurement take the same time to play. A frame index starts at one step per frame. |
| **Step** | Which slice is on screen. Drag to scrub. |
| ◀◀ ◀ ⏸ ▶ ▶▶ | Step, play, stop. Pressing a play button again stops it; pressing the opposite one reverses. |
| **Mode** | *Window* — one slice, the population as it was then. *Integrate* — everything up to the current step, so a population that arrives late is visible as it arrives. *Stack* — no gating, the whole measurement (how a file opens). |
| **Speed** | Steps per second. A redraw takes a few tens of milliseconds, so above roughly 30 fps steps are dropped rather than shown faster. |

The readout under the controls names the slice and the number of points in it.

Playback is a gate like any other, so every other panel follows it: the marginals,
the 2-D map, a Gaussian fit and a curve fit all see only the surviving points. A
selection added with **➕ select** while a slice is on screen records that slice
as part of the gate, so it keeps meaning the same thing after the playback moves
on.

To watch one population rather than the whole cloud, gate it first and then play:
the marginal of a gated blob over time is the cleanest way to see a state
depopulate.

## Constants: edit, fix/free, and link

The **parameter table** holds the calibration constants as `FittingParameter`s.
Each row has a value, a **fixed** box, and bounds — the same compact fitting-table
widget used across ChiSurf. Editing a value recomputes every derived column live.

To keep one number consistent between a fit and the explorer, **link** a constant
to a ChiSurf fit parameter (for example ndX's `tauD0` to the donor-only
lifetime of a TCSPC {doc}`lifetime fit <10_lifetime_anisotropy_fitting>`). The
linked constant then tracks the fit — re-fit the lifetime and the FRET columns
update. Constants default to **fixed**, so fitting a curve never silently moves
your calibration; free one deliberately and it joins the fit as a
[data parameter](#fitting-a-constant-moving-the-data-onto-the-curve).

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
   (one point per populated x column of the 2-D distribution) or an axis
   **marginal** (bin counts with Poisson weights). Free parameters are
   optimised, fixed ones held — including constants and linked parameters, whose
   values belong elsewhere. The fit reports a reduced $\chi^2_r$ and redraws the
   overlay.

### Fit through the cloud, not through a summary of it

**Fit through** decides what the curve is compared with, and it matters more
than it sounds.

The obvious thing — reduce each x column to one point and fit the curve through
those — cannot describe a **population**. A blob is round: reduced column by
column it becomes a *horizontal streak* across its own columns, and no static
FRET line follows both that streak and the donor-only population further along.
Fitting a real measurement that way put the line beside the population and ended
it a nanosecond past the donor-only cluster.

- **the cloud** (default) fits the curve to the distribution itself. Every
  populated bin pulls on the curve, weighted by what it counted, and a bin more
  than a couple of bins away stops pulling harder — so the curve follows the
  populations and ignores the junk around them. This is what puts a static FRET
  line through the FRET population *and* through the donor-only cluster at its
  end.
- **the population of each column** reduces a column to its densest
  population (the local mode). Useful when the curve really is a function of x
  and you want that reading.
- **the mean of each column** is the plain weighted average, for a distribution
  you know to be single-peaked. Note that the average of a *mixture* lies where
  nothing is — on real data the column mean runs some $0.1$ in $E$ below the
  FRET population's ridge.

**Scan first** (on by default) evaluates a coarse grid over the free parameters
before fitting and starts the fit at the best point, then keeps whichever of
that fit and the fit from your own start ends lower. A least-squares run only
goes downhill from where it starts, and a constant that scales the data against
a curve parameter that scales the model is exactly the degenerate pair that
strands it. See
[finding the minimum](../concepts/parameter_uncertainty.md#finding-the-minimum-before-describing-it).

### Fitting a constant: moving the data onto the curve

Below the curve's parameters the fit dialog shows a second table: nDXplorer's
own constants — the ones an equation actually reads. Freeing one puts it in the
same optimisation, but it does something different there. A constant is not part
of the curve: it is an input of the equations that build the plotted axes, so
moving it moves the **burst population**, not the line. Every step of the fit
re-derives the derived columns and re-reduces them, on the bin edges and columns
the fit started with.

That is how a detection-correction factor is determined in the first place: fix
the static FRET line at the donor lifetime you measured, free `gG/gR`, and the
fit returns the $\gamma$ for which the population sits on the line. The same
works for `alpha`, `beta`, the background rates or `PhiA`/`PhiD`.

Three things worth knowing:

- **It is slower** — a step costs a recompute plus a re-reduction, so this is
  seconds where a curve-only fit is milliseconds. A progress bar with a Cancel
  button runs in the dialog meanwhile; stopping puts every parameter back.
  Only the columns the fit reads (the two plotted axes) are recomputed per step,
  and only the rows visible when it started, which is what makes it seconds
  rather than minutes.
- **The fitted value lands in the Parameters tab**, and the plots — the
  histograms and the overlay curves with them — are rebuilt from the data the
  fit ended on. (A curve is drawn in bin coordinates, so every redraw of the
  histogram redraws the curves over it: they always describe the plot you are
  looking at.) The other derived
  columns, which the fit skipped, are brought up to date in the same breath. The
  constants table and the dialog show the same parameters, so there is nothing
  to copy across.
- **Free one constant at a time.** Calibration factors trade off against each
  other and against the curve's own parameters (scaling the data is nearly the
  same as scaling a slope), so a fit with several freed at once will find *a*
  solution rather than *the* solution. When the factors themselves are what you
  are after, the photon-statistics route in
  {doc}`accurate FRET <41_accurate_fret>` estimates them jointly.

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
so they are optimised through the function itself: for a trial set of parameters
the line is traced, and each data point's residual is its **distance to that
line**, measured in units of the point's own uncertainties (the column width
across, the population's standard error up). Parameters named `num_points` (and
the like) set the curve's *resolution*, not its shape, and start fixed.

A distance rather than a vertical offset, because a traced curve does not span
the whole plot: interpolating it onto the data's x gives a point the line does
not reach *no* residual at all — so the optimiser is rewarded for making the
line **shorter** until it covers only what it already fits, which is exactly
what a static FRET line did. It collapsed to $\tau_{D0} \approx 1$ ns, covering
a third of the columns, and reported a better $\chi^2$ for it.

Fitting the cloud, that same distance is weighted by what the bin counted and
flattens off beyond a couple of bins, and everything pushed *outside* the
plotted range is charged for — otherwise a fit with a free constant has a
trivial way out: shove the population off the axes, and a cloud with nothing in
it matches every curve perfectly.

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

Constants are attached to such a handle as
{py:class}`~ndxplorer.analysis.curve_fit.DataParameters` — the parameters plus
the callback that re-derives the data for them:

```python
from ndxplorer.analysis.curve_fit import DataParameters

def refresh(changed):                 # changed: the names that moved
    recompute_columns(changed)        # ndX: data_source.compute_columns(...)
    return x, y, ey                   # the fit's target, on the same x grid

cf.attach_data_parameters(DataParameters(parameters=[gamma], refresh=refresh))
gamma.fixed = False
result = cf.run()
print(result.data_params["gG/gR"])
```

`refresh` must return the same number of points every time — hold the columns
with `ridge_from_values(..., keep=...)`, which reports an emptied column as
`nan` instead of dropping it. In the GUI that plumbing is
`NDXplorer.build_data_parameters(...)`, and `cf.set_progress(cb)` reports each
step to `cb(step)` — return `False` there to stop the fit.

Three numerical details are load-bearing, and all three are easy to get wrong:

- Reduce the **unbinned** values (`ridge_from_values`), not the y bins. A binned
  column mean only moves when a burst crosses a bin edge, so the optimiser's
  finite difference measures a derivative of exactly zero and the fit returns
  instantly, unchanged.
- Take that difference over a **per-mille step** (`FINITE_DIFFERENCE_STEP`), not
  the default ~1e-8: counting data is discrete, a traced curve is a set of
  points, and a probe that small sees neither move.
- **Freeze the weights.** The uncertainty of a reduced point is estimated from
  the data, so letting it move with the fit hands the optimiser a way to lower
  $\chi^2$ that has nothing to do with the curve — blur the population and every
  residual shrinks. Taken once, at the start, and held (`freeze_weights`).

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

(ndx-gaussian-panel)=

## Fit 2-D Gaussians to the populations on the map

A marginal is a projection: two populations that overlap in $E$ can be well
separated in $S$. The **Gaussian Fit** dock fits the populations in the plane
they are actually separated in. Theory: {ref}`concept-md-2d-gaussians`.

1. Tick **Select point** and click a population on the 2-D map. A component is
   added with its centre at the click and its width estimated from the bins
   around it, and its 1σ / 2σ / 3σ ellipses appear on the map. (**add** puts one
   in the middle of the visible map instead; **del** removes the selected row.)
2. Press **🎯 Fit**. Expectation–maximisation optimises every free parameter
   against the bursts inside the visible range — not against the binned image, so
   the answer does not move when you change the binning.
3. **🔍 Select** turns the chosen rows into $n\sigma$ selections (the **Selection
   σ** box sets $n$), which is how a fitted population becomes a gate a
   [bridge](#from-marginal-to-full-model-bridges) can hand on.

Each Gaussian is six **rows** of the same parameter table used everywhere else in
ChiSurf — centre $x$, $y$, widths $\sigma_x$, $\sigma_y$, correlation $\rho$ and
weight $w$, each with its own value and **Fixed** box. They are stacked rather
than spread across the panel, because six numbers side by side is a dozen columns
and the dock does not have them; a row names the Gaussian it belongs to
($x_1$, $\sigma_{x,1}$, …), and selecting one selects that Gaussian.

- **Hold what you know.** Tick *Fixed* on a centre you placed deliberately — the
  donor-only corner, say — and it is held *inside* the fit, while that
  component's width and weight are still optimised.
- **Link what is shared.** Right-click a cell → **🔗 Link … to** and pin the
  parameter to another one: a parameter of a ChiSurf fit, an ndX constant, or the
  matching parameter of another Gaussian (to test a mixture against one shared
  width). A linked parameter is held by the fit and follows its master, so
  re-fitting the thing it is pinned to moves the ellipse on the map.
- **Bounds are armed** where a value outside them is meaningless ($\sigma \ge 0$,
  $|\rho| \le 1$, $w \ge 0$); their columns are hidden until you press the
  panel's **bounds** button, and a row's **🔍 Details…** always has them.
- **del** and the **Delete** key both remove the selected Gaussian; **💾 Save** /
  **📂 Load** write the components, with their held flags, to JSON/CSV alongside
  the histogram, the model and both marginals.

```{figure} figures/ndxplorer_gaussian_panel.png
:name: fig-ndxplorer-gaussian-panel
:width: 100%

The Gaussian-fit panel after fitting two simulated populations — ChiSurf's
parameter table, stacked one parameter per row so the panel stays narrow. The
second component's centre was held (ticked *Fixed*, greyed out, and returned
unchanged at 0.74) while everything else was optimised onto the data.
```

## From marginal to full model: bridges

A marginal fit gives peak positions and widths. To resolve the shot-noise
distance distribution ({doc}`PDA <11_pda2c>`), the multi-exponential donor decay
({doc}`lifetime <10_lifetime_anisotropy_fitting>`) or the diffusion/dynamics
({doc}`FRET-FCS <16_fret_fcs>`) of a gated population, use a **bridge**: gate the
sub-cloud, and ndX resolves the selection to its bursts' photons and starts
the matching ChiSurf fit over the RPC link, overlaying the result back in the
parameter space. See {ref}`concept-md-bridges`.

## See also

- Theory: {ref}`concept-multidimensional-exploration`, {ref}`concept-accurate-fret`.
- `ndxplorer/analysis/curve_fit.py` (engine); {src}`chisurf/core/expressions.py`
  (safe equation engine); histogram fitting alternative:
  {doc}`FRET-efficiency histogram fitting <29_fret_histogram_fitting>`.
</content>
