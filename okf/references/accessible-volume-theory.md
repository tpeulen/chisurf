---
type: Reference
title: "Accessible-volume theory — from a flexible dye to a FRET distance restraint"
description: The physics behind ChiSurf's accessible-volume (AV) dye modeling — why a linker-tethered dye samples a distribution of positions, the geometric AV grid search, the mean dye position, the accessible-contact-volume (ACV) refinement, the three AV-to-distance measures (Rmp, <R_DA>, <R_DA>_E), the κ²=2/3 assumption, and how AV distances become FRET restraints for integrative structural modeling.
tags: [reference, av, fret, modelling, restraints, pedagogy]
timestamp: '2026-07-24T00:00:00Z'
---

# Accessible-volume theory — from a flexible dye to a FRET distance restraint

FRET measures a distance between two fluorophores, but structural modeling needs
a distance between two **atoms** of the biomolecule. The gap between them is the
dye and its linker: a fluorophore is coupled to the biomolecule through a
flexible, mostly aliphatic spacer arm, so it does not sit at a fixed point — it
explores a cloud of positions around its attachment atom. The **accessible
volume (AV)** model turns that cloud into a computable object, and from a pair of
AVs into a *model distance* that can be compared to a measured FRET distance and
used as a **restraint** in integrative structural modeling. This concept is the
science/pedagogy layer for ChiSurf's AV tooling: what the AV is, why three
different "distances" fall out of it, and how those become restraints.

It complements the maintained user guide
[/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) (workflow and
API), the [modelling roadmap](modelling-roadmap.md) (forward-looking `fps.json`
and parameter-adapter work), and the [Modelling plugins](/plugins/modelling.md)
group. The molecular-modelling kernel itself has migrated out of ChiSurf into the
external Bayesian-fluorescence framework (`IMP.bff`, dye/labeling code under
`IMP.bff.cgdye`); ChiSurf wraps it and is Cython-free.

The physics and terminology follow the FPS/AV literature as **documented prior
art**: the AV construction (Sindbert et al., *J. Am. Chem. Soc.* 2011,
133:2463), the FPS toolkit and benchmark that established AV-restrained modeling
(Kalinin et al., *Nat. Methods* 2012, 9:1218), the ACV refinement (Steffen et
al., *Phys. Chem. Chem. Phys.* 2016, 18:29045), and the integrative-modeling
review (Dimura et al., *Curr. Opin. Struct. Biol.* 2016, 40:163). The grid engine
role is that of the low-level LabelLib library; formulas here are reimplemented
independently in ChiSurf, nothing is a verbatim code copy.

## Why a tethered dye samples a distribution

A dye on a $C_n$ linker has two consequences, and the AV model exploits the
first to justify the second:

- **Rotational freedom → $\kappa^2 = 2/3$.** On the fluorescence-lifetime
  timescale the linker lets the dye reorient over most of a sphere, so the
  donor–acceptor transition dipoles sample orientations nearly isotropically.
  This is the physical basis of the standard **orientation-factor assumption**
  $\langle\kappa^2\rangle = 2/3$, which decouples the FRET rate from the
  unknown mutual dye orientation and leaves it a pure function of distance (see
  the κ² section below).
- **Positional freedom → a spatial distribution.** The same flexibility means
  the dye's *position* relative to the biomolecule is uncertain. Instead of one
  point there is a probability cloud, and the inter-dye distance is a
  **distribution** $P(R_{DA})$, not a single number.

An explicit all-atom molecular-dynamics simulation with the dyes included would
sample this cloud rigorously, but it is expensive per labeling site. The AV
approach replaces it with a cheap, purely **geometric** search that captures the
dominant, steric part of the distribution.

## The AV construction — a probe on a leash

The dye plus linker is coarse-grained into a simple geometric probe swept around
the attachment atom:

- The **linker** is a flexible tube of length $L_\text{link}$ (its contour
  length) and width $W_\text{link}$ (its steric diameter).
- The **dye** is a soft body approximated by one radius ($R_1$, the `AV1` model)
  or three radii ($R_1, R_2, R_3$ for a spheroid, the `AV3` model), depending on
  how anisotropic the fluorophore is.

The search then asks: which grid points, on a lattice of spacing $\Delta$
(typically ~0.5–1.0 Å) around the attachment atom, can the dye centre occupy such
that (i) it is reachable by a linker path of length $\le L_\text{link}$ that does
not pass through the biomolecule, and (ii) the dye body does not clash with any
biomolecule atom (each atom carries its van-der-Waals radius). Reachability is a
shortest-path (Dijkstra-style) flood-fill over the free grid from the attachment
point; the linker cannot tunnel through the protein, so the accessible set hugs
the surface rather than filling a naïve sphere. The result is a weighted point
cloud — every allowed grid point, initially with equal weight — describing where
the dye can be.

In ChiSurf this is `chisurf/core/structure/av/` and the FRET plugin's
`core/av.py`, backed by either the LabelLib kernel or `IMP.bff` (`AV`,
`PM_TILE_ACCESSIBLE_DENSITY`); the returned `AccessibleVolume` carries the points
$(x, y, z, w)$ and derived quantities.

## The mean dye position

The first quantity read off an AV cloud is the **mean dye position**, the
weight-weighted centroid of the point cloud:

$$
\mathbf{R}_\text{mp} = \frac{\sum_i w_i\,\mathbf{r}_i}{\sum_i w_i}.
$$

$\mathbf{R}_\text{mp}$ is the single "effective" point where the dye sits on
average. It is what lets a FRET distance be expressed relative to the
biomolecule's frame, and it is the anchor for the fast rigid-body restraints (a
docking move only has to retranslate the mean positions, not re-flood the grid).

## The accessible-contact volume (ACV)

The plain AV assumes the dye samples its whole steric envelope uniformly. Real
dyes with conjugated $\pi$-systems often **stick** to the biomolecule surface
(base stacking on DNA, hydrophobic patches on proteins), which shifts the mean
position toward the surface and shows up experimentally as an incomplete
anisotropy decay levelling off at $r_\infty > 0$.

The **accessible-contact volume (ACV)** refinement (Steffen et al. 2016) splits
the AV into two zones and reweights them:

- a thin **contact volume (CV)** shell within a distance $W_\text{CV}$ of the
  biomolecule surface (its width is usually set to a dye dimension), and
- the remaining **free volume**.

A fraction $w_\text{CV}$ of the total weight is placed in the contact shell and
$1 - w_\text{CV}$ in the free volume, so the point weights $w_i$ are no longer
uniform. The contact weight can be estimated from the residual anisotropy
$r_\infty$. Setting $w_\text{CV} = 0$ recovers the plain AV. In ChiSurf this is
the `ACV` variant; `DynamicAV` is a further diffusion-with-quenching refinement.

## From an AV pair to a model distance

Two AVs (donor, acceptor) define a distribution of inter-dye distances. Draw
weighted samples $\mathbf{r}_D \sim \{w_i^D\}$, $\mathbf{r}_A \sim \{w_j^A\}$ with
combined weight $w = w_i^D w_j^A$; each pair gives a distance
$R = \lVert\mathbf{r}_D - \mathbf{r}_A\rVert$. This empirical, weighted $P(R_{DA})$
is what the AV pair actually predicts. From it come **three distinct scalar
"distances"**, and confusing them is the classic AV pitfall — they differ by
several Å and each answers a different question.

1. **Distance between mean positions, $R_\text{mp}$** — the distance between the
   two mean dye positions,
   $$
   R_\text{mp} = \lVert \mathbf{R}_\text{mp}^{D} - \mathbf{R}_\text{mp}^{A} \rVert .
   $$
   Cheap and geometric, but it ignores the *widths* of the clouds, so it is a
   biased estimator of what FRET measures. Use it only as a fast proxy (e.g. in
   rigid-body docking), never as the direct model of an efficiency.

2. **Mean inter-dye distance, $\langle R_{DA}\rangle$** — the weighted first
   moment of the distribution,
   $$
   \langle R_{DA}\rangle = \frac{\sum w\,R}{\sum w}.
   $$
   The true average separation. Because FRET is nonlinear in $R$, this is still
   not what a measured efficiency reports.

3. **FRET-averaged distance, $\langle R_{DA}\rangle_E$** — the distance that
   reproduces the *mean FRET efficiency* over the distribution. FRET averages the
   rate, not the distance, so one first averages the efficiency and only then
   inverts:
   $$
   \langle E\rangle = \frac{\sum w\,E(R)}{\sum w},
   \qquad E(R) = \frac{1}{1 + (R/R_0)^6},
   $$
   $$
   \boxed{\;\langle R_{DA}\rangle_E \;=\; R_0\left(\frac{1}{\langle E\rangle} - 1\right)^{1/6}\;}
   $$
   with $R_0$ the Förster radius. **This is the measure to compare against a
   FRET-efficiency measurement** (single-molecule intensity-based FRET, PDA),
   because it is defined by the same $E \to R$ inversion the experiment uses.

The ordering is generally $R_\text{mp} \lesssim \langle R_{DA}\rangle_E \lesssim
\langle R_{DA}\rangle$ for typical linker widths; the FRET-weighting in measure 3
pulls the estimate toward the short-distance tail of $P(R_{DA})$ because those
conformers dominate the transfer. A related caveat is the **static vs. dynamic
averaging regime**: $\langle R_{DA}\rangle_E$ as written assumes the dye explores
the whole AV *slowly* relative to the fluorescence lifetime (each photon sees one
frozen distance); a time-resolved decay analysis (TCSPC) that resolves $P(R_{DA})$
directly is the way to model the fast-averaging case. ChiSurf exposes all three
via `distance_between_mean_positions`, `average_distance`, and
`mean_fret_distance` (plus `av_pair_statistics`, which also returns the
distribution's standard deviation $\sigma_R$).

## The κ² = 2/3 assumption

The Förster radius $R_0$ hides the orientation factor:

$$
R_0^6 \;\propto\; \kappa^2\, Q_D\, J(\lambda)\, n^{-4},
\qquad
\kappa^2 = \left(\cos\theta_{DA} - 3\cos\theta_D\cos\theta_A\right)^2,
$$

where $\theta_{DA}$, $\theta_D$, $\theta_A$ are the angles between the two
transition dipoles and the donor–acceptor vector. $\kappa^2$ ranges from $0$ to
$4$ and cannot be measured per-photon. The AV justification (rotational freedom
above) is what allows the **isotropic-average $\langle\kappa^2\rangle = 2/3$** to
be substituted, making $R_0$ — and therefore every AV distance — a function of
distance alone. When the dye sticks (large $r_\infty$, the ACV regime), rotational
averaging is incomplete and $\kappa^2$ carries residual uncertainty; this is a
dominant systematic in AV-based distances and the reason anisotropy is checked
alongside FRET. The κ² uncertainty propagates into $R_0$ and can be carried as a
distance-uncertainty band on the restraint.

## AV distances as FRET restraints for modeling

The point of all this is structural modeling. A set of FRET measurements between
labeled positions becomes a set of **distance restraints**, and a candidate
structure (or an ensemble) is scored by how well its *model* AV distances match
the *measured* ones. For each pair the score is an (often asymmetric) $\chi^2$:

$$
\chi^2 = \sum_\text{pairs}
\left(\frac{\langle R_{DA}\rangle_E^\text{model} - R^\text{exp}}{\sigma}\right)^2,
$$

evaluated with the appropriate measure ($\langle R_{DA}\rangle_E$ for
efficiency-derived experimental distances). This score can drive:

- **Screening** a set of candidate structures against the FRET data (rank by
  $\chi^2$),
- **Rigid-body docking** — moving domains to minimise $\chi^2$; the fast path
  scores on the mean-position distances so each move only retranslates
  $\mathbf{R}_\text{mp}$ rather than re-flooding the grid,
- **Integrative modeling** — adding the FRET $\chi^2$ as one restraint among
  many (excluded-volume, other experimental data) in a Monte-Carlo / minimization
  sampler.

The labeling configuration — attachment atoms, per-dye linker/radius parameters,
Förster radii, experimental distances, and named scoring groups — is carried in
an **`fps.json`** file. ChiSurf's `fps_json_editor` plugin edits it against a
loaded PDB; the FRET plugin's `imp_engine` hands it to
`IMP.bff.restraints.AVNetworkRestraintWrapper`, which builds the AV network and
the $\chi^2$ scoring function used by the docking/refinement runs. The
`av_decay` TCSPC model instead feeds the simulated $P(R_{DA})$ straight into a
time-resolved FRET-decay fit, closing the loop between the geometric AV and the
measured decay.

## Pointers

- ChiSurf AV core: `chisurf/core/structure/av/` (`BasicAV`, `ACV`, `DynamicAV`,
  `calculate_1_radius`/`calculate_3_radius`); FRET-plugin engine
  `chisurf/plugins/modelling/fret/core/av.py`, distance measures
  `core/distance.py` (`distance_between_mean_positions`, `average_distance`,
  `mean_fret_distance`, `av_pair_statistics`), integrative scoring
  `core/imp_engine.py`.
- Editor & config: `chisurf/plugins/modelling/fps_json_editor/` (the `fps.json`
  labeling/scoring schema).
- User guide: [/guides/23_accessible_volume.md](/guides/23_accessible_volume.md);
  polymer $P(R)$ companion
  [/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md).
- Forward roadmap (full `fps.json` schema, distance-parameter adapters):
  [modelling-roadmap.md](modelling-roadmap.md); modelling plugin overview
  [/plugins/modelling.md](/plugins/modelling.md).
- External kernel: the Bayesian-fluorescence framework (`IMP.bff`, dye code
  `IMP.bff.cgdye`) and the low-level AV grid library it wraps.
- Key literature: Sindbert et al. 2011 (*JACS* 133:2463, AV); Kalinin et al. 2012
  (*Nat. Methods* 9:1218, FPS toolkit); Steffen et al. 2016 (*PCCP* 18:29045,
  ACV); Dimura et al. 2016 (*COSB* 40:163, integrative FRET modeling).
