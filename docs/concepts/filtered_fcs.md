---
type: Concept
title: Filtered FCS (fFCS/FLCS) and 2D-FLCS
description: Ordinary FCS correlates the total intensity in each detection channel.
tags: [concepts, fcs, filtered]
anchor: concept-filtered-fcs
---

(concept-filtered-fcs)=
# Filtered FCS (fFCS/FLCS) and 2D-FLCS

Ordinary FCS ({ref}`concept-fcs-correlation`) correlates the *total* intensity in
each detection channel. When two species share the same diffusion time — or when
a detector artefact rides on top of the real signal — the plain autocorrelation
cannot tell them apart. **Filtered FCS** uses the extra information hidden in the
**micro-time (TCSPC) dimension**: every photon carries a nanosecond arrival time
relative to the excitation pulse, and different species leave different micro-time
*fingerprints* (their fluorescence-decay patterns). From those patterns one builds
per-photon **statistical weights** and correlates the *weighted* photon streams,
so the resulting curves are species-selective.

The technique appears under several names for the same idea: **FLCS**
(fluorescence-lifetime correlation spectroscopy, {cite}`boehmer2002,kapusta2007`) when
the fingerprint is a lifetime pattern, **fFCS / species-FCS** ({cite}`felekyan2012`) in
the multiparameter (MFD) setting where the pattern may also encode polarisation or
spectrum, and **2D-FLCS** ({cite}`ishii2013`) for the two-dimensional
lifetime–lifetime extension.

For the step-by-step workflow in ChiSurf, see the guide
{doc}`/guides/17_filtered_fcs`.

## The idea: correlate weighted photons, not raw intensity

Suppose the sample contains $s = 1\dots K$ components, each with a known,
normalised micro-time pattern $p_s(t)$ (a fluorescence decay over TAC bins $t$).
Any measured photon at micro-time $t$ could have come from any component; the
best we can do is assign it a *weight* — a **filter value** $F_s(t)$ — that says
how much this photon should count towards component $s$. If we then correlate two
weighted streams,

$$
G_{ij}(\tau) \;=\;
\frac{\big\langle\, w_i(t_0)\, w_j(t_0+\tau) \,\big\rangle}
     {\langle w_i\rangle\,\langle w_j\rangle},
\qquad w_s = F_s\!\big(t_{\text{photon}}\big),
$$

we recover the **species auto-correlations** $G_{ii}$ and **species
cross-correlations** $G_{ij}$ — the correlation functions we *would* have measured
had we been able to detect each component separately. The filters are designed so
that this holds on average.

## The weighted pseudo-inverse filter

The filters are the **weighted least-squares** solution to "reconstruct the total
decay as a mixture of the patterns". Collect the normalised patterns as columns of
a matrix $D$ (rows = micro-time bins, columns = species) and let $I(t)$ be the
measured total decay. Weighting each bin by its Poisson variance $\propto I(t)$
gives the diagonal weight $W = \mathrm{diag}(1/I)$, and the filter matrix is the
weighted pseudo-inverse

$$
\boxed{\;F \;=\; \big(D^{\mathsf T} W D\big)^{-1} D^{\mathsf T} W\;}
$$

Each row $F_s(t)$ is one species' filter over the micro-time axis. The filters are
*not* probabilities — they can go negative — but they obey the defining
orthogonality relation

$$
\sum_t F_s(t)\, p_{s'}(t) \;=\; \delta_{s s'},
$$

so a photon stream that is purely species $s'$ carries unit average weight under
$F_{s'}$ and zero average weight under every other filter. A long-lifetime filter
up-weights late micro-time channels and down-weights early ones; a short-lifetime
filter does the opposite. Feeding the per-photon weights $w_s(t)$ into a multi-tau
correlator then yields the species auto- and cross-correlations directly.

**Empty bins.** A micro-time bin where the measured total decay is zero has no
defined weight $1/I(t)$. There are two conventions, selected by `empty_bins` in
`calc_ffcs_filters`, and PAM uses both:

- `"unit_weight"` (the default; PAM's BurstBrowser fFCS) sets $I(t)=1$ there and
  keeps every bin. The orthogonality relation holds over the whole micro-time axis.
  The catch is that an empty bin then carries the *largest* weight any bin can have
  (the same as a one-photon bin), so where a pattern still has weight on empty bins
  — a decay gated to a PIE window, say, against an ungated pattern — the filters
  are shaped by bins that hold no photons.
- `"exclude"` (PAM's main-window fFCS) leaves empty bins out: $D$, $W$ and the
  pattern normalisation are taken over the occupied bins, and the filters are zero
  on the empty ones. The relation holds on the occupied bins, with each species
  scaled by its pattern fraction there — a factor that cancels in the normalised
  correlation.

The two agree exactly when no bin is empty. ChiSurf reproduces each PAM routine
to $10^{-15}$ relative (A/B test `test/fitting/test_fcs_filters.py`).

**Several detectors.** Parallel and perpendicular (or any set of) detection
channels can share one filter by concatenating their decays and patterns on a
single micro-time axis. The patterns are then normalised over all channels
together, so the filter also uses each species' intensity *ratio* between the
channels — its anisotropy, say — as contrast, not only the decay shape.

## Afterpulse removal with a flat pattern

Detector **afterpulsing** and **dark counts** are uncorrelated with the excitation
pulse, so their micro-time distribution is (to first order) *flat*. Adding a
uniform pattern $p_\text{ap}(t) = 1/N_\text{bins}$ as an extra "species" builds a
filter that soaks up this flat contribution, and the fluorescence filters that
come out are **afterpulse-free** — the classic Enderlein trick that lets FLCS
reach sub-microsecond lag times where afterpulsing would otherwise dominate the
autocorrelation. No second detector or cross-correlation is needed.

## Conditioning: the price of similar patterns

The filter quality is governed by the normal matrix $D^{\mathsf T} W D$. When two
patterns are nearly collinear — e.g. two species whose lifetimes differ by only a
few hundred picoseconds — this matrix is **ill-conditioned**, its inverse is huge,
and the filters become large with alternating signs. Such filters technically
satisfy the orthogonality relation but **amplify shot noise** enormously, so the
species correlations come out noisy. Two levers help:

- a **truncated-SVD** pseudo-inverse (drop near-zero singular values, `rcond`), and
- **Tikhonov / ridge** regularisation, $\big(D^{\mathsf T} W D + \lambda I\big)^{-1}$,
  which trades a little species bias for much lower noise.

The condition number of $D^{\mathsf T} W D$ is a cheap diagnostic: if it is $\gg 1$,
the patterns are too similar to separate cleanly and no amount of correlation time
will fix it.

**Worked numbers.** Two mono-exponential patterns on a 25 ns window with 32 ps
bins, mixed 50:50, with $\tau_1 = 2$ ns fixed and $\tau_2$ varied
(`filter_condition_number` and `calc_ffcs_filters`):

| $\tau_2$ | $\tau_2/\tau_1$ | condition number | largest filter value |
|---|---|---|---|
| 6.0 ns | 3.0 | 4.9 | 3.0 |
| 4.0 ns | 2.0 | 10.2 | 5.6 |
| 3.0 ns | 1.5 | 26.6 | 13.2 |
| 2.5 ns | 1.25 | 82.9 | 34.3 |
| 2.2 ns | 1.1 | 443 | 107 |

The two columns move together, which is the whole story: halving the lifetime
*contrast* from a factor 2 to a factor 1.1 inflates the condition number by ~40×
and the filter amplitudes with it. Because the variance of a filtered correlation grows with the *mean square*
filter amplitude, going from a factor-3 to a factor-1.1 lifetime contrast — a
~35× rise in filter magnitude — costs roughly **three orders of magnitude in
photons** for the same precision.

The practical rule: aim for a lifetime ratio of **at least 1.5** (condition number
in the tens). Below a ratio of ~1.25, regularise (`rcond` or `tikhonov`) and treat
species amplitudes as semi-quantitative; below ~1.1, add a genuinely independent
contrast — polarisation or a spectral channel — rather than pushing the inversion.

## 2D-FLCS: a lifetime–lifetime correlation map

**2D-FLCS** ({cite}`ishii2013`) drops the requirement of *known* patterns and
instead measures, at each correlation lag $\tau$, the **joint distribution of the
micro-time of the first photon and the micro-time of the second photon**:

$$
M(t_1, t_2; \tau) \;=\;
\big\langle\, \delta\!\big(t_1 - t_{\text{photon}}(t_0)\big)\,
             \delta\!\big(t_2 - t_{\text{photon}}(t_0+\tau)\big) \big\rangle .
$$

This 2-D fluorescence-decay correlation matrix is then **inverted** into a
lifetime–lifetime map $P(\tau_1, \tau_2)$ — a distribution over pairs of lifetimes
— using an inverse Laplace transform stabilised by the **maximum-entropy method
(MEM)** or **Tikhonov** regularisation, since the raw inversion is severely
ill-posed. Reading the map:

- **diagonal peaks** ($\tau_1 = \tau_2$) are species that keep their lifetime over
  the lag $\tau$ — static heterogeneity;
- **off-diagonal (cross) peaks** grow with $\tau$ when a molecule *interconverts*
  between two lifetime states during the lag — dynamic exchange.

Comparing maps at increasing $\tau$ therefore resolves conformational or chemical
**dynamics** and separates them from static heterogeneity, all without a second
spectral or polarisation channel. Once the lifetime species are resolved from the
map, their interconversion kinetics can be read out with the same fFCS filters
above: for a two-state exchange the two species auto-correlations decay and the
cross-correlation is anti-correlated, both with the relaxation rate
$k = k_{12} + k_{21}$.

## See also

- Guide: {doc}`/guides/17_filtered_fcs`; foundational FCS concept:
  {ref}`concept-fcs-correlation`.
- ChiSurf source:
  {src}`chisurf/core/fluorescence/fcs/filtered.py#calc_ffcs_filters` is the
  $F=(D^{\mathsf T}WD)^{-1}D^{\mathsf T}W$ filter itself;
  {src}`chisurf/core/fluorescence/fcs/filtered.py#uniform_pattern` the
  afterpulse removal;
  {src}`chisurf/core/fluorescence/fcs/filtered.py#filter_condition_number` the
  conditioning diagnostic; and
  {src}`chisurf/core/fluorescence/fcs/filtered.py#species_filtered_correlation`
  the weighted correlator. Interactive filter design in the
  `chisurf/plugins/fcs/fcs_filter_calculator/` plugin; 2D-FLCS maps and MEM/Tikhonov
  inversion in the `chisurf/plugins/fcs/flc_2d/` plugin.
- Literature: {cite}`boehmer2002` introduces lifetime-weighted correlation;
  {cite}`kapusta2007` the filter formulation; {cite}`felekyan2012` the species
  auto- and cross-correlations this page derives; {cite}`ishii2013,ishii2013b`
  the two-dimensional extension, principle and application; {cite}`kondo2019`
  the single-molecule application — microsecond-to-millisecond exchange in the
  photosynthetic protein LHCSR1 — that the ChiSurf plugin's original MATLAB code
  was written for.
