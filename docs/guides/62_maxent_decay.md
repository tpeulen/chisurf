# Maximum-entropy decay analysis

This guide runs the **MaxEnt decay** tool to recover a *distribution* of decay
times — or of distances — instead of two or three exponential components. The
theory is in {ref}`concept-maximum-entropy`.

**Open it:** *Tools ▸ Fluorescence decay ▸ MaxEnt decay*, or `maxent-decay`
from a shell.

Press **Guide** in the tool for a five-step walk through the buttons.

## When to reach for it

Use MEM when you suspect a continuum rather than states: a dye sampling many
environments, a quencher at a range of distances, a disordered chain. Use it
*also* as a check on a discrete fit — if two exponentials fit well and MEM
returns two narrow peaks at the same lifetimes, the discrete reading is safe; if
MEM returns one broad hump, the two "states" were a parameterization of a
continuum ({ref}`concept-tcspc-lifetime`).

Do not use it to squeeze more components out of a decay. It cannot add
information, only choose which of the many fitting answers you are shown.

## Step 1 — decay and IRF

**Refresh** picks up the decay from the current fit; **IRF** selects the
instrument response. MEM fits in convolved space like every other TCSPC
analysis, so both are required.

An instrument response taken on a different day, at a different count rate, or
after an optical adjustment no longer matches the data — and the mismatch does
not raise $\chi^2_r$ visibly, it appears in the recovered distribution as
structure ({ref}`fundamentals-photon-counting`).

## Step 2 — run once, and distrust the answer

Press **Run**. You get a smooth, positive distribution that depends entirely on
the regularization weight $\nu$ you have not chosen yet. That is the honest
state of the result, not a defect: the inversion is ill-posed, so $\nu$ decides
how much structure you are shown.

## Step 3 — choose ν with the L-curve

Press **L-curve**. It sweeps $\nu$ and plots residual norm against solution
norm; the corner — marked automatically
({src}`chisurf/core/math/regularization.py#sample_lcurve`) — is the point past
which more smoothness starts costing real fit quality.

Then check that $\chi^2_r$ at that $\nu$ is still acceptable
({ref}`fundamentals-photon-statistics`). The corner is a heuristic, not a
criterion with a confidence level.

## Step 4 — the step that decides whether you can publish it

Re-run at $\nu$ a factor of two either side of the corner and compare.

| Outcome | Reading |
|---|---|
| Peaks stay put | Real features |
| Peaks move, split or merge | Regularization artefacts |
| A peak sits at the grid edge | Mass the data cannot constrain — widen the grid |
| Structure follows the prior | The prior showing through — change it and re-run |

Nothing in the goodness of fit distinguishes these. Only the sweep does.

Then vary the grid range and spacing, and vary the prior. Two lifetimes closer
than about a factor of two will merge at *any* $\nu$ — that information is not
in the data, and no regularization recovers it.

## Step 5 — FRET mode

**FRET** mode recovers $p(R)$ directly on a distance grid, using the same solver
with the transfer kernel substituted. It is the model-free counterpart to the
Gaussian and polymer distance models ({ref}`concept-distance-distributions`).

It needs a donor-only reference: **Load donor** or **Load donor fit**. Getting
that reference wrong puts the donor's own heterogeneity into your distance
distribution, which is the most common way a MEM distance result goes wrong.

## Step 6 — uncertainty and export

**Sample** gives the spread on a derived quantity. The MEM result itself is one
distribution at one $\nu$, with no error bars on the bins and strong correlation
between them — so a bin-wise uncertainty is not available and should not be
invented ({ref}`concept-parameter-uncertainty`).

**Save** writes the result out; **JSON settings** edits the run configuration.

## Headless

```python
from chisurf.plugins.fluorescence_decay.maxent_decay.fmem import (
    build_tau_grid,
    run_lifetime_mem_from_arrays,
)

tau = build_tau_grid(tau_min=0.05, tau_max=6.0, tau_bins=192)
result = run_lifetime_mem_from_arrays(
    decay=decay, irf=irf, dt=0.0141, tau=tau, nu=1e-3,
)
print(result["chisq"], result["S"])
```

The same analysis is available as the `maxent-decay` CLI, and the plugin ships
worked notebooks for both modes under `notebooks/`.

## See also

- Concept: {ref}`concept-maximum-entropy` — the entropy functional, the L-curve,
  and what a MEM distribution can claim.
- Fundamentals: {ref}`fundamentals-photon-statistics` (why the width costs far
  more photons than the mean) · {ref}`fundamentals-photon-counting`.
- Guides: {doc}`10_lifetime_anisotropy_fitting` (the discrete fit to compare
  against) · {doc}`03_polymer_distance_distributions` (the parametric
  alternative in FRET mode) · {doc}`39_parameter_uncertainty`.
- Tool: **MaxEnt decay**
  (`chisurf/plugins/fluorescence_decay/maxent_decay/`).
