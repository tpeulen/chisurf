---
type: Concept
title: Distance distributions from the donor decay
description: A single donor–acceptor distance gives a single transfer rate and therefore a single-exponential quenched donor decay.
tags: [concepts, fret, tcspc, decay]
anchor: concept-distance-distributions
---

(concept-distance-distributions)=
# Distance distributions from the donor decay

A single donor–acceptor distance gives a single transfer rate and therefore a
single-exponential quenched donor decay. Real molecules almost never do that:
the linkers are flexible, the molecule is conformationally heterogeneous, or
both. The donor decay in the presence of acceptor then carries information a
steady-state efficiency cannot — not only the *mean* distance but the **width**
of the distribution.

This page covers what that information is, what limits it, and which of
ChiSurf's models to fit. The transfer physics is in
{ref}`fundamentals-energy-transfer`; the decay machinery — reconvolution,
nuisance terms, statistics — is in {ref}`concept-tcspc-lifetime`.

## Why an efficiency is not enough

A steady-state efficiency is one number, so it yields one distance. Since $E(R)$
is steep and non-linear, that distance is not the mean of the underlying
distribution:

$$
\langle E \rangle = \int p(R)\,\frac{R_0^6}{R_0^6 + R^6}\,\mathrm{d}R
\;\neq\; E(\langle R \rangle).
$$

$E(R)$ changes curvature at $R = (5/7)^{1/6}R_0 \approx 0.95\,R_0$: it is
concave below and convex above. So a symmetric $p(R)$ centred beyond
$\approx 0.95\,R_0$ gives $\langle E\rangle > E(\langle R\rangle)$ and
$E^{-1}(\langle E\rangle)$ returns a distance that is too short; centred inside,
the bias reverses and the distance comes back too long. For $R_0 = 50$ Å and a
Gaussian of $\sigma = 8$ Å, $\langle R\rangle = 40$ Å returns 41.4 Å and
$\langle R\rangle = 65$ Å returns 62.9 Å. Nothing in the measurement announces
either.

The time-resolved donor decay does not have this problem. Each sub-population
contributes its own exponential, so the decay is the distribution, weighted
{cite}`grinvald1972`:

$$
I_{DA}(t) = I_{D(0)}(t) \int p(R)\,
            \exp\!\left[-\frac{t}{\tau_{D(0)}}\left(\frac{R_0}{R}\right)^{6}\right]
            \mathrm{d}R .
$$

Fitting this — rather than a sum of free exponentials — is what turns a decay
into a distance distribution, first done for flexible oligopeptides
{cite}`haas1975`.

## What the decay can and cannot resolve

The kernel above is a Laplace-like transform, and inverting it is
ill-conditioned {cite}`istratov1999`. The practical limits, which matter more
than the formalism {cite}`peulen2017`:

- **The mean is easy, the width is not.** Recovering $\langle R\rangle$ needs a
  few thousand photons; recovering the width needs one to two orders of
  magnitude more, and recovering a *shape* (bimodal versus broad-unimodal)
  more again.
- **Distances outside $0.5R_0$–$2R_0$ contribute almost nothing.** A
  sub-population beyond $2R_0$ transfers so little that it is indistinguishable
  from donor-only; one below $0.5R_0$ is quenched so completely that it barely
  emits. A wide distribution is therefore *clipped* by the window, and its
  recovered width is a lower bound.
- **The donor-only decay must be known.** $I_{D(0)}(t)$ enters as a factor, so a
  multi-exponential donor-only decay must be measured on the same construct and
  carried through — not assumed single-exponential. This is the single most
  common way a distance distribution goes wrong.
- **A broad distribution and a distribution of $\kappa^2$ look alike.** Both
  broaden the decay. Bounding $\kappa^2$ from anisotropy
  ({ref}`concept-kappa2-orientation`, {cite}`dale1979`) is what separates them, and ChiSurf can
  fold the $\kappa^2$ spread into the distance distribution explicitly
  ({src}`chisurf/core/fluorescence/general.py#convolve_distance_with_k2_ratio`).

## Choosing what $p(R)$ to fit

The choice is a modelling decision, not a technical one, and it is where the
physics enters. ChiSurf ships four, in increasing amount of assumed structure.

**Gaussian** (`FRET: FD (Gaussian)`). One or more Gaussians in $R$, each with a
mean and a width. Assumes nothing about the polymer, which makes it the default
when the question is "how broad is this?" rather than "which chain model
applies?". Several Gaussians describe discrete conformational states, and the
usual caution applies — two Gaussians will fit a broad unimodal distribution
convincingly. The Gaussian is the form used since the first decay-based distance
distributions {cite}`haas1975`.

**Worm-like chain** (`FRET: FD (Worm-like chain)`). $p(R)$ from a contour length
and a persistence length, the standard model for a semi-flexible chain such as
duplex DNA or an unfolded but stiff peptide; ChiSurf evaluates the analytical
radial distribution of {cite}`becker2010`. Two physical parameters instead of
a free shape, so it is far better conditioned — when the model is right. An
optional linker width broadens the result to account for the dye clouds.

**SAW-ν** (`FRET: FD (SAW-ν)`). A self-avoiding walk parameterized by the RMS
end-to-end distance and the Flory scaling exponent $\nu$
{cite}`flory1949`, in the des Cloizeaux form
$p(R) \propto R^{2+(\gamma-1)/\nu}\exp[-(R/r_0)^{1/(1-\nu)}]$
{cite}`descloizeaux1974` {cite}`zheng2018` with $\gamma = 1.1615$
{cite}`leguillou1980`. This is the model for an intrinsically disordered or
unfolded protein {cite}`obrien2009`, and $\nu$ is the observable worth having:
$\nu \approx 0.59$ is a good solvent (expanded), $\nu \to 1/3$ a poor one
(collapsed globule), $\nu = 0.5$ the theta state
{cite}`hofmann2012` {cite}`schuler2016`. Fitting $\nu$ rather than assuming it
is what makes the measurement a statement about chain–solvent interaction.

**Ising chain** (`FRET: FD (Ising)`). A two-state chain in which a field drives
folded (compact) against unfolded (expanded) segments, with a nearest-neighbour
coupling for cooperativity — the helix–coil model of {cite}`zimm1959` with a
Gaussian bond per residue state, solved by a transfer-matrix product. It gives a
distance distribution that changes shape with the field rather than merely
shifting.

**Discrete rates** (`FRET: FD (Discrete)`) is the degenerate case: fit transfer
rate constants directly, with no distance model at all. Useful when the
distribution is genuinely a small number of states and you would rather not
impose a shape on it.

For the workflow and worked parameter sweeps, see
{doc}`/guides/03_polymer_distance_distributions`.

## The dye is not at the attachment point

Every distance above is between the *dyes*, not between the labelled residues. A
linker places each fluorophore in a cloud of accessible positions several
ångström across, so a measured $\langle R_{DA}\rangle$ and a structural
$C_\alpha$–$C_\alpha$ distance are different quantities and can differ by
nanometres.

This is not a correction to apply afterwards — the cloud has to be modelled, and
its width adds to the measured distribution width. The accessible-volume
treatment {cite}`sindbert2011` {cite}`kalinin2012` and the three distinct
distance measures it produces are in {ref}`concept-accessible-volume`.

## Reading a result

Before believing a recovered width, check in this order:

1. **Is the donor-only reference right?** Fit $I_{D(0)}(t)$ on the same
   construct. A donor whose own decay is multi-exponential and modelled as
   single-exponential puts that heterogeneity into $p(R)$.
2. **Is the width above the $\kappa^2$ floor?** Compute the orientational
   contribution ({ref}`concept-kappa2-orientation`) and compare. A width at or
   below it is not a distance distribution.
3. **Does the fit survive a model change?** If a Gaussian and a worm-like chain
   fit equally well and disagree about the width, the data do not determine the
   width — report that rather than the model that gave the prettier number.
4. **Is the distribution inside the window?** Mass near $2R_0$ is
   unconstrained; the fit will place it wherever the prior or the parameter
   bound allows.
5. **Are the uncertainties from a profile or a chain, not a diagonal?**
   Distribution parameters are strongly correlated with each other and with the
   nuisance terms ({ref}`concept-parameter-uncertainty`).

## See also

- Fundamentals: {ref}`fundamentals-energy-transfer` (the $1/R^6$ kernel and the
  usable window) · {ref}`fundamentals-photon-statistics` (why the width costs so
  many more photons than the mean).
- Guide: {doc}`/guides/03_polymer_distance_distributions`.
- Related concepts: {ref}`concept-tcspc-lifetime` ·
  {ref}`concept-kappa2-orientation` · {ref}`concept-accessible-volume` ·
  {ref}`concept-fret` · {ref}`concept-mfd-fitting`.
- Implementation: IMP.bff model descriptions `tcspc_fret_gaussian`,
  `tcspc_fret_worm_like_chain`, `tcspc_fret_saw_nu`, `tcspc_fret_ising_chain`,
  `tcspc_fret_discrete`, with their editor layouts in
  `chisurf/core/models/views/tcspc_fret_*.view.json`; the $p(R)$ kernels
  {src}`chisurf/core/math/functions/rdf.py`;
  distance/rate conversions
  {src}`chisurf/core/fluorescence/general.py#distribution2rates` and
  {src}`chisurf/core/fluorescence/general.py#gaussian2rates`.
- Literature: {cite}`lakowicz2006`, the chapter on time-resolved energy transfer
  and conformational distributions of biopolymers; {cite}`grinvald1972` and
  {cite}`haas1975` for the method; {cite}`peulen2017` for what a decay can
  resolve; {cite}`schuler2016` and {cite}`obrien2009` for the polymer models;
  {cite}`sindbert2011` for what the linker contributes to the measured width.
