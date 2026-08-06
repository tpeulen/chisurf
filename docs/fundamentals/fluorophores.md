---
type: Fundamentals
title: Fluorophores
description: 'What the probe contributes and what it hides: the fluorophore classes, brightness and photostability, and what actually governs the choice of label.'
tags: [fundamentals, fluorophores]
anchor: fundamentals-fluorophores
---

(fundamentals-fluorophores)=
# Fluorophores

Nothing here is measured on the molecule of interest. It is measured on a
fluorophore, which is either part of the sample already or has been attached to
it. What the probe contributes — and what it hides — is set before any data are
taken. This page covers what to know about the probe classes and what actually
governs the choice.

## Intrinsic fluorophores

**Tryptophan** dominates the UV fluorescence of proteins. It absorbs near
280 nm and emits between roughly 310 and 350 nm depending on how buried it is,
which makes it a direct reporter of solvent exposure: a blue-shifted emission
means a buried residue, a red shift means exposure to water. Its lifetimes span
1–6 ns and are essentially never single-exponential, both because most proteins
contain several tryptophans in different environments and because the indole
side chain itself has multiple rotamers with distinct decay times.

Tryptophan is also quenched by a long list of nearby groups — protonated
histidine, disulfides, carboxylates, protonated amines — as well as by iodide
and acrylamide from solution. That sensitivity is what makes it useful and also
what makes intrinsic protein fluorescence hard to interpret quantitatively.

**Tyrosine** has a comparable quantum yield but a narrower emission band near
305 nm. In folded proteins it is often quenched, by interaction with the peptide
backbone or by energy transfer to tryptophan, so tyrosine emission frequently
appears on denaturation. **Phenylalanine** is only observed when a protein
contains neither of the other two, which is rare.

**NADH** absorbs at 340 nm and emits near 460 nm; the oxidized NAD⁺ is dark.
Free in buffer its lifetime is about 0.4 ns, shortened by stacking of the
adenine on the fluorescent nicotinamide ring. Bound to a protein the stacking is
prevented, the quantum yield rises several-fold, and the lifetime moves to
roughly 1–5 ns depending on the protein. **FAD** behaves oppositely: it is
quenched when its adenine stacks on the isoalloxazine, so the free cofactor has
a shorter lifetime than the bound one.

The free/bound lifetime contrast in both cofactors is the physical basis of
label-free metabolic FLIM ({ref}`concept-imaging-flim-phasor`), and it is a good
example of the general rule that lifetime changes report on contacts.

## Extrinsic labels

Synthetic dyes are used wherever a defined position, a defined photophysics, or
visible-wavelength excitation is needed. The practical families are rhodamines
and their sulfonated derivatives, cyanines, and the various commercial series
built from them.

Attachment is normally through maleimide chemistry to a cysteine thiol, or
NHS-ester chemistry to a lysine amine. Cysteine labelling is what
site-specific work uses, because a protein can be engineered to present exactly
one; lysine labelling is not site-specific and produces a distribution of
labelling positions, which is fatal for FRET and acceptable for a general
brightness stain.

What matters when choosing a dye for the methods in this documentation:

- **Photostability and total photon budget.** The number of photons a dye emits
  before bleaching sets what a single-molecule experiment can measure, far more
  than its peak brightness ({ref}`fundamentals-quenching`).
- **Little triplet and little blinking.** Dark-state excursions on microseconds
  contaminate correlation curves and broaden burst distributions.
- **Low stickiness.** A dye that adsorbs to the biomolecule reports its own
  binding equilibrium rather than the conformational change. This shows up as a
  reduced quantum yield, a long rotational correlation time, and a residual
  anisotropy close to that of the protein. Sulfonated, hydrophilic dyes are used
  because they stick less, not because they are brighter.
- **Environment insensitivity.** For FRET, a donor whose quantum yield varies
  with attachment position changes $R_0$ between constructs
  ({ref}`fundamentals-energy-transfer`). A dye that is a good polarity sensor is
  a bad FRET donor, for the same reason.
- **Lifetime matched to the motion of interest.** Anisotropy only sees rotation
  on the timescale of the lifetime ({ref}`fundamentals-polarization`).
- **Linker length.** A long linker decouples the dye from the biomolecule,
  giving the rotational freedom that justifies $\kappa^2 = 2/3$ — at the cost of
  a larger positional uncertainty that has to be modelled
  ({ref}`concept-accessible-volume`).

The last two points are in direct conflict, and the resolution is always a
compromise rather than an optimum.

ChiSurf ships reference spectra and properties for common dyes
({src}`chisurf/core/fluorescence/dyes.py#reference_dyes`), with Förster radii for
pairs held in the metadata store
({src}`chisurf/core/fluorescence/fret/forster.py#lookup_forster_radius`).

## Fluorescent proteins

Genetically encoded labels remove the labelling chemistry and guarantee
stoichiometry, at the cost of a large, slowly tumbling barrel attached to the
target. For the methods here that cost is substantial:

- The rotational correlation time of the barrel is tens of nanoseconds, so the
  dye orientation does not average during the excited-state lifetime and
  $\kappa^2 = 2/3$ is harder to justify than for a linker-attached dye.
- Many fluorescent proteins have multi-exponential decays and pH-dependent dark
  states.
- The chromophore sits inside the barrel, so the donor–acceptor distance has a
  floor of several nanometres set by the protein shells themselves.

They remain the right choice in cells, where site-specific chemical labelling is
the harder problem.

## Long-lifetime probes

Lanthanide chelates (europium, terbium) emit from shielded f-orbital
transitions, with lifetimes in the microsecond-to-millisecond range and
extremely narrow emission bands. The long lifetime allows time-gated detection
that discards all prompt autofluorescence and scatter, which is why they are
used in assay formats with poor optical backgrounds.

Their transfer distances are unremarkable despite the long lifetime, because
the transfer rate scales with the donor emission rate
({ref}`fundamentals-energy-transfer`).

## Quantifying a probe before trusting it

Two measurements, on the donor-only sample, decide whether the rest of an
analysis is meaningful:

- The **lifetime** compared with the free dye. A shortened lifetime means an
  added non-radiative route — usually contact quenching by a nearby residue —
  which changes $Q_D$ and therefore $R_0$.
- The **anisotropy decay**. A large residual anisotropy means the dye is not
  rotating freely, which invalidates the $\kappa^2$ assumption and widens the
  distance uncertainty ({ref}`fundamentals-polarization`).

Neither is optional in quantitative FRET work, and neither will be flagged by a
fit that only sees intensities.

## See also

- Previous: {ref}`fundamentals-energy-transfer`. Next:
  {ref}`fundamentals-solvent`.
- Concepts: {ref}`concept-accessible-volume` (linker clouds) ·
  {ref}`concept-imaging-flim-phasor` (cofactor FLIM) ·
  {ref}`concept-accurate-fret`.
- Implementation: {src}`chisurf/core/fluorescence/dyes.py#reference_dyes` ·
  {src}`chisurf/core/fluorescence/dyes.py#diffusion_coefficient_25C`.
- Literature: {cite}`lakowicz2006`, fluorophore and protein-fluorescence
  chapters.
