---
type: Concept
title: 'Global analysis: one value fitted against all the data'
description: Fitting measurements one at a time lets every fit invent its own value for every parameter — including quantities that are physically the same in all of them.
tags: [concepts, fitting, global-analysis]
anchor: concept-global-analysis
---

(concept-global-analysis)=
# Global analysis: one value fitted against all the data

Fitting measurements one at a time lets every fit invent its own value for every
parameter — including quantities that are physically the same in all of them.
Global analysis ties those together: **one value, determined by all the data at
once**. It is often the only way to pin a parameter that no single dataset can
constrain, and it is what ChiSurf is built around.

This page explains what linking does to the estimation problem and how to read
the result. The [global-analysis guide](../guides/60_global_analysis.md) shows
how to do it, in the GUI and headless.

## The estimator

Suppose $M$ measurements $D_1 \dots D_M$, each with its own model
$m_k(\theta_k)$. Fitted separately, each minimises its own objective and the
total is

$$\chi^2_{\text{sep}} = \sum_{k=1}^{M} \sum_i
  \left(\frac{y_{ki} - m_k(\theta_k)_i}{\sigma_{ki}}\right)^2 ,$$

over $\sum_k \dim\theta_k$ free parameters. Nothing couples the terms, so
minimising the sum is exactly minimising each term — separate fits *are* the
global fit when nothing is shared.

Linking asserts that some components are one quantity. Partition each
$\theta_k = (\phi,\, \psi_k)$ into a **shared** block $\phi$, identical across
the measurements, and a **local** block $\psi_k$. The global objective is the
same sum, minimised over far fewer parameters:

$$\chi^2_{\text{glob}}(\phi, \psi_1 \dots \psi_M) = \sum_{k=1}^{M} \sum_i
  \left(\frac{y_{ki} - m_k(\phi, \psi_k)_i}{\sigma_{ki}}\right)^2 ,
\qquad
\nu = \sum_k n_k - \dim\phi - \sum_k \dim\psi_k .$$

Two consequences follow immediately, and they are the whole point:

- **The fit gets worse; the parameters get better.** $\chi^2_{\text{glob}} \ge
  \chi^2_{\text{sep}}$ always — a constrained minimum cannot beat an
  unconstrained one. What improves is the *precision* of $\phi$, which is now
  informed by every dataset.
- **Degeneracies can break.** A parameter pair that trades off within one
  measurement need not trade off the same way in another. Sharing one member
  across measurements whose local blocks differ turns a valley in one
  $\chi^2$ surface into a minimum in the sum. This is why a donor lifetime
  shared across a FRET series is identifiable when neither dataset alone
  determines it.

In ChiSurf a link is directional: the **follower** is removed from the free
parameter vector and evaluates to its **master**'s value. A chain of links
resolves to the master at its head; a cycle is refused, because it has no
value.

### Uncertainty

The shared parameter's covariance comes from the *joint* Jacobian. For a
Gaussian-error least-squares fit the information adds:

$$\mathcal{I}(\phi) = \sum_{k=1}^{M} \mathcal{I}_k(\phi),
\qquad
\sigma_\phi \;\sim\; \left(\textstyle\sum_k \mathcal{I}_k(\phi)\right)^{-1/2} ,$$

so $M$ equally informative measurements shrink the interval by roughly
$\sqrt{M}$ — the familiar scaling, and the honest reason to do this rather than
average $M$ separately fitted values. Averaging afterwards is not the same
estimator: it weights by each fit's own (possibly degenerate) uncertainty and
cannot break a degeneracy at all. See
[parameter uncertainty](parameter_uncertainty.md) for how the interval itself is
computed.

## What to link, and what not to

Link a parameter when it is a property of the *system or the instrument* rather
than of the individual measurement:

- donor lifetimes across a FRET series measured with the same dye,
- an instrument response shift or colour shift within one session,
- a background or detection-correction factor belonging to one detector,
- a distance or rate the experiment is designed to hold constant.

Do **not** link what the experiment is varying — the concentration in a
titration, the efficiency you are measuring per sample, an amplitude that
reflects how much of each species is present. Linking those manufactures the
answer: the estimator will happily return a precise value for a quantity that
was never common.

### Linking is not fixing

Both remove a degree of freedom, and they say different things:

| | asserts | uses data | keeps its uncertainty |
| --- | --- | --- | --- |
| **fix** | "this value is known" | no | no — treated as exact |
| **link** | "this value is the same everywhere" | yes | yes |

When the reference measurement is itself part of the analysis, link rather than
fix: fixing discards the reference's own uncertainty and reports intervals that
are too narrow. A **prior** is the third option — "approximately known, with a
stated spread" — and is described in
[parameter uncertainty](parameter_uncertainty.md).

## Reading the result

- **The free-parameter count must drop.** If it did not, the link did not take
  effect and the numbers mean nothing.
- **Re-run every fit.** A link changes the objective of *all* the measurements
  it touches, so results computed before it are stale.
- **A small rise in $\chi^2_r$ is expected** — it is the price of the
  constraint. A *large* rise means the parameter is not actually shared, and the
  honest conclusion is that the measurements disagree. Test it: unlink, refit,
  and compare. With $\nu_{\text{glob}} - \nu_{\text{sep}} = (M-1)\dim\phi$ extra
  constraints, an $F$-test on
  $\Delta\chi^2$ says whether the rise is more than noise.
- **State what was linked.** A globally fitted number is meaningless without the
  linking scheme it came from; ChiSurf can save that scheme alongside the
  result.

## Where the structure is visible

The linking scheme is a graph: parameters are nodes, links are directed edges,
and the connected components are the quantities the analysis actually estimates.
ChiSurf's **Global View** draws exactly that graph and lets it be edited — see
the [guide](../guides/60_global_analysis.md). The same information appears as a
table, and both are views of one live state: a link made in either is a link in
the fit.

For the posterior's structure — which parameters the data actually constrains
*jointly*, whether or not they were linked — see
[parameter uncertainty](parameter_uncertainty.md).

## References

- Beechem, J. M. (1992) Global analysis of biochemical and biophysical data.
  *Methods in Enzymology* **210**, 37–54.
  [10.1016/0076-6879(92)10004-W](https://doi.org/10.1016/0076-6879(92)10004-W)
- Knutson, J. R., Beechem, J. M., Brand, L. (1983) Simultaneous analysis of
  multiple fluorescence decay curves: a global approach. *Chemical Physics
  Letters* **102**, 501–507.
  [10.1016/0009-2614(83)87454-5](https://doi.org/10.1016/0009-2614(83)87454-5)
- Beechem, J. M., Ameloot, M., Brand, L. (1985) Global and target analysis of
  complex decay phenomena. *Analytical Instrumentation* **14**, 379–402.
  [10.1080/10739148508543581](https://doi.org/10.1080/10739148508543581)
