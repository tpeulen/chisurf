# κ² distributions: how much is the orientation assumption costing?

Every FRET distance you report assumes an orientation factor, almost always
$\kappa^2 = 2/3$. This guide runs ChiSurf's **κ² Distribution Calculator** to
turn measured anisotropies into the range of distances your data actually
supports. The theory is in {ref}`concept-kappa2-orientation`.

**Open it:** *Tools ▸ Calculators ▸ Kappa2 Distribution*, or
`csg_kappa2_dist` from a shell.

If this is your first time, press **Guide** in the tool for a six-step walk
through the controls.

## What you need first

Three of the four inputs come from ordinary time-resolved anisotropy fits
({doc}`10_lifetime_anisotropy_fitting`):

| Field | Measure it on |
|---|---|
| `r₀ (fund.)` | Your dye, at the excitation wavelength you use |
| `r_D∞` | The donor-only sample |
| `r_A∞` | The acceptor, directly excited |
| `r_AD∞` | The FRET-sensitized acceptor — the hard one |

Leave **r_AD known** unchecked unless you actually measured $r_\infty^{AD}$.
Without it the tool drops the $\delta$ angle and returns a wider bound, which is
the honest answer rather than a falsely tight one.

## Step 1 — establish the worst case

Select **Isotropic** and press **Compute**. No anisotropy inputs are used.

The mean comes back at $2/3$ — the value everyone assumes — but look at the
plot: the distribution is broad and piles up near zero, and **SD R_app/R_DA** is
about 0.24. That is a 24% systematic uncertainty on every distance, from
orientation alone.

This is the reference, not a model of your sample. The point of running it first
is to see that a correct mean says nothing about the spread.

## Step 2 — use your own dyes

Switch to **WIC (Cone)** and enter your measured anisotropies.

```{figure} /guides/figures/kappa2_tool.png
:alt: the kappa-squared distribution calculator with restricted dyes
:width: 70%
:align: center

The calculator with a deliberately restricted pair ($r_{D\infty} = 0.15$,
$r_{A\infty} = 0.20$). Mean $\kappa^2$ is still 0.66 — but **SD R_app/R_DA** is
0.15, so the distance carries a 15% systematic range. The plot shows why: the
distribution is broad, not the sharp spike a mobile pair gives.
```

Now lower `r_D∞` and `r_A∞` toward zero and recompute. The distribution narrows
onto $2/3$ and the distance error collapses to a few per cent. That sweep is the
whole argument for long flexible linkers, and it is worth doing once on your own
numbers rather than taking it on trust.

## Step 3 — read the right number

**SD R_app/R_DA** is the output. Everything else is diagnostic.

| Reading | What it means |
|---|---|
| SD R_app/R_DA < 0.05 | Orientation is not your dominant error. Report it and move on. |
| 0.05 – 0.15 | Real, and worth quoting alongside the distance. |
| > 0.15 | Orientation dominates. Change linkers, or measure $r_\infty^{AD}$ and use $\delta$. |
| Mean κ² far from 2/3 | Check the inputs — a residual anisotropy above $r_0$ is not physical. |
| Result changes with **Bins** | A binning artefact, not a result. |

## Step 4 — when the bound is too wide

Two routes, in increasing cost:

1. **Measure $r_\infty^{AD}$** and tick **r_AD known**. Fixing the angle
   $\delta$ between the dyes tightens the bound substantially, because the first
   two anisotropies constrain how much each dye moves but not how the two are
   oriented relative to each other.
2. **Change the labelling.** A longer or more flexible linker lowers both order
   parameters at the source. The cost is a larger positional uncertainty, which
   the accessible-volume model then has to carry
   ({doc}`23_accessible_volume`).

If you suspect the dye is *sticking* rather than uniformly restricted, use
**DWT (Diffusion)** instead — it models a trapped fraction rather than a cone.
DWT needs the **FRET E** field set to your measured efficiency, because it
averages efficiencies rather than rates; leaving it at the default gives a
meaningless answer.

## Step 5 — export

**Save** writes the κ² histogram as CSV, with the model and the order parameters
in the header comments, so the figure can be redrawn and the provenance is not
lost.

## Headless

```python
from chisurf.plugins.calculator.kappa2_dist.core.algorithms import compute_kappa2_dist

result = compute_kappa2_dist(
    model_type="cone",
    r_0=0.38, r_Dinf=0.15, r_Ainf=0.20, r_ADinf=0.005,
    rAD_known=False,
)
print(result["k2_mean"], result["RappSD"])
```

## See also

- Concept: {ref}`concept-kappa2-orientation` — the models and where $\delta$
  comes from.
- Fundamentals: {ref}`fundamentals-energy-transfer` ·
  {ref}`fundamentals-polarization`.
- Guides: {doc}`10_lifetime_anisotropy_fitting` (measuring the inputs) ·
  {doc}`23_accessible_volume` (the positional half of the same problem) ·
  {doc}`41_accurate_fret`.
- Tool: **Kappa2 Distribution** (`chisurf/plugins/calculator/kappa2_dist/`).
