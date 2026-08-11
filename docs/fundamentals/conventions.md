---
type: Fundamentals
title: Symbols and conventions
description: Fluorescence notation is not uniform. The same letter means different things in the FRET and FCS literature, and the same quantity is written differently by different groups.
tags: [fundamentals, fret, fcs]
anchor: fundamentals-conventions
---

(fundamentals-conventions)=
# Symbols and conventions

Fluorescence notation is not uniform. The same letter means different things in
the FRET and FCS literature, and the same quantity is written differently by
different groups. This page records which spelling ChiSurf uses, what the
parameter is called in the code and interface, and which alternatives you will
meet elsewhere. It is a translation table, not a claim that one choice is
correct.

Read it when a number from a paper does not reproduce: more often than not the
formula is right and the convention is not.

## The excited state

| Quantity | ChiSurf | In code / UI | Also written |
|---|---|---|---|
| Fluorescence lifetime | $\tau$ | `t…`, `tau` | — |
| Radiative rate | $\Gamma$ | — | $k_r$, $k_f$ |
| Non-radiative rate (sum) | $k_{nr}$ | — | $k_{ic}+k_{isc}+\dots$ |
| Quantum yield | $Q$, donor $Q_D$ | — | $\Phi$, $\Phi_F$, $\phi$ |
| Natural (radiative) lifetime | $\tau_n$ | — | $\tau_r$, $\tau_0$ |
| Decay amplitude of species $i$ | $a_i$ | `x…` | $\alpha_i$, $A_i$, $B_i$ |
| Species fraction | $x_i = a_i/\sum_j a_j$ | `x…` | $\alpha_i$ (normalized) |
| Intensity fraction | $f_i = a_i\tau_i/\sum_j a_j\tau_j$ | — | $\beta_i$ |
| Species-weighted average | $\langle\tau\rangle_x$ | — | $\bar\tau$, $\tau_\text{amp}$, $\langle\tau\rangle_1$ |
| Intensity-weighted average | $\langle\tau\rangle_f$ | — | $\tau_\text{int}$, $\langle\tau\rangle_2$ |

:::{warning}
$\tau_0$ is used in the literature both for the natural lifetime $1/\Gamma$ and
for the unquenched lifetime in a Stern–Volmer plot. These are different
quantities. This documentation writes $\tau_n$ for the first and names the
second explicitly.
:::

## Anisotropy

| Quantity | ChiSurf | In code / UI | Also written |
|---|---|---|---|
| Time-resolved anisotropy | $r(t)$ | `r(t)` | $A(t)$, $P(t)$ (polarization, a different function) |
| Fundamental anisotropy | $r_0$ | `r0` | $r(0)$, $A_0$ |
| Residual anisotropy | $r_\infty$ | `rinf` | $r_\text{res}$, $r_\infty$ |
| Rotational correlation time | $\rho$ | `rho` | $\theta$, $\phi$, $\tau_r$, $\tau_c$ |
| Anisotropy amplitude of term $i$ | $\beta_i$ | `b` | $r_{0,i}$, $A_i$ |
| G-factor | $G$ | `g` | $G$, or its reciprocal — check which |
| Channel mixing | $l_1, l_2$ | `l1`, `l2` | $\ell_1,\ell_2$ |

Two traps here. **$\rho$ versus $\theta$**: Lakowicz and much of the older
literature write $\theta$ for the rotational correlation time; ChiSurf writes
$\rho$ throughout, in the docs and in the code, and reserves $\theta$ for a
geometric angle. **The G-factor's direction**: some instruments and papers
define $G$ as the reciprocal of the definition used here
({ref}`concept-anisotropy`), which inverts the correction. A $G$ applied the
wrong way round shifts the whole $r(t)$ curve and biases $r_0$ and $r_\infty$
without breaking the fit.

Note also that $\rho$ is a correlation time and the Perrin equation is written
here per molecule, $\rho = \eta V/(k_B T)$, where the classical form uses the
molar gas constant, $\rho = \eta V/(RT)$ with $V$ the molar volume. Both are the
same relation; mixing them costs a factor of Avogadro's number.

## FRET

| Quantity | ChiSurf | In code / UI | Also written |
|---|---|---|---|
| Transfer efficiency | $E$ | `E` | $E_\text{FRET}$, $\eta$, $T$ |
| Donor–acceptor distance | $R$ | `RDA` | $r$, $d$ |
| Förster radius | $R_0$ | `R0`, `forster_radius` | $R_F$, $R_0$ |
| Orientation factor | $\kappa^2$ | `kappa2` | $\kappa^2$ |
| Overlap integral | $J$ | `J` | $J(\lambda)$, $\Omega$ |
| Donor lifetime, no acceptor | $\tau_{D(0)}$ | — | $\tau_D$, $\tau_{D,0}$ |
| Donor lifetime with acceptor | $\tau_{DA}$ | — | $\tau_{D(A)}$ |
| Leakage / spectral crosstalk | $\alpha$ | `alpha` | $lk$, $ct$, $\beta$ |
| Direct acceptor excitation | $\delta$ | `delta` | $dir$, $de$, $\gamma$ |
| Detection/quantum-yield factor | $\gamma$ | `gamma` | $\gamma$ |
| Excitation flux ratio | $\beta$ | `beta` | $\beta$ |

The correction-factor letters are the least stable notation in the field.
ChiSurf follows the multi-laboratory benchmark convention
{cite}`hellenkamp2018`, in which $\alpha$ is leakage, $\delta$ is direct
excitation, $\gamma$ folds detection efficiency and acceptor/donor quantum-yield
ratio together, and $\beta$ is the excitation flux ratio
({ref}`concept-accurate-fret`). Papers predating that convention frequently swap
$\alpha$ and $\delta$, or bundle leakage into $\gamma$.

$R_0$ carries a hidden convention of its own: it is quoted for an assumed
$\kappa^2$, almost always $2/3$, and for a particular refractive index and donor
quantum yield. A tabulated $R_0$ is therefore not a constant of the dye pair
({ref}`fundamentals-energy-transfer`).

## FCS

| Quantity | ChiSurf | In code / UI | Also written |
|---|---|---|---|
| Correlation function | $G(\tau)$ | — | $g^{(2)}(\tau)$, $G(\tau)-1$ |
| Number of molecules | $N$ | `N` | $\langle N\rangle$, $1/G(0)$ |
| Diffusion time | $\tau_D$ | `tauD` | $\tau_\text{diff}$, $\tau_d$ |
| Lateral beam waist | $w_{xy}$ | `w_r` | $\omega_0$, $\omega_{xy}$, $r_0$ |
| Axial beam waist | $w_z$ | `w_z` | $\omega_z$, $z_0$ |
| Structure / aspect parameter | $\gamma$ | — | $p$, $s$, $\kappa$, $S$ |
| Anomalous exponent | $\alpha$ | — | $\alpha$ |

:::{warning}
Three collisions matter in practice, because both readings are plausible in a
multiparameter experiment:

- $\gamma$ is the FRET detection-correction factor **and** the FCS structure
  parameter $w_z/w_{xy}$.
- $\alpha$ is FRET leakage **and** the anomalous-diffusion exponent.
- $\tau_D$ is the FCS diffusion time; the donor-only *lifetime* is written
  $\tau_{D(0)}$ here for exactly this reason.
- $r_0$ is the fundamental anisotropy; some FCS literature uses $r_0$ for the
  lateral beam waist that this documentation calls $w_{xy}$.
- $G$ is the anisotropy G-factor **and** the correlation function $G(\tau)$.
:::

## Units

Every number ChiSurf holds is a plain number in a fixed unit. Nothing carries a
unit with it and nothing converts behind your back, so the table below is the
whole contract — a value you type into a field, read off a plot or find in a
file is in the unit given here.

| Quantity | Unit |
|---|---|
| Fluorescence lifetime $\tau$, decay time axis | nanoseconds |
| Rotational correlation time $\rho$ | nanoseconds |
| FCS correlation time, diffusion time $\tau_D$ | **milliseconds** |
| Burst duration, macro time | milliseconds |
| Micro-time (TAC) resolution | picoseconds |
| Macro-time resolution | nanoseconds |
| Count rate | kilohertz |
| $R_0$, $R_{DA}$, distance distributions | ångström |
| Atomic coordinates, radius of gyration | ångström |
| Wavelength | nanometres |

Two of these surprise people, and both are deliberate.

**Times are not all the same.** A fluorescence lifetime is nanoseconds and an
FCS correlation time is milliseconds, because that is what each field publishes;
forcing one unit on both would make one of them a number with six leading zeros.
The unit follows the *quantity*, not the dimension — $\tau$, $\rho$ and $\tau_D$
are all times and are not all in the same unit.

Note the two things called a correlation time. The **rotational** correlation
time $\rho$ of an anisotropy decay shares the decay's nanosecond axis; the
**translational** diffusion time $\tau_D$ of an FCS curve is milliseconds. They
differ by roughly six orders of magnitude and are easy to conflate by name
alone.

**Lengths are all ångström.** Structures, Förster radii, fitted distances and
distance distributions alike. Coordinates were once held in nanometres
internally, which meant a distance computed from coordinates and a distance
fitted from a decay could differ by a factor of ten with nothing to warn you;
they no longer do. Every structure format ChiSurf reads (PDB, mmCIF, DCD) is
already ångström, so nothing is rescaled on the way in.

ChiSurf uses per-molecule (Boltzmann) rather than molar (gas-constant) forms of
thermodynamic relations.

:::{warning}
The Förster-radius formula is evaluated with $J$ in M⁻¹ cm⁻¹ nm⁴ and the
prefactor $0.02108$, which yields $R_0$ in **nanometres**
({ref}`concept-fret`); {src}`chisurf/core/fluorescence/fret/forster.py#forster_radius`
converts and returns ångström. Literature formulas written in ångström use a
prefactor of $9.78\times10^3$, and some are written for $J$ in M⁻¹ cm³. The
difference is a power of ten and is easy to miss — check the units of an $R_0$
before combining it with a distance from anywhere else.
:::

Spectra carry a units convention too: an emission spectrum per unit wavelength
and the same spectrum per unit wavenumber have different shapes, and the overlap
integral is defined on one of them ({ref}`fundamentals-absorption-emission`).

### Units in saved files

A ChiSurf photon container (`.pto`) records the unit of every column beside the
column itself, so a table read back says what its numbers are without relying on
the column name. Names like `Duration (ms)` are still written for people and for
older tools, but they are no longer the only record.

## See also

- {ref}`concept-anisotropy` · {ref}`concept-fret` · {ref}`concept-accurate-fret`
  · {ref}`concept-fcs-correlation` for the definitions in context.
- Literature: {cite}`hellenkamp2018` for the FRET correction-factor convention;
  {cite}`lakowicz2006` for the classical notation this page translates from.
