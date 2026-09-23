---
type: Concept
title: 'Dye quenching by amino acids: photoinduced electron transfer at contact'
description: How aromatic and sulfur-containing residues quench a tethered dye by photoinduced electron transfer, why the process is a contact reaction, what it does to lifetimes, FCS and FRET, and how QuEst simulates it from a structure.
tags: [concepts, photophysics, structure, fret, fcs]
anchor: concept-dye-quenching
---

(concept-dye-quenching)=
# Dye quenching by amino acids: photoinduced electron transfer at contact

A dye attached to a protein is usually less bright, and has a shorter and less
single-exponential lifetime, than the same dye free in buffer. The main cause
is **photoinduced electron transfer (PET)** from nearby residues. PET is a
contact reaction, so its size depends on where the labelling site is, how the
dye moves on its linker, and which residues are within reach. The same
process that biases a FRET measurement is also used deliberately as a probe of
contact formation, in PET-FCS.

For the simulation tool, see {doc}`the QuEst guide </guides/80_quenching_estimator>`.
Quenching between freely diffusing partners (Stern–Volmer, the Rehm–Weller
driving force, nucleobases) is covered in {ref}`fundamentals-quenching-mechanisms`;
this page is about a dye tethered to a structure.

## The reaction

In the excited state a dye is both a stronger oxidant and a stronger reductant
than in the ground state. When an electron-rich side chain, most of all the
indole of tryptophan, is in contact with it, an electron moves between the two.
The resulting radical-ion pair recombines without emitting a photon. The
driving force follows from the redox potentials of the two partners and the
excitation energy of the dye, as in the Rehm–Weller relation {cite}`rehm1970`. It
therefore depends on the pair: a residue that quenches one dye strongly can
leave another almost untouched {cite}`marme2003`. The same reasoning ranks the
nucleobases as quenchers, with guanine the strongest {cite}`seidel1996`.

Electron transfer needs orbital overlap, so its rate falls off exponentially
with distance, on a length scale of about an ångström. In practice the dye is
quenched when it is in van der Waals contact with the residue and not
otherwise. Molecular dynamics of dye–tryptophan pairs shows quenching in
stacked contact complexes {cite}`vaiana2003`, and experiments separate a
dynamic, diffusion-limited part from a static part due to complexes present
before excitation {cite}`doose2005`.

**Which residues.** For oxazine and rhodamine dyes, tryptophan is essentially
the only amino-acid quencher {cite}`marme2003,doose2005`. The xanthene
Alexa488 is also quenched by tyrosine, methionine and histidine
{cite}`chen2010`.

## What quenching does to the observables

- **Lifetime.** Contacts formed during the excited-state lifetime add a
  non-radiative rate. The donor decay becomes multi-exponential even though
  the dye has a single unquenched lifetime $\tau_0$
  ({ref}`concept-tcspc-lifetime`).
- **Brightness.** Static complexes are dark from the moment of excitation.
  They reduce the brightness but do not show up in the lifetime, so the
  lifetime underestimates the total quenching.
- **FCS.** Contact formation and breakage switch the fluorescence off and on.
  If this happens faster than diffusion through the focus, it adds a bunching
  term to the correlation curve, at nanoseconds to microseconds. This is
  PET-FCS: a dye–tryptophan pair placed in a peptide or protein reports the
  contact-formation rate directly {cite}`neuweiler2003,doose2009`
  ({ref}`concept-fcs-correlation`).
- **FRET.** Donor quenching lowers the donor quantum yield, which changes
  $R_0$. The donor-only reference also has to come from the same site, and a
  donor that is quenched while it sits near the surface samples a different
  part of its accessible volume than an unquenched one
  {cite}`peulen2017,dimura2016` ({ref}`concept-fret`,
  {ref}`concept-accessible-volume`).

## Why the dye's motion matters

A dye on a flexible linker explores its accessible volume (AV). With QuEst's
default diffusion coefficient for a tethered dye, $D = 7.5$ Å²/ns, crossing a
20 Å region takes $(20\ \text{Å})^2/(6D) \approx 9$ ns. This is comparable to
$\tau_0 \approx 4$ ns. The decay is therefore neither in the static limit (the
dye stays where it was excited) nor in the fast-exchange limit (the dye
averages over the whole volume within the lifetime). It depends on how often
the dye reaches a quencher and how long it stays there. For this reason QuEst
simulates a trajectory instead of averaging over the AV {cite}`peulen2017`.
Unspecific adhesion to the surface lengthens the stays, which is why it has to
be modelled too.

## The QuEst model

QuEst follows three steps {cite}`peulen2017`:

1. **Accessible volume.** The AV of a sphere of radius $R_\text{dye}$ on a
   linker of length $L$ and width $w$ is computed on a grid of spacing
   $d_g$ ({ref}`concept-accessible-volume`). Each quenching residue $i$ gets a
   centre $\mathbf{q}_i$, the centroid of its redox-active atoms (not
   C$_\beta$), a rate $k_{Q,i}$ and a contact radius $R_i$ measured from the
   dye centre.
2. **Brownian dynamics.** The dye centre $\mathbf{r}(t)$ diffuses on the AV
   grid with time step $\Delta t$ for a total time $t_\text{max}$. Near a
   residue the local diffusion coefficient is reduced by that residue's slow
   factor $s_i \le 1$. Overlapping factors multiply:
   $$
   D(\mathbf{r}) = D \prod_i s_i^{\,H(R_s - |\mathbf{r}-\mathbf{c}_i|)},
   $$
   with $H$ the step function, $\mathbf{c}_i$ the residue centre and $R_s$
   the slowing radius.
3. **Photons.** Along the trajectory the excited-state decay rate is
   $$
   k(t) = \frac{1}{\tau_0} + \sum_i k_{Q,i}\,H\!\left(R_i - |\mathbf{r}(t)-\mathbf{q}_i|\right),
   $$
   so overlapping contact spheres add their rates. Photons are excited at
   random frames and decay in competition with $k(t)$. Those that are emitted
   form the decay histogram. The reported quantum yield is the emitted
   fraction of all excitations, so it is relative to the unquenched dye and
   equals 1 without quenchers. With an acceptor, a Förster rate proportional
   to $(R_0/R_{DA})^6$ is added in the same way.

**Reference parameters.** The shipped table is for a xanthene dye of the
Alexa488 type. The values below were read from the quenching tables of the
library QuEst calls (`IMP.bff.pet_quenching_reference()` and
`amino_acid_quenching_defaults(probe_radius=3.5)`):

| residue | $k_Q$ (1/ns) | contact from dye surface (Å) | $R_i$ from dye centre (Å) | quenching centre |
|---|---|---|---|---|
| TRP | 3.5 | 5.0 | 8.5 | indole ring (9 atoms) |
| TYR | 2.0 | 5.0 | 8.5 | phenol ring (7 atoms) |
| PRO | 2.0 | 4.0 | 7.5 | N, CB, CG, CD |
| MET | 1.67 | 3.5 | 7.0 | SD |
| HIS | 1.0 | 4.7 | 8.2 | imidazole ring (5 atoms) |
| CYS | 0.8 | 3.5 | 7.0 | SG |

The other fourteen residues have $k_Q = 0$. $R_i$ is the surface contact
distance plus the dye radius. These are starting values, meant to be calibrated
against measured donor lifetimes with a common scale factor on $k_Q$. They are
not fixed constants for every dye.

For T4 lysozyme (PDB 148L, chain E, 163 residues) the table counts 18
quenching residues: 3 Trp (126, 138, 158), 6 Tyr, 5 Met, 3 Pro and 1 His. The
structure is of a cysteine-free variant, so there is no Cys.

## Using it well

- **Compare sites, do not predict absolute lifetimes.** The dye is one sphere
  without orientation, the protein is one rigid structure, and adhesion is an
  isotropic slow factor. The numbers are reproducible, but their agreement
  with experiment is a separate question. A QuEst result is most useful as a
  comparison between candidate labelling sites.
- **Calibrate on several sites at once.** A single measured lifetime can be
  fitted by more than one combination of $k_Q$ scale and stickiness. Several
  sites fitted jointly separate the two.
- **Clean the structure.** Crystal waters and ligands block the AV and hide
  quenchers. Remove waters before simulating. Missing side chains remove
  quenching centres.
- **Static quenching is outside the model.** Dark complexes formed before
  excitation lower the brightness without changing the simulated decay.

## See also

- Guide: {doc}`/guides/80_quenching_estimator`.
- Fundamentals: {ref}`fundamentals-quenching-mechanisms`.
- Related concepts: {ref}`concept-accessible-volume` (where the dye can be),
  {ref}`concept-fret` (what donor quenching does to a FRET efficiency),
  {ref}`concept-fcs-correlation` (the bunching term PET-FCS reads),
  {ref}`concept-hydrodynamics` (diffusion coefficients).
- Implementation: the plugin is a shell around the `quest` package
  (`modules/quest`); the chemistry tables and kernels live in IMP.bff.

## References

- {cite}`peulen2017`: QuEst, and dynamic quenching in the analysis of
  time-resolved FRET.
- {cite}`doose2005`: dynamic and static quenching of an oxazine by tryptophan,
  and the need for contact.
- {cite}`vaiana2003`: dye–tryptophan contact complexes at atomic detail.
- {cite}`marme2003`: which dyes tryptophan quenches.
- {cite}`chen2010`: amino-acid quenchers of Alexa dyes.
- {cite}`neuweiler2003`, {cite}`doose2009`: PET-FCS.
- {cite}`rehm1970`: the driving force of electron-transfer quenching.
- {cite}`seidel1996`: nucleobase quenching tracks the redox potentials.
- {cite}`dimura2016`: accessible and contact volumes in quantitative FRET.
