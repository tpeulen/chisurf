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
(`chisurf/core/expressions.py`) that ndX uses when present: it parses an
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

## References

- Sisamakis, E., Valeri, A., Kalinin, S., Rothwell, P. J. & Seidel, C. A. M.
  *Accurate single-molecule FRET studies using multiparameter fluorescence
  detection.* Methods in Enzymology **475**, 455–514 (2010).
- Kalinin, S., Valeri, A., Antonik, M., Felekyan, S. & Seidel, C. A. M.
  *Detection of structural dynamics by FRET: a photon distribution and
  fluorescence lifetime analysis of systems with multiple states.* J. Phys.
  Chem. B **114**, 7983–7995 (2010).
- McInnes, L., Healy, J. & Melville, J. *UMAP: Uniform Manifold Approximation and
  Projection for dimension reduction.* arXiv:1802.03426 (2018).
- Campello, R. J. G. B., Moulavi, D. & Sander, J. *Density-based clustering based
  on hierarchical density estimates.* PAKDD, LNCS **7819**, 160–172 (2013).
</content>
</invoke>
