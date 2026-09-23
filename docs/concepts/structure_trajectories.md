---
type: Concept
title: 'Structure trajectories: superposition, RMSD, clashes and FRET along a trajectory'
description: What a trajectory tool does to the coordinates — optimal rigid superposition (Kabsch, quaternions), the minimal RMSD, steric clashes as van-der-Waals overlap, and why the FRET efficiency of a moving molecule depends on how the average is taken.
tags: [concepts, structure, trajectory, fret]
anchor: concept-structure-trajectories
---

(concept-structure-trajectories)=
# Structure trajectories: superposition, RMSD, clashes and FRET along a trajectory

A trajectory is a stack of coordinate frames, $\mathbf{x}_i(t)$ for atoms
$i = 1\ldots N$, plus a topology that names the atoms. The frames come from a
molecular-dynamics run, a normal-mode ensemble or a docking screen. The
trajectory tools do four things with them. They remove rigid-body motion
(superposition), measure how far a frame is from a reference (RMSD), drop
physically impossible frames (clashes) and turn the geometry into FRET
observables. Each step has a result that depends on a choice the user makes,
and this page explains those choices.

For the tools themselves see the {doc}`trajectory tools guide
</guides/81_trajectory_tools>`. For the dye clouds behind a FRET distance see
{ref}`concept-accessible-volume`, and for the orientation factor see
{ref}`concept-kappa2-orientation`.

The numbers on this page come from the T4 lysozyme normal-mode ensemble that
ships with ChiSurf (`chisurf/plugins/modelling/fret/examples/olga_t4l/`:
894 frames, 1293 heavy atoms, 162 Cα). Coordinates are in ångström, the unit of
the DCD file.

## Optimal superposition

Two frames of the same molecule differ by internal motion and by a rigid
rotation and translation. To compare the internal motion, the rigid part is
removed first. That means finding the rotation $\mathbf{R}$ and translation
$\mathbf{t}$ that minimise

$$
D(\mathbf{R},\mathbf{t}) = \sum_{i\in S} \left\lVert \mathbf{R}\,\mathbf{x}_i + \mathbf{t} - \mathbf{y}_i \right\rVert^2
$$

over a fitting set $S$ of atoms, where $\mathbf{x}$ is the mobile frame and
$\mathbf{y}$ the reference. The optimal translation superimposes the centroids,
so both sets are centred first ($\mathbf{x}_i \leftarrow \mathbf{x}_i - \bar{\mathbf{x}}$,
likewise $\mathbf{y}$). That leaves only the rotation.

**Kabsch's solution.** Build the $3\times3$ covariance matrix
$\mathbf{H} = \sum_{i\in S} \mathbf{x}_i \mathbf{y}_i^{\mathsf T}$ and take its
singular-value decomposition $\mathbf{H} = \mathbf{U}\boldsymbol{\Sigma}\mathbf{V}^{\mathsf T}$.
The rotation is

$$
\mathbf{R} = \mathbf{V}\,\mathrm{diag}(1, 1, d)\,\mathbf{U}^{\mathsf T},
\qquad d = \mathrm{sign}\,\det(\mathbf{V}\mathbf{U}^{\mathsf T})
$$

{cite}`kabsch1976,kabsch1978`. The factor $d$ matters. Without it the SVD
can return a reflection, which superimposes a molecule on its mirror image and
reports an RMSD that is too small. Kabsch's 1978 note describes this
correction. ChiSurf's superposition
({src}`chisurf/core/structure/trajectory_data.py`) is this SVD with the
handedness flip. It works on all frames at once.

**The quaternion route.** The same minimum can be found from a unit
quaternion: the optimal rotation is the eigenvector of the largest eigenvalue
$\lambda_\text{max}$ of a symmetric $4\times4$ matrix built from the elements
of $\mathbf{H}$ {cite}`horn1987,coutsias2004`. Quaternions cannot encode a
reflection, so no sign correction is needed. The minimal deviation follows from
the eigenvalue alone,

$$
\mathrm{RMSD}_\text{min} = \sqrt{\frac{G_x + G_y - 2\lambda_\text{max}}{N_S}},
\qquad G_x = \sum_{i\in S}\lVert\mathbf{x}_i\rVert^2 ,
$$

and Theobald's QCP method gets $\lambda_\text{max}$ by Newton iteration on the
characteristic polynomial without computing the eigenvector
{cite}`theobald2005`. The two routes give the same rotation to floating-point
precision. ChiSurf uses the SVD because it is a dozen readable lines.

**What the fitting set does.** Only the atoms in $S$ enter $\mathbf{H}$, but
the rotation is applied to every atom. The usual choice is to fit on a stable
core (the backbone, or the Cα of a domain) and carry the rest along. A flexible
loop then shows up as displacement relative to the core. Fitting on everything
spreads the loop's motion over the whole molecule instead.

## RMSD

After superposition,

$$
\mathrm{RMSD} = \sqrt{\frac{1}{N_S}\sum_{i\in S}\lVert \mathbf{R}\,\mathbf{x}_i + \mathbf{t} - \mathbf{y}_i\rVert^2 }.
$$

An RMSD is only meaningful with its fitting set and its reference frame stated.
Two points follow from the T4 lysozyme ensemble:

* **Superposition roughly halves the number.** The Cα RMSD of each frame
  against frame 0 has a median of 3.86 Å (range 1.83–6.68 Å) after
  superposition. The plain coordinate difference, without it, has a median of
  6.56 Å. Most of that difference is rigid-body motion.
* **An aligned trajectory reproduces the minimal RMSD.** After the Align tool
  has superposed every frame on frame 0, the plain RMSD of the output equals
  the minimal RMSD of the input to within $2\times10^{-6}$ Å. This is the check
  that the alignment did what it claims.

A single RMSD value mixes a few large displacements with many small ones.
When the question is *where* the molecule moves, per-atom fluctuations or a
per-residue RMSD answer it better.

## Steric clashes

Two atoms that are not bonded cannot come closer than roughly the sum of their
van der Waals radii. Bondi's radii are the usual reference: C 1.70 Å,
N 1.55 Å, O 1.52 Å {cite}`bondi1964`. A pair clashes when it overlaps by more
than a tolerance,

$$
d_{ij} < r_i + r_j - \delta ,
$$

and pairs that are chemically connected (1–2 and 1–3 neighbours) are excluded,
because covalent bonds are much shorter than $r_i + r_j$. MolProbity's
all-atom contact analysis uses an overlap of $\delta = 0.4$ Å with explicit
hydrogens as a serious clash {cite}`word1999,chen2010molprobity`. Coarse or generated
ensembles (normal modes, rigid-body docking, coarse-grained models) produce
such frames, and they have to be removed before anything is averaged over the
ensemble.

ChiSurf computes two cruder versions of this test:

* **Remove Clashed** (a filter) uses a single minimum distance $d_\text{min}$
  over a selected atom set. There are no per-element radii and no bond
  exclusion. A frame is dropped if any selected pair satisfies
  $d_{ij} < d_\text{min}$. Because bonds are not excluded, the filter is only
  meaningful on a sparse selection. On Cα atoms, consecutive residues sit
  3.8 Å apart, so $d_\text{min}$ must stay below that. On the T4 lysozyme
  ensemble, 0 frames have a Cα pair below 3.0 Å, 132 below 3.5 Å, 420 below
  3.7 Å and all 894 below 3.8 Å. On all heavy atoms, a 2.0 Å threshold flags
  every frame, because every C–C bond is shorter than that.
* **Clash potential** (a score in the energy calculator) is a soft-sphere
  penalty with per-atom radii,
  $E = \sum_{i<j} \big((r_i + r_j - d_{ij})/\delta\big)^2$ for
  $d_\text{cov} < d_{ij} < r_i + r_j$ (defaults $\delta = 2$ Å,
  $d_\text{cov} = 1.5$ Å). Pairs closer than $d_\text{cov}$ count as bonded
  and are ignored. The value is useful for ranking frames, not as an energy
  in physical units.

## FRET along a trajectory

For one frame, the donor–acceptor distance $R$ and orientation factor
$\kappa^2$ give a transfer rate

$$
k_\text{FRET} = \frac{3}{2}\,\kappa^2\,\frac{1}{\tau_{D(0)}}\left(\frac{R_0}{R}\right)^6 ,
$$

with $R_0$ defined for $\kappa^2 = 2/3$ {cite}`dale1979`, and the efficiency is
$E = k_\text{FRET}/(k_\text{FRET} + 1/\tau_{D(0)})$. Averaging over the frames
is where it gets subtle. The result depends on how the frame-to-frame motion
compares with the donor lifetime $\tau_{D(0)}$ (a few ns), and no single
formula is correct in both regimes.

* **Static averaging** (motion slower than $\tau_{D(0)}$). Each excitation
  sees a frozen structure, and the ensemble averages efficiencies:
  $\langle E\rangle = \frac{1}{T}\sum_t E(t)$.
* **Dynamic averaging** (motion faster than $\tau_{D(0)}$). The donor sees the
  time-averaged rate before it decays:
  $E = \langle k\rangle/(\langle k\rangle + 1/\tau_{D(0)})$.
* **$E(\langle R\rangle)$** puts the mean distance into the Förster equation.
  It matches neither regime and is the number a single-distance model implies.

Orientation behaves the same way. $\kappa^2 = 2/3$ is the *dynamic* isotropic
average, valid when both dyes rotate much faster than $\tau_{D(0)}$
{cite}`dale1979`. Frozen random orientations give the static average of the
per-frame efficiencies instead, which is lower.

On the T4 lysozyme ensemble, taking the Cα→Cβ vectors of residues 36 and 132
as stand-ins for the dye dipoles ($R_0$ = 52 Å, $\tau_{D(0)}$ = 4 ns) gives a
dipole-centre distance of 27.1 ± 5.7 Å and:

| averaging | $\kappa^2 = 2/3$ | $\kappa^2$ per frame ($\langle\kappa^2\rangle$ = 0.574) |
|---|---|---|
| $E(\langle R\rangle)$ | 0.980 | — |
| static, $\langle E\rangle$ | 0.967 | 0.840 |
| dynamic, $\langle k\rangle$ | 0.994 | 0.993 |

The distances alone move $E$ by 0.03 between regimes. The per-frame
orientations move the static value by 0.15, because a quarter of the frames
have $\kappa^2 < 0.1$ and those frames barely transfer at all. (Backbone bond
vectors are not dye dipoles. The table illustrates the size of the effect,
not a prediction for a labelled T4 lysozyme.) MD–FRET studies that follow
$\kappa^2(t)$ explicitly reach the same conclusion. Replacing $\kappa^2(t)$
with 2/3 is only safe when orientational relaxation is fast, and $\kappa^2$
and $R$ can be correlated {cite}`hoefling2011,schroder2005`.

**Dyes on a structure without dyes.** Most trajectories contain the protein
only. The dye position is then modelled per frame by an accessible volume, and
the frame's efficiency is the average over donor and acceptor positions,
$\langle E\rangle_\text{AV} = \sum w_D w_A E(\lVert\mathbf{r}_D - \mathbf{r}_A\rVert)$.
Dye diffusion inside its AV is fast compared with most conformational motion,
so the usual choice averages the AV per frame and then combines frames
according to the regimes above. The three AV distance measures and the choice
between them are explained in {ref}`concept-accessible-volume`, and the FPS
benchmark discusses when each regime applies {cite}`kalinin2012`.

What ChiSurf computes:

* The **FRET** tab of the trajectory tools uses two atoms per dye as a dipole.
  For each frame it writes $R$, $\kappa$, $\kappa^2$ and $k_\text{FRET}$, with
  no AV and no averaging. The table is the input for either regime. Unchecking
  *Dipole* switches to the distance between the first atoms, with a fixed
  $\kappa^2 = 2/3$.
* The FRET-modelling evaluator
  ({src}`chisurf/plugins/modelling/fret/core/trajectory.py`) builds an AV per
  frame and returns $\langle E\rangle_\text{AV}$ per frame and label pair.

## Assumptions worth stating

* **One topology for every frame.** A DCD file stores coordinates only. Atom
  names, residues and chains come from the topology PDB, and a mismatched atom
  count is refused.
* **Rigid-body superposition assumes a meaningful core.** A molecule with two
  domains that move relative to each other has no single correct alignment.
  Choose the fitting set for the question you are asking.
* **A clash filter drops frames, so the time axis gets gaps.** The kept frames
  keep their source times (written beside the DCD). An ensemble average over
  them is an average over the physically allowed frames only.
* **Frames are not independent samples.** Neighbouring MD frames are
  correlated. A standard error computed as if each frame were independent is
  too small.

## See also

- Guide: {doc}`/guides/81_trajectory_tools`. AV workflow:
  {doc}`/guides/23_accessible_volume`.
- {ref}`concept-accessible-volume` (dye clouds, $R_\text{mp}$ /
  $\langle R_{DA}\rangle$ / $\langle R_{DA}\rangle_E$) ·
  {ref}`concept-kappa2-orientation` · {ref}`concept-fret` ·
  {ref}`concept-molecular-surfaces` (whether a site can be labelled).

## References

- {cite}`kabsch1976` — the SVD solution for the optimal rotation.
- {cite}`kabsch1978` — the reflection case and the handedness correction.
- {cite}`horn1987` — closed-form absolute orientation with unit quaternions.
- {cite}`coutsias2004` — quaternion RMSD, and its equivalence to Kabsch.
- {cite}`theobald2005` — the QCP method: RMSD from the characteristic polynomial.
- {cite}`bondi1964` — van der Waals radii.
- {cite}`word1999` — all-atom contact dots and the overlap criterion for clashes.
- {cite}`chen2010molprobity` — MolProbity clashscore.
- {cite}`dale1979` — orientation-factor averaging regimes.
- {cite}`schroder2005` — simulating anisotropy and orientations from MD trajectories.
- {cite}`hoefling2011` — FRET efficiency distributions from atomistic trajectories with explicit κ²(t).
- {cite}`kalinin2012` — AV modelling, distance measures and averaging regimes (FPS).
