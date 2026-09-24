---
type: Concept
title: Interactive multidimensional exploration
description: 'Reading a measurement that has many parameters per molecule or per pixel: multi-dimensional histograms, gating, and the projections that make a population visible.'
tags: [concepts, multidimensional, exploration]
anchor: concept-multidimensional-exploration
---

(concept-multidimensional-exploration)=

# Interactive multidimensional exploration

A single-molecule or imaging measurement does not hand you a curve. It hands you
a *table*: one row per burst (or per pixel, per molecule, per posterior draw)
and a dozen columns — FRET efficiency, stoichiometry, donor lifetime,
anisotropy, brightness, duration, arrival time. Every scientific question about
that table is a question about a **projection** of it: which populations exist,
where they sit, how a gate in one projection reshapes another. This is what
ndX is for, and this page explains the ideas that make its projections
*quantitative* rather than merely pretty — the derived-parameter equation engine,
constants that are real fitting parameters, and fitting a model to a marginal.

The theory of the individual observables lives elsewhere: see
{ref}`concept-smfret-bursts` for burst FRET, {ref}`concept-accurate-fret` for the
correction factors and the static FRET line, {ref}`concept-tcspc-lifetime` for
the donor lifetime, and {doc}`parameter uncertainty <parameter_uncertainty>` for
posterior draws.
This page is about the *space* those observables define and how you interrogate
it. The {doc}`workflow guide </guides/46_ndxplorer>` shows the buttons.

## A measurement is a point cloud

Write each row of the table as a point $\mathbf{p} = (p_1, \dots, p_d)$ in a
$d$-dimensional **parameter space**. A structurally and photophysically
homogeneous population is a *blob* in that space — a cluster whose position
encodes the physics (a mean FRET efficiency, a lifetime) and whose spread encodes
noise and heterogeneity. Two states appear as two blobs; exchange between them
smears the density along the line that joins them.

You never see the whole cloud at once. What you see are **marginals** — the cloud
projected onto one axis (a 1-D histogram) or two (a 2-D histogram, the familiar
E–S or E–τ plot). A marginal is an integral: the 1-D marginal of axis $j$ is

$$
h_j(v) = \int \rho(\mathbf{p})\,\delta(p_j - v)\,\mathrm{d}\mathbf{p},
$$

the density $\rho$ summed over every other axis. This is why gating matters. When
you restrict the cloud to a sub-region — brush a rectangle on the E–S plot, keep
only bursts with stoichiometry near $0.5$ — every *other* marginal is recomputed
from the surviving points. A shoulder on the lifetime axis that was hidden under
a donor-only population appears the moment that population is gated out. **The
selection is the analysis**: choosing the sub-cloud is how you isolate the
species you will then quantify — by fitting its marginal here, or by handing it
to a full model through a {ref}`bridge <concept-md-bridges>`.

(concept-md-playback)=
## Time is a column, and a static plot integrates it away

One of those axes is special, because it is not a property of the molecule: the
**macro time** at which each burst was detected. A single-molecule measurement is
a time series of burst events, and the marginal above is an integral over the
whole acquisition. If $\rho$ depends on time — the sample photobleaches,
aggregates, sediments, or the alignment drifts — then

$$
h_j(v) = \int_0^{T} \!\!\int \rho(\mathbf{p}, t)\,\delta(p_j - v)
         \,\mathrm{d}\mathbf{p}\,\mathrm{d}t
$$

averages that dependence away, and the plot of a drifting sample is
indistinguishable from the plot of a stable one with broader populations.

Restricting to a slice $[t_i, t_{i+1})$ recovers it, and stepping the slice makes
the change visible as motion rather than as broadening. The same gate answers two
different questions depending on where its lower edge sits:

- a **window**, $t_i \le t < t_{i+1}$, shows the population as it was *then* — the
  instantaneous $\rho(\mathbf{p}, t)$, at the cost of the counts in one slice;
- an **integral**, $t < t_{i+1}$, shows everything acquired so far. It converges
  to the static plot, and watching it converge is what distinguishes a population
  that was there from the start from one that only arrives late — both of which
  look identical in the final histogram.

Nothing about this is specific to time. It is a one-dimensional gate that steps,
so any column can drive it; a frame index does exactly the same thing for an
image stack, one frame per step. See the
{doc}`playback controls <../guides/46_ndxplorer>`.

## Derived parameters: the columns are computed, not stored

Most of the interesting axes are not measured directly. A burst measures *photon
counts* in a few detection channels; the FRET efficiency, the stoichiometry, the
donor lifetime are **derived** from those counts and from calibration constants.
ndX computes every derived column from a small set of **equations** over
the raw columns and a table of named **constants** — background rates, detection
efficiency ratios, quantum yields, the Förster radius, the donor-only lifetime:

$$
E \;=\; \frac{F_A/(\gamma\,F_D)}{1 + F_A/(\gamma\,F_D)},
\qquad
F_D = S_{GG} - \mathrm{Bg}_{GG}, \quad F_A = S_{GR} - \mathrm{Bg}_{GR} - \dots
$$

where $S_{\bullet}$ are the raw signals and $\mathrm{Bg}$, $\gamma$, $g_G/g_R$,
$\Phi_A/\Phi_D$, $R_0$, $\tau_{D(0)}$ are the constants. Change a constant and
every dependent column recomputes, live. The calibration *is* the physics that
turns counts into efficiencies, and keeping it as an explicit, editable equation
means the transform is inspectable rather than baked into a loader.

### A safe expression engine

Those equations are user-editable text, so they cannot be handed to Python's
`eval`. ChiSurf provides a shared **safe expression engine**
({src}`chisurf/core/support/expressions.py`) that ndX uses when present: it parses an
expression to an abstract syntax tree and walks it against an explicit
**allow-list** of node types, functions (`exp`, `sqrt`, `log`, trigonometry, …)
and constants ($\pi$, $e$). A name that is not a known column, a listed function
or an allowed constant is either flagged as an error or *discovered as a new
parameter* — never executed. The same validated formula that draws an overlay
curve therefore also drives its fit, with no second, differently-behaved parser.
The engine is documented for the wider codebase; it also backs the TCSPC/FCS
formula ("parse") models.

## Constants are fitting parameters

Here is the design decision that connects exploration to fitting. ndX's
constants are not bare floats. They are ChiSurf **`FittingParameter`s**, rendered
in the same fitting-parameter table used everywhere else in ChiSurf: each carries
a value, a **fixed/free** flag, and **bounds**. A constant you are confident about
(the Förster radius from the literature) stays fixed; one you want to determine
from the data (a background rate) can be freed.

Because they are real `FittingParameter`s, a constant can be **crosslinked** to a
parameter in an actual ChiSurf fit. Link ndX's $\tau_{D(0)}$ to the
donor-only lifetime returned by a TCSPC {ref}`lifetime fit <concept-tcspc-lifetime>`,
and the calibration follows the fit: re-fit the lifetime and every FRET column in
the explorer updates. There is then *one* source of truth for that number instead
of a value typed into two places that silently drift apart. The link is a
directed edge in ChiSurf's parameter graph, the same machinery global fits use to
share a parameter across datasets.

## Fitting a marginal

An overlay curve on an axis is a parameterised function $y = f(x;\,\theta)$ — a
Gaussian, a sum of Gaussians, any expression the safe engine accepts. Once you
can draw it you want to **fit** it to the marginal histogram, and ndX does
this by reusing ChiSurf's fitting stack rather than a bespoke optimiser: the
equation becomes a ChiSurf `ParseModel`, the histogram (bin centres → counts)
becomes a `DataCurve` with Poisson counting weights
$\sigma_i = \sqrt{\max(N_i, 1)}$, and ChiSurf's bounded least-squares `Fit`
minimises

$$
\chi^2(\theta) = \sum_i \left(\frac{N_i - f(x_i;\theta)}{\sigma_i}\right)^2 .
$$

The model's parameters *are* the fitting group. This is where the "constants are
fitting parameters" idea pays off:

- **Free parameters are optimised** — the peak positions, widths and amplitudes
  you actually want from the marginal.
- **Constants join the fit fixed by default** — a background level or a Förster
  radius that appears in the equation is held at its calibrated value unless you
  free it, so a marginal fit cannot silently drift your calibration.
- Every parameter shows its own fix/free box and bounds in the table, and the fit
  reports a reduced $\chi^2_r$.

An elevated $\chi^2_r$ is information, not a failure: a two-Gaussian fit of a FRET
histogram with a near-zero-efficiency population fits the broad FRET peak well
but the low-E peak poorly, because at $E\approx 0$ with tens of photons the
acceptor count is a small integer and that cluster is shot-noise-discretised
rather than Gaussian. The honest description of a shot-noise line shape is a
{ref}`PDA model <concept-pda2c>` — which is exactly the kind of quantitative model a
{ref}`bridge <concept-md-bridges>` hands the gated population off to.

(concept-md-2d-gaussians)=

## Fitting the map itself: 2-D Gaussians

A marginal is a projection, and two populations that overlap in $E$ may be well
separated in $S$. Fitting the **two-dimensional** distribution keeps that
information: each population is a 2-D Gaussian with a centre $\boldsymbol\mu$, a
covariance $\Sigma$ and a weight, and the mixture is fitted by
expectation–maximisation over the *bursts* inside the displayed range — not over
the binned image, so the answer does not depend on the binning you happen to be
looking at.

The covariance is parameterised as it is read: two widths and a correlation,
$\Sigma = \begin{pmatrix}\sigma_x^2 & \rho\,\sigma_x\sigma_y\\
\rho\,\sigma_x\sigma_y & \sigma_y^2\end{pmatrix}$, with $\rho$ the tilt of the
population's ellipse. On a logarithmic axis the fit is done in $\log$ space and
the result mapped back, so a population that is log-normal in, say, burst
duration is described by a Gaussian where it *is* one.

The six numbers of each component are `FittingParameter`s, in the same table as
everything else, which has two consequences beyond a nicer widget:

- **Holding is the ordinary *fixed* flag.** Click a peak where you know it is
  (the donor-only corner at $E \approx 0$) and hold its centre while its width
  and weight are fitted — the EM applies the constraint inside the M step, so the
  held value is not merely restored afterwards.
- **A component can be crosslinked.** Pin one population's centre to a parameter
  of an actual fit, or pin two populations' widths to each other to test whether
  a mixture is consistent with a single shared width. A linked parameter is held
  by the fit and never written back: its value belongs to the master it follows,
  and the ellipse on the map moves when *that* moves.

A fitted component is also a **gate**: its $n\sigma$ ellipse becomes a selection,
and the bursts inside it are what a {ref}`bridge <concept-md-bridges>` hands to a
quantitative model.

(concept-md-ranking)=

## Which two parameters to look at: ranking the views

A burst table with forty parameters holds 780 two-parameter plots, and the one
that shows the populations is rarely the first one tried. **Find informative
projections** scores every pair (and every candidate third axis) and lists them
best first, in the background, so the plots worth looking at are found rather
than hunted for. The design is Orange3's *VizRank*; a **Rank by** switch picks
one of three questions, and every score is computed on one random sample of the
bursts (5 000 by default), identical for every view.

**Separation** (the default). In smFRET the informative view is the one where
the molecules fall apart into species — donor-only, acceptor-only and FRET
populations in $E$ vs $S$, a dynamic population off the static FRET line in $E$
vs $\langle\tau_{D(A)}\rangle_F$ or in the variance plot — not the one where two
parameters co-vary. The bursts of a view are binned on a $64\times64$ raster
and smoothed with a Gaussian of width $0.125\,n^{-1/6}$ of the axis range
(about 0.6 of Scott's rule, which oversmooths multimodal clouds). Every cell
climbs to its highest neighbour, so each density peak collects a basin; merging
basins from the highest saddle down — the elder rule of 0-dimensional
persistent homology (Edelsbrunner, Letscher & Zomorodian,
[10.1007/s00454-002-2885-2](https://doi.org/10.1007/s00454-002-2885-2)) — pairs
every peak but the highest with the valley that separates it from a denser one.
A split counts, and its two sides become separate **islands**, when the valley
is significant against the Poisson noise of the smoothed counts,
$(f_{peak} - f_{saddle}) / \sqrt{\mathrm{var}_{peak} + \mathrm{var}_{saddle}} \geq 3$,
and the smaller side holds at least 3 % of the bursts. The score is

$$\mathrm{sep} = \sum_{i \neq j} p_i\, p_j\, \left(1 - \frac{f_{ij}}{\min(f_i, f_j)}\right),$$

with $p_i$ the share of the sampled bursts in island $i$'s **core** (above its
highest valley to any other island: bursts on a bridge, in a tail or in the
noise do not count), $f_i$ its peak and $f_{ij}$ the saddle between two
islands. It is the chance that two bursts drawn at random sit in two different,
clearly separated islands: 0 for one population however elongated, skewed or
correlated, 0.5 for two equal islands with empty space between them, 0.18 for a
10 % island off a 90 % blob, 0.67 for three equal islands.

Each axis is prepared as the calibration prepares its gating dimensions: values
the axis cannot draw are missing (non-positive on a log axis); an exact value
holding at least 2 % of the bursts and ten times the typical count is a fit
sentinel or bound (`-1` where a channel was not fitted) and is missing too;
counted or rounded values are spread over their step, so integers are not a comb
of "populations"; outliers are fenced per dimension (the 2.5–97.5 % quantiles
widened by their spread); and only then is the axis mapped onto its robust
0.5–99.5 % range. The score is therefore invariant to each axis' units. Shot noise
widens low-photon bursts, which fill the valleys; the ranking can weight bursts
by their photon count or keep only bursts above a photon threshold. Parameters
that cannot show molecules apart are set aside before any pair is scored: flags
(fewer than 20 values), the acquisition clock (a column that rises from row to
row), and *folds* — a many-to-one function of another parameter, such as
$(1-E)E$ of $E$, which piles density up where it folds. Parameters that are the
same quantity (Spearman $|\rho| \geq 0.98$, or each a function of the other, as
the proximity ratio and $E$) are ranked once. A pair in which one axis is a
function of the other (correlation ratio $\eta^2 \geq 0.95$ on ranks) is a curve,
not a cloud, and is not ranked.

Why a density valley: on the MFD and ALEX test tables, HDBSCAN per pair agreed on
synthetic splits but was about eight times slower and cut uniform acquisition
times and photon counts into clusters, and a Gaussian-mixture BIC gain calls any
skewed or curved single population (a log-normal count rate, a banana) three
components. The valley score costs about a millisecond per pair.

**Correlation.** Spearman's $\rho$ of the pair (Orange3's correlation ranking),
over the same columns: it finds parameters that measure related things — $E$ and
a lifetime, a rate and its count — not populations.

**Classes.** Offered when classes exist — the gate (inside vs outside), each
gate as its own population, the clusters, or a z parameter that holds labels — a
view is good when bursts of one class sit next to each other. For every burst the
$k = 10$ nearest bursts in the view are found and the share $p_o$ with the same
class is averaged (Orange3's scatter-plot score). The table shows it corrected for
chance,

$$\kappa = \frac{p_o - p_e}{1 - p_e}, \qquad p_e = \sum_c p_c^2 ,$$

because a gate holding 5 % of the bursts makes $p_o \geq 0.9$ in *every* view by
the majority class alone. Distances are taken **as the plot draws the axes** —
each axis mapped onto its range, in decades on a log axis. The parameters a gate
is defined on, and any parameter that is a monotone function of one of them
(Spearman $|\rho| \geq 0.98$, e.g. $E_\tau$ from $\tau$), are left out: they
separate their own gate by construction.

In ndX the panel opens from **View ▸ Find informative projections…** (and its
*z axis* entry), below *UMAP*. Clicking a row sets the axes (and the scale they
were scored on); choosing axes by
hand marks the matching row. The workflow is in the
{ref}`guide <ndx-find-projections>`.

(concept-md-bridges)=

## From a selection to a full analysis: bridges

Fitting a marginal answers *where* and *how wide*. It does not answer questions
that need the photons back — the shot-noise-resolved distance distribution
({ref}`PDA <concept-pda2c>`), the multi-exponential donor decay
({ref}`lifetime <concept-tcspc-lifetime>`), the diffusion time and dynamics
({ref}`FRET-FCS <concept-filtered-fcs>`). Those are ChiSurf's job, on the *photon
stream* of the selected bursts, not on a histogram of a derived column.

A **bridge** is the handoff. You gate a sub-population in the explorer; the bridge
resolves that gate to the underlying burst identifiers, pulls their photons, and
starts the corresponding ChiSurf fit — a PDA fit, a lifetime fit, a correlation —
returning its result to be overlaid back in the parameter space. Exploration and
rigorous fitting become one loop: *see* a population, *select* it, *quantify* it,
*overlay* the answer, refine the gate. The mechanics — which identifier a row
carries, how the selection becomes photons, and how the fit is launched over
ChiSurf's RPC link — are in the {doc}`workflow guide </guides/46_ndxplorer>`; the
individual analyses have their own concept pages.

## See also

- Tools in ChiSurf: **ndX** (`chisurf/plugins/ndxplorer/`) is the multidimensional histogram browser these selections are made in.

## References

- {cite}`sisamakis2010` — the multiparameter detection scheme and the correction factors it rests on.
- {cite}`kalinin2010` — photon distribution analysis combined with lifetime, and what each adds.
- {cite}`mcinnes2018` — the embedding used to lay out a many-dimensional burst set in two.
- {cite}`campello2013` — the density-based clustering that finds populations without being told how many; the method is in {ref}`concept-density-clustering`.
