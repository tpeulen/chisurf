---
type: Concept
title: 'Hydrodynamics of rigid macromolecules: how fast a structure diffuses and tumbles'
description: Translational and rotational diffusion of a rigid body in solvent, from the Stokes–Einstein sphere to bead and shell models (HYDROPRO), and how the results connect to FCS diffusion times and anisotropy correlation times.
tags: [concepts, structure, hydrodynamics, fcs, anisotropy]
anchor: concept-hydrodynamics
---

(concept-hydrodynamics)=
# Hydrodynamics of rigid macromolecules: how fast a structure diffuses and tumbles

A protein in solution moves in two ways that fluorescence can see. It
**translates**, which FCS measures as a diffusion time $\tau_D$. It
**tumbles**, which time-resolved anisotropy measures as a rotational
correlation time $\rho$. Both are set by the friction the solvent exerts on
the molecule, which depends on its size and shape. A hydrodynamic calculation
predicts both numbers from a structure, before any measurement, so a measured
$\tau_D$ or $\rho$ can be checked against a structural model.

For the workflow, see {doc}`the HydroPro guide </guides/79_hydropro>`.

## The sphere: Stokes–Einstein and Stokes–Einstein–Debye

A sphere of hydrodynamic radius $R_h$ in a solvent of viscosity $\eta$ has
translational friction $f_t = 6\pi\eta R_h$ (Stokes). The fluctuation–dissipation
relation turns friction into diffusion {cite}`einstein1905,sutherland1905`:

$$
D_t = \frac{k_\mathrm{B}T}{6\pi\eta R_h}.
$$

For rotation the friction is $8\pi\eta R_h^3$ {cite}`debye1929`, and the
rotational diffusion coefficient $D_r$ gives the correlation time that
anisotropy measures:

$$
D_r = \frac{k_\mathrm{B}T}{8\pi\eta R_h^3}, \qquad
\rho = \frac{1}{6D_r} = \frac{\eta V_h}{k_\mathrm{B}T},
$$

with $V_h = \tfrac{4}{3}\pi R_h^3$. $D_t$ scales as $R_h^{-1}$ and $\rho$ as
$R_h^3$, so rotation is much more sensitive to size than translation: twice the
mass changes $D_t$ by 21 % but changes $\rho$ by a factor of two.

**Worked numbers for T4 lysozyme** (PDB 148L, 163 residues, $M = 18.7$ kDa,
$\bar v = 0.73\ \mathrm{cm^3\,g^{-1}}$, water at 20 °C,
$\eta = 1.002$ mPa·s). The sphere with the anhydrous volume
$M\bar v/N_A$ has $R_h = 1.76$ nm, which gives $D_t = 1.22\times10^{-6}\ \mathrm{cm^2\,s^{-1}}$
and $\rho = 5.6$ ns. Adding a typical hydration of 0.3 g water per g protein
gives $R_h = 1.97$ nm, $D_t = 1.09\times10^{-6}\ \mathrm{cm^2\,s^{-1}}$
(109 µm²/s) and $\rho = 7.9$ ns. The hydration assumption alone moves $\rho$ by
40 %. This is the reason to compute the friction from the structure rather than
from the mass.

## Arbitrary shapes: bead models

A rigid body of any shape has a $6\times6$ **diffusion tensor**
$\mathbf{D} = k_\mathrm{B}T\,\boldsymbol{\Xi}^{-1}$, the inverse of its friction
tensor $\boldsymbol{\Xi}$. $\mathbf{D}$ has a $3\times3$ translational block,
a rotational block and a translation–rotation coupling block. The scalar
coefficients are the mean traces,
$D_t = \tfrac13\operatorname{tr}\mathbf{D}_{tt}$ and
$D_r = \tfrac13\operatorname{tr}\mathbf{D}_{rr}$.

A **bead model** approximates the body by $N$ spheres. Each bead feels the
solvent flow induced by all the others, and this hydrodynamic interaction is
described by a pairwise tensor, usually the Rotne–Prager form
{cite}`rotne1969`. Solving the $3N\times3N$ linear system for the bead forces
gives $\boldsymbol{\Xi}$ {cite}`garciadelatorre1981`. The result depends on how
the beads are placed. Filling the volume with beads miscounts the friction,
because friction acts at the surface. A **shell model** covers the surface with
$N$ small minibeads of radius $\sigma$, computes the properties for several
values of $\sigma$, and extrapolates to $\sigma \to 0$. This is the accurate
procedure, and the cost is fixed by $N$ rather than by the size of the molecule
{cite}`carrasco1999`. For bead models given directly as coordinates, HYDRO++ computes the same
tensors with an improved treatment of rotation and intrinsic viscosity
{cite}`garciadelatorre2007`.

## HYDROPRO

HYDROPRO builds the model from the atomic coordinates {cite}`garciadelatorre2000`.
Every non-hydrogen atom becomes a sphere of radius **AER**, and the surface of
this *primary model* is covered with minibeads for the shell calculation. AER
is larger than a van der Waals radius on purpose: the excess represents the
hydration layer that moves with the protein. It was fitted once, against
measured properties of a set of proteins, and is meant to be kept fixed
{cite}`garciadelatorre2001`. HYDROPRO 10 adds residue-level primary models
{cite}`ortega2011`:

| INDMODE | primary model | calculation | AER |
|---|---|---|---|
| 1 | one sphere per atom | shell, extrapolated | 2.9 Å |
| 2 | one sphere per residue | shell, extrapolated | 4.8 Å |
| 4 | one sphere per residue | one bead per residue | 6.1 Å |

The output is the translational diffusion coefficient, the rotational
diffusion tensor and the five rotational relaxation times, the radius of
gyration, the volume, the sedimentation coefficient and the intrinsic
viscosity. $D_t$, $D_r$ and the relaxation times depend only on the shape,
$T$ and $\eta$. The molecular mass $M$, $\bar v$ and the solvent density enter
only the sedimentation coefficient, $s = M(1-\bar v\rho_s)/(N_A f_t)$, and the
intrinsic viscosity.

## From the calculation to the measurement

**FCS.** A labelled protein diffusing through a focus of lateral waist
$w_{xy}$ has a diffusion time ({ref}`concept-fcs-correlation`)

$$
\tau_D = \frac{w_{xy}^2}{4D_t}.
$$

With $D_t = 109$ µm²/s and $w_{xy} = 0.4$ µm this gives $\tau_D = 0.37$ ms.
The comparison goes both ways. A measured $\tau_D$ against a predicted $D_t$
checks the waist calibration, and against a calibrated waist it checks the
assumed structure or oligomeric state. Because $D_t \propto R_h^{-1}$, a dimer
changes $\tau_D$ by only about 25 %, so a small difference needs a calibrated
setup. The rotational motion also appears in the correlation function, at
nanoseconds, well below $\tau_D$ {cite}`ehrenberg1974`.

**Anisotropy.** For a dye rigidly fixed in the protein frame, the anisotropy
decay is a sum of up to five exponentials. Their correlation times are
HYDROPRO's five rotational relaxation times, and their amplitudes depend on the
orientation of the dipoles in the body frame {cite}`perrin1934,perrin1936`.
For a near-spherical protein such as T4 lysozyme the five times are close
together and one $\rho$ describes the decay. A dye on a flexible linker adds a
fast local term. The global $\rho$ is then the slow component of the fit, and
it is the one to compare with the hydrodynamic prediction
({ref}`concept-anisotropy`).

**The dye itself.** The same Stokes–Einstein relation gives the diffusion
coefficient of a free dye. For $R_h \approx 0.6$ nm it is about
360 µm²/s, or 36 Å²/ns. Dye diffusion
simulations such as QuEst ({ref}`concept-dye-quenching`) work in Å²/ns and use
smaller values, because a tethered dye diffuses more slowly than a free one.

## Using it well

- **Rigid bodies only.** A bead model has one conformation. Flexible linkers,
  disordered tails and domain motions make the real molecule larger and
  slower than a calculation on the crystal structure predicts. Treat the
  prediction as a lower bound on $\tau_D$ and $\rho$.
- **Viscosity and temperature.** Every diffusion coefficient scales as
  $T/\eta$. Buffer additives change $\eta$ (10 % glycerol raises it by about
  30 % at 20 °C). Quote the conditions with the number, and convert to
  $D_{20,w}$ before comparing numbers from different buffers.
- **Infinite dilution.** The calculation describes one molecule alone in the
  solvent. Crowding and high concentration slow both motions.
- **Keep AER at its calibrated value.** Changing AER to fit a measurement moves
  the hydration layer, and the model then predicts a different molecule. It is
  adjusted only for low-resolution bead models, such as those from SAXS, where
  there are no atoms.
- **Remove what is not the molecule.** HYDROPRO counts every non-hydrogen
  `ATOM` and `HETATM` record except water oxygens. Ligands, detergent and
  alternate conformations in the file become part of the body.

## See also

- Guide: {doc}`/guides/79_hydropro`.
- Related concepts: {ref}`concept-anisotropy` (rotational correlation times),
  {ref}`concept-fcs-correlation` (diffusion times),
  {ref}`concept-molecular-surfaces` (the surface the shell model covers),
  {ref}`concept-dye-quenching` (diffusion of a tethered dye).
- Implementation: the input file
  {src}`chisurf/plugins/modelling/hydropro/core/runner.py#write_hydropro_input`,
  the run {src}`chisurf/plugins/modelling/hydropro/core/runner.py#run_hydro`
  and the parser
  {src}`chisurf/plugins/modelling/hydropro/core/runner.py#parse_diffusion_coefficient`.

## References

- {cite}`einstein1905`, {cite}`sutherland1905`: the diffusion–friction relation
  for a sphere.
- {cite}`debye1929`: rotational diffusion of a sphere.
- {cite}`garciadelatorre1981`: bead-model theory of the friction and diffusion
  tensors.
- {cite}`rotne1969`: the hydrodynamic interaction tensor between beads.
- {cite}`carrasco1999`: bead against shell models, and the extrapolation to
  zero minibead size.
- {cite}`garciadelatorre2000`: HYDROPRO.
- {cite}`ortega2011`: HYDROPRO 10 and the residue-level modes.
- {cite}`garciadelatorre2007`: HYDRO++, rotational diffusion and intrinsic
  viscosity of bead models.
- {cite}`garciadelatorre2001`: what the hydration in a hydrodynamic model
  means.
