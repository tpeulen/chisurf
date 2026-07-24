(concept-accessible-volume)=
# Accessible-volume (AV) dye modeling

FRET reports a distance between two **dyes**, but structural modeling needs a
distance between two **atoms** of the biomolecule. Bridging that gap is the job of
the dye and its linker: a fluorophore is coupled through a flexible spacer arm, so
it does not sit at a fixed point — it explores a cloud of positions around its
attachment atom. The **accessible-volume (AV)** model turns that cloud into a
computable object and, from a pair of AVs, into a *model distance* that can be
compared to a measured FRET distance and used as a **restraint** in structural
modeling.

This page explains what the AV *is*, why three different "distances" fall out of a
pair of AVs, and how they become restraints. For the step-by-step workflow and API
in ChiSurf, see the guide {doc}`/guides/23_accessible_volume`. The theory here is
the user-facing rendering of the maintained OKF concept
`okf/references/accessible-volume-theory.md`.

## Why a tethered dye samples a distribution

A dye on a flexible linker has two consequences, and the AV model uses the first
to justify the second:

- **Rotational freedom → $\kappa^2 = 2/3$.** On the fluorescence timescale the
  linker lets the dye reorient over nearly a full sphere, so the transition
  dipoles sample orientations almost isotropically. This is the physical basis of
  the standard orientation-factor assumption $\langle\kappa^2\rangle = 2/3$, which
  removes the unknown mutual dye orientation from the FRET rate.
- **Positional freedom → a spatial distribution.** The same flexibility makes the
  dye's *position* uncertain, so the inter-dye distance is a **distribution**
  $P(R_{DA})$, not a single number.

An explicit all-atom molecular-dynamics simulation would sample this cloud
rigorously but is expensive per site. The AV replaces it with a cheap **geometric**
search that captures the dominant, steric part of the distribution.

## The AV construction — a probe on a leash

The dye plus linker is coarse-grained into a simple probe swept around the
attachment atom:

- the **linker** is a flexible tube of contour length $L_\text{link}$ and steric
  width $W_\text{link}$;
- the **dye** is a soft body approximated by one radius $R_1$ (the `AV1` model) or
  three radii $R_1, R_2, R_3$ for a spheroid (the `AV3` model).

On a grid of spacing $\Delta$ (~0.5–1 Å) around the attachment atom, a point is
*accessible* if the dye centre can reach it via a linker path of length
$\le L_\text{link}$ that does not cut through the biomolecule, and the dye body
does not clash with any atom (each carrying its van-der-Waals radius).
Reachability is a shortest-path flood-fill from the attachment point, so the
linker cannot tunnel through the protein and the cloud hugs the surface rather
than filling a naïve sphere. The result is a **weighted point cloud** — the
allowed grid points $\mathbf{r}_i$ with weights $w_i$.

## The mean dye position

The first quantity read off the cloud is the **mean dye position**, the
weight-weighted centroid:

$$
\mathbf{R}_\text{mp} = \frac{\sum_i w_i\,\mathbf{r}_i}{\sum_i w_i}.
$$

It is the single effective point where the dye sits on average, and it anchors the
fast rigid-body restraints (a docking move only retranslates the mean positions).

## The accessible-contact volume (ACV)

The plain AV assumes the dye samples its whole envelope uniformly. Real dyes with
conjugated $\pi$-systems often **stick** to the surface (base-stacking on DNA,
hydrophobic patches on proteins), which shifts the mean position toward the
surface and shows up as an anisotropy decay that levels off at $r_\infty > 0$.

The **accessible-contact volume (ACV)** splits the AV into a thin **contact
volume** shell of width $W_\text{CV}$ near the surface and the remaining **free
volume**, then places a fraction $w_\text{CV}$ of the weight in the contact shell
and $1 - w_\text{CV}$ in the free volume — so the point weights $w_i$ are no longer
uniform. The contact weight can be estimated from the residual anisotropy
$r_\infty$; setting $w_\text{CV}=0$ recovers the plain AV.

## Three AV-to-distance measures

Two AVs (donor, acceptor) predict a weighted distribution of inter-dye distances:
draw weighted samples $\mathbf{r}_D, \mathbf{r}_A$ with combined weight
$w = w_i^D w_j^A$, each giving $R = \lVert\mathbf{r}_D - \mathbf{r}_A\rVert$. From
this $P(R_{DA})$ come **three distinct scalar distances** — confusing them is the
classic AV pitfall, since they differ by several Å and each answers a different
question.

**1. Distance between mean positions, $R_\text{mp}$:**

$$
R_\text{mp} = \lVert \mathbf{R}_\text{mp}^{D} - \mathbf{R}_\text{mp}^{A} \rVert .
$$

Cheap and geometric, but it ignores the cloud *widths* — a fast proxy (rigid-body
docking), never a direct model of an efficiency.

**2. Mean inter-dye distance, $\langle R_{DA}\rangle$:**

$$
\langle R_{DA}\rangle = \frac{\sum w\,R}{\sum w}.
$$

The true average separation. Because FRET is nonlinear in $R$, still not what a
measured efficiency reports.

**3. FRET-averaged distance, $\langle R_{DA}\rangle_E$:** FRET averages the *rate*,
not the distance, so average the efficiency first and invert only then:

$$
\langle E\rangle = \frac{\sum w\,E(R)}{\sum w},
\qquad E(R) = \frac{1}{1 + (R/R_0)^6},
$$

$$
\boxed{\;\langle R_{DA}\rangle_E \;=\; R_0\left(\frac{1}{\langle E\rangle} - 1\right)^{1/6}\;}
$$

with $R_0$ the Förster radius. **This is the measure to compare against an
intensity-based FRET-efficiency measurement**, because it uses the same $E\to R$
inversion the experiment does. The ordering is typically
$R_\text{mp} \lesssim \langle R_{DA}\rangle_E \lesssim \langle R_{DA}\rangle$: the
FRET weighting pulls estimate 3 toward the short-distance conformers that dominate
transfer. (A time-resolved FRET-decay analysis resolves $P(R_{DA})$ directly and is
the way to handle fast dye averaging.)

## The κ² = 2/3 assumption

The Förster radius hides the orientation factor:

$$
R_0^6 \;\propto\; \kappa^2\, Q_D\, J(\lambda)\, n^{-4},
\qquad
\kappa^2 = \left(\cos\theta_{DA} - 3\cos\theta_D\cos\theta_A\right)^2,
$$

with $\theta_{DA}$, $\theta_D$, $\theta_A$ the angles between the two dipoles and
the donor–acceptor vector. $\kappa^2 \in [0, 4]$ and is not measurable per photon;
the dye's rotational freedom is what licenses the isotropic average
$\langle\kappa^2\rangle = 2/3$, making $R_0$ — and every AV distance — a function
of distance alone. When the dye sticks (large $r_\infty$, the ACV regime),
averaging is incomplete and $\kappa^2$ contributes a residual distance
uncertainty — a dominant systematic, and the reason anisotropy is checked
alongside FRET.

## From AV distances to structural restraints

A set of FRET measurements between labeled positions becomes a set of **distance
restraints**. A candidate structure (or ensemble) is scored by how well its model
AV distances match the measured ones, usually via an (often asymmetric) $\chi^2$,

$$
\chi^2 = \sum_\text{pairs}
\left(\frac{\langle R_{DA}\rangle_E^\text{model} - R^\text{exp}}{\sigma}\right)^2,
$$

evaluated with the measure appropriate to the experiment. This score drives
screening (rank candidates), rigid-body docking (move domains to minimise
$\chi^2$), and integrative modeling (add the FRET $\chi^2$ as one restraint among
excluded-volume and other data). Combined with the analytic
{doc}`/guides/03_polymer_distance_distributions` shapes, the same machinery
connects a measured efficiency to a structure or an ensemble.

In ChiSurf the labeling/scoring configuration lives in an `fps.json` file edited by
the `fps_json_editor` plugin; the AV grid engine is the external Bayesian-
fluorescence framework (`IMP.bff`, dye code `IMP.bff.cgdye`), and the FRET plugin
hands the network to an AV-restraint scoring function for docking and refinement.

## See also

- Guides: {doc}`/guides/23_accessible_volume` (AV workflow and API) ·
  {doc}`/guides/03_polymer_distance_distributions` (analytic $P(R)$ shapes).
- Code: `chisurf/core/structure/av/` (`BasicAV`, `ACV`, `DynamicAV`); FRET plugin
  `chisurf/plugins/modelling/fret/` (`core/av.py`, `core/distance.py`,
  `core/imp_engine.py`); editor `chisurf/plugins/modelling/fps_json_editor/`.
- OKF concept: `okf/references/accessible-volume-theory.md`.
- Key literature: Sindbert et al. 2011 (*JACS*, AV); Kalinin et al. 2012
  (*Nat. Methods*, FPS toolkit); Dimura et al. 2016 (*COSB*, integrative FRET
  modeling).
