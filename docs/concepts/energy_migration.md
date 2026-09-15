---
type: Concept
title: Homo-transfer and energy migration
description: Förster transfer between two chemically identical fluorophores is called homo-transfer, or energy migration.
tags: [concepts, fret, energy, migration]
anchor: concept-energy-migration
---

(concept-energy-migration)=
# Homo-transfer and energy migration

Förster transfer between two *chemically identical* fluorophores is called
homo-transfer, or energy migration. It obeys the same $1/R^6$ physics as
donor–acceptor FRET ({ref}`fundamentals-energy-transfer`) but is almost invisible
to the observable everyone reaches for first — because donor and acceptor are the
same species, the excitation moves without the emission spectrum or the total
intensity changing at all.

This page covers how to detect it, when it is a nuisance and when it is the
measurement, and what ChiSurf's PDDEM model extracts from a decay.

## Why it hides

Consider what each observable sees when excitation hops from one dye to an
identical neighbour:

| Observable | Effect of homo-transfer |
|---|---|
| Emission spectrum | none — the acceptor emits where the donor would |
| Total intensity | none, unless the two positions have different quantum yields |
| Fluorescence lifetime | none, for identical dyes in identical environments |
| **Anisotropy** | **large** — each hop re-randomizes the emission dipole |

Depolarization is therefore the primary signature, and it was historically the
first one observed: fluorophore solutions lose anisotropy as concentration rises,
long before any of them are close enough to interact chemically
({ref}`fundamentals-polarization`).

The condition for homo-transfer is a **small Stokes shift**, which is what makes
a dye's own emission overlap its own absorption. Fluorescein and the BODIPY dyes
are the standard examples; quinine, with a large shift, does not migrate. A dye
chosen for a large Stokes shift to simplify filtering is, for the same reason,
unlikely to migrate.

## Two situations, opposite intentions

**As a nuisance.** Labelling a biomolecule with several copies of the same dye
does not make it proportionally brighter. Past a handful of labels the intensity
*falls*, because migration delivers excitation to whichever copy is most quenched
and because contact between dyes opens non-radiative routes — self-quenching
({ref}`fundamentals-quenching`). The practical rule is that a labelling density
optimized by eye is usually past the optimum, and that anisotropy is the cheap
diagnostic: a labelled construct with a lower anisotropy than the free dye at the
same viscosity has migration, not faster rotation.

It also biases anything read off the anisotropy. A rotational correlation time
fitted on a multiply labelled sample is contaminated by a depolarization
mechanism that has nothing to do with rotation, and the fitted $\rho$ comes out
too short.

**As the measurement.** Because the transfer still goes as $1/R^6$, migration
between two identical dyes is a ruler over the same distance range as ordinary
FRET — with the practical advantage that only one labelling chemistry is needed
and no correction factors for leakage, direct excitation or detection efficiency
apply ({ref}`concept-accurate-fret`). What it costs is that the signal has to be
extracted from a decay or an anisotropy rather than read as a photon ratio.

## PDDEM: what the model does

Two identical dyes at two *non-equivalent* sites are not one species. They differ
in local quenching, in orientation, and therefore in decay. Excitation migrating
between them produces a decay that is not the decay of either.

ChiSurf's **partial donor–donor energy migration** model
(`FRET: PDDEM`, {cite}`kalinin2004`) describes exactly this: two donor
populations $A$ and $B$, each carrying its own multi-exponential lifetime
spectrum, coupled by transfer rates in **both** directions. The parameters that
matter, beyond the two decays:

- **$\alpha_A$, $\alpha_B$** — the transfer efficiencies $A\!\to\!B$ and
  $B\!\to\!A$. They are independent, and their inequality is what "partial"
  refers to: migration is not symmetric when the two sites are not equivalent.
- **Excitation probabilities $p_x^A$, $p_x^B$** — how the initial excitation is
  divided between the sites, set by the two absorption cross-sections at the
  excitation wavelength.
- **Emission probabilities $p_m^A$, $p_m^B$** — how much of each site's emission
  reaches the detector, set by the detection band.

The transfer rate is taken from a **distance distribution** rather than a single
distance, using the same Gaussian machinery as the other FRET models, so a spread
of separations gives a spread of migration rates
({ref}`concept-distance-distributions`).

The two directions being separate parameters is the point of the model. A
symmetric treatment would be a single migration rate and would fit a
back-and-forth exchange between two identical environments; the asymmetry is what
carries the information that the two sites are different.

## Beyond a pair: many acceptors and dimensionality

The single-distance expression assumes one donor and one acceptor. When
acceptors are distributed rather than placed — dyes in a membrane, on a surface,
or free in solution — the donor decay takes a different functional form
altogether, and its shape depends on the **dimensionality** of the distribution:
one, two or three dimensions each give a distinct decay law.

Two consequences worth knowing before fitting such a sample:

- The observable is a **surface or volume density of acceptors**, not a distance.
  Fitting a distance to a acceptor population spread at random returns a number with
  no physical referent.
- The decay is strongly non-exponential by construction, so a multi-exponential
  fit will describe it with components that are not species. This is the same
  trap as in {ref}`concept-maximum-entropy`, arriving from a different direction.

For a randomly acceptor population spread at random there is a characteristic
concentration at which transfer becomes efficient, set by $R_0$ — for
$R_0 = 25$ Å it is in the tens of millimolar, which is why homo-transfer between
freely diffusing dyes needs concentrations far above those used in
single-molecule work and is a non-issue there.

## Reading a result

- **Check the anisotropy first.** If a construct's anisotropy is not depressed
  relative to the free dye, there is no migration to model, and a PDDEM fit will
  find transfer efficiencies that are fitting something else.
- **Do not read $\alpha_A \ne \alpha_B$ as an error.** Asymmetric efficiencies
  are the expected result for non-equivalent sites; symmetric ones are the
  special case.
- **Fix what you can measure.** The excitation and emission probabilities follow
  from the spectra and the filter set. Releasing all of them alongside two
  lifetime spectra and a distance distribution over-parameterizes the fit badly
  ({ref}`concept-parameter-uncertainty`).
- **Rule out simple heterogeneity.** Two non-interacting populations with
  different decays also give a non-exponential decay. What distinguishes
  migration is that the *anisotropy* decays faster than rotation alone accounts
  for.

## See also

- Fundamentals: {ref}`fundamentals-energy-transfer` (the mechanism, and why
  homo-transfer does not change the lifetime) ·
  {ref}`fundamentals-polarization` (depolarization as the detection route) ·
  {ref}`fundamentals-quenching` (self-quenching at high labelling density).
- Guide: {doc}`/guides/10_lifetime_anisotropy_fitting` — migration is detected
  in the anisotropy, so that is where a suspected case starts.
- Manual: {doc}`/manual/partial_donordonor_energy_migration` — the parameters as
  they appear in the model editor.
- Related concepts: {ref}`concept-fret` · {ref}`concept-anisotropy` ·
  {ref}`concept-distance-distributions` · {ref}`concept-maximum-entropy`.
- Implementation: the IMP.bff description `tcspc_pddem` (IMP.bff's
  `data/model_search/tcspc_pddem.json`); ChiSurf's editor is generated from it
  by `chisurf.core.models.description`.
- Literature: {cite}`kalinin2004` for the PDDEM treatment;
  {cite}`lakowicz2006`, the energy-transfer chapters, for homo-transfer and for
  transfer to acceptors distributed in one, two or three dimensions.
