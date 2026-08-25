---
type: Fundamentals
title: Solvent and environmental effects
description: The same dye has different spectra, different quantum yields and different lifetimes depending on where it sits.
tags: [fundamentals, spectra, solvent, environment]
anchor: fundamentals-solvent
---

(fundamentals-solvent)=
# Solvent and environmental effects

The same dye has different spectra, different quantum yields and different
lifetimes depending on where it sits. This is the mechanism behind
environment-sensing probes, and it is the reason a Förster radius or a reference
lifetime measured on free dye does not transfer to a conjugate.

## General solvent effects

Most fluorophores have a larger dipole moment in $S_1$ than in $S_0$. After
excitation the solvent shell reorients around the new dipole, lowering the
energy of the excited state before emission. The more polar the solvent, and the
more it can reorient, the further the emission red-shifts.

The Lippert–Mataga equation {cite}`lippert1955,mataga1956` makes this
quantitative. The Stokes shift, in
wavenumbers, is

$$
\bar\nu_A - \bar\nu_F = \frac{2}{hc}\,\Delta f\,
\frac{(\mu_E - \mu_G)^2}{a^3} + \text{const},
$$

where $\mu_E$ and $\mu_G$ are the excited- and ground-state dipole moments, $a$
is the radius of the cavity the fluorophore occupies, and

$$
\Delta f = \frac{\varepsilon - 1}{2\varepsilon + 1}
         - \frac{n^2 - 1}{2n^2 + 1}
$$

is the orientation polarizability, built from the solvent's static dielectric
constant $\varepsilon$ and refractive index $n$.

The structure of $\Delta f$ is the informative part. The refractive index term
describes the redistribution of *electrons* in the solvent, which is
instantaneous and therefore stabilizes ground and excited states about equally —
it shifts both, and largely cancels from the Stokes shift. The dielectric term
includes the reorientation of whole solvent *molecules*, which takes time and so
stabilizes only the excited state, after absorption and before emission. The
difference of the two is what produces a Stokes shift. This is why a solvent can
be highly refractive without being a strong shifter, and why polarity and
polarizability must be kept apart.

Lippert–Mataga is a continuum approximation: the fluorophore is a point dipole
in a uniform dielectric. It ignores the polarizability of the fluorophore itself
and any specific chemistry.

## Specific effects

Deviations from the continuum prediction are usually the interesting part.
Hydrogen bonding to the fluorophore, charge-transfer character in the excited
state, and preferential solvation in mixed solvents all shift emission by
amounts the general theory does not predict, and they do so
non-monotonically in solvent polarity. A plot of Stokes shift against $\Delta f$
that is linear for aprotic solvents and off the line for alcohols and water is
the standard diagnostic.

Excited-state proton transfer belongs here too: a fluorophore whose
$\mathrm{p}K_a$ changes on excitation can lose or gain a proton within the
excited-state lifetime and emit as a chemically different species
({ref}`fundamentals-absorption-emission`).

### Empirical scales, when one axis is not enough

The continuum model has exactly one knob, $\Delta f$, so it can only say that a
solvent is more or less polarizing. Real fluorophores respond to several
distinct properties that $\Delta f$ blends together, which is why the
alcohols-and-water points fall off the line rather than scattering about it.
The empirical scales exist to separate those properties, by measuring them with
probe molecules instead of deriving them from bulk constants.

The **Kamlet-Taft** decomposition uses three {cite}`kamlet1983`:

- $\pi^*$ — dipolarity/polarizability, the part the continuum model already
  approximates;
- $\alpha$ — the solvent's hydrogen-bond *donor* strength, which is what makes
  water and the alcohols special;
- $\beta$ — its hydrogen-bond *acceptor* strength.

Any solvent-dependent quantity is then fitted as a linear combination,

$$
XYZ = XYZ_0 + s\,\pi^{*} + a\,\alpha + b\,\beta ,
$$

and the useful output is not the fit quality but the *coefficients*: a dye whose
emission maximum has a large $a$ and a small $s$ is telling you it is
hydrogen-bonded in the excited state, not merely sitting in a polar medium. That
is a mechanistic statement the Lippert-Mataga plot cannot make.

**Reichardt's $E_\mathrm{T}(30)$** goes the other way and compresses everything
into one number, the transition energy of a betaine dye chosen because its
charge-transfer band is unusually sensitive {cite}`reichardt1994`. It is
convenient, widely tabulated, and — being one number — reintroduces exactly the
blending Kamlet-Taft separates. Use it to *rank* environments, not to explain
one.

Two cautions before applying either to a labelled biomolecule. Both scales are
calibrated on small probes in bulk solvents, and a dye tethered to a protein is
in none: its environment is heterogeneous over the linker's reach, partly
ordered, and may not have relaxed at all ({ref}`fundamentals-lifetime-quantum-yield`).
And a fitted coefficient is a correlation over a solvent series, so reading one
off a *single* measured environment is not something the framework supports.
What the scales are good for here is comparative — the same construct in two
buffers, or a dye before and after a conformational change — where the axis that
moved is the result.

## Relaxation on the lifetime timescale

The treatment above assumes solvent relaxation is complete before emission. That
is true in fluid solution at room temperature, where relaxation takes
picoseconds and the lifetime is nanoseconds. It stops being true in viscous
media, in glasses, at low temperature, and — importantly here — for a dye buried
in a protein or a membrane, where the local relaxation time can be comparable to
the lifetime.

When relaxation and emission are on the same timescale the emission spectrum
shifts *during* the decay. The observable consequences are specific and easy to
misdiagnose:

- The decay measured on the blue edge of the emission band is faster than the
  average, and the decay on the red edge shows a rise term — a negative
  amplitude — because that part of the population is still being created by
  relaxation while it decays.
- A global fit across emission wavelengths that does not allow negative
  amplitudes will absorb this into extra positive exponentials and report
  spurious species.
- The apparent lifetime becomes emission-wavelength dependent, which is
  otherwise a signature of multiple species.

A negative pre-exponential amplitude on the red edge is the clean diagnostic for
relaxation, and distinguishes it from ground-state heterogeneity, which produces
positive amplitudes at all wavelengths.

## Why this matters for the quantitative methods

Environment sensitivity is a nuisance parameter in almost everything except
sensing:

- **$R_0$ is not transferable.** It depends on $Q_D$ and on the refractive index
  of the medium between the dyes ({ref}`fundamentals-energy-transfer`). Both
  change between free dye in buffer and a dye conjugated near a hydrophobic
  pocket. The $n^{-4}$ dependence makes the choice between $n = 1.33$ for water
  and $n = 1.4$ for a protein interior a several-percent effect on $R_0$, which
  is small but systematic.
- **A donor whose quantum yield differs between conformational states** makes
  the measured efficiency depend on the state through $R_0$ as well as through
  distance. The two are not separable from intensities alone.
- **The detection correction factor $\gamma$ folds in the acceptor/donor
  quantum-yield ratio**, so an environment-sensitive dye makes $\gamma$
  state-dependent, which is an assumption the standard correction scheme does
  not make ({ref}`concept-accurate-fret`).
- **Viscosity and local rigidity** set the rotational correlation time and the
  residual anisotropy, and hence the $\kappa^2$ bounds
  ({ref}`fundamentals-polarization`).

The practical consequence is the same one as in the previous page: characterize
the probe in the actual construct rather than trusting a table.

## See also

- Previous: {ref}`fundamentals-fluorophores`. Next:
  {ref}`fundamentals-instrumentation`.
- Concepts: {ref}`concept-tcspc-lifetime` (wavelength-dependent decays and
  negative amplitudes) · {ref}`concept-accurate-fret` ·
  {ref}`concept-imaging-flim-phasor`.
- Literature: {cite}`lippert1955` · {cite}`mataga1956` ·
  {cite}`lakowicz2006`, solvent-effects and spectral-relaxation
  chapters. For the empirical scales, {cite}`kamlet1983` is the
  three-parameter decomposition and its tabulated values;
  {cite}`reichardt1994` the single-parameter $E_\mathrm{T}(30)$ alternative.
