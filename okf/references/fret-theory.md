---
type: Reference
title: Förster resonance energy transfer (FRET) theory
description: The dipole–dipole FRET mechanism, transfer rate, efficiency, Förster radius, overlap integral and orientation factor, mapped to the chisurf implementation.
resource: chisurf/core/fluorescence/fret/
tags: [fret, forster-radius, efficiency, orientation-factor, overlap-integral, fret-line, smfret, lifetime]
timestamp: '2026-07-24T00:00:00Z'
---

# Purpose

The foundational FRET physics on which most fluorescence-distance work in chisurf
builds: single-molecule burst analysis
([smfret burst analysis](/references/smfret-burst-analysis.md)), calibration
([fret calibration](/references/fret-calibration.md)), accessible-volume dye
modelling ([accessible-volume theory](/references/accessible-volume-theory.md)),
and the TCSPC lifetime route
([tcspc lifetime theory](/references/tcspc-lifetime-theory.md)). This note records
the physics and maps each quantity to the code that computes it. The user-facing
counterpart is `docs/concepts/fret.md` (anchor `concept-fret`).

# Mechanism

Non-radiative excitation transfer from an excited donor to a nearby acceptor via
**dipole–dipole coupling** in Förster's weak-coupling (incoherent) limit: the
chromophores keep their own spectra, transfer is rate-like, the coupling energy
scales as $1/R^3$ and the rate as $1/R^6$. No photon is emitted/reabsorbed and no
orbital overlap is needed — resonant Coulombic transfer over 2–10 nm, the useful
ruler range. Resonance = donor emission overlaps acceptor absorption; strength =
mutual dipole orientation.

# Core relations

Transfer rate for donor-only lifetime $\tau_D$ and separation $R$:

$$k_T(R) = \frac{1}{\tau_D}\left(\frac{R_0}{R}\right)^6.$$

Efficiency (three equivalent forms):

$$E = \frac{k_T}{k_T + 1/\tau_D} = \frac{1}{1 + (R/R_0)^6} = 1 - \frac{\tau_{DA}}{\tau_D},
\qquad R = R_0\left(\tfrac{1}{E}-1\right)^{1/6}.$$

$R_0$ = distance where $E = 1/2$ ($k_T = 1/\tau_D$). FRET averages the **rate**,
not the distance, so a distributed $P(R)$ must be efficiency-weighted before
inversion (three distance measures in
[accessible-volume theory](/references/accessible-volume-theory.md)).

# The Förster radius

$$R_0^6 \propto \kappa^2\, n^{-4}\, Q_D\, J,\qquad
R_0\,[\text{nm}] = 0.02108\,(\kappa^2\, n^{-4}\, Q_D\, J)^{1/6},$$

overlap integral (donor emission area-normalized, acceptor as **molar**
extinction $\varepsilon_A$ in $\mathrm{M^{-1}cm^{-1}}$):

$$J = \int f_D(\lambda)\,\varepsilon_A(\lambda)\,\lambda^4\,\mathrm{d}\lambda
\quad[\mathrm{M^{-1}cm^{-1}nm^4}].$$

Sixth-root dependence → robust to moderate $Q_D$/$J$ error. Screening $n^{-4}$,
default $n = 1.33$. Typical pairs $R_0 \approx 4$–$6$ nm.

## chisurf mapping

- `chisurf/core/fluorescence/fret/forster.py`:
  - `overlap_integral(wavelength_nm, donor_emission, acceptor_extinction)` → $J$;
    area-normalizes $f_D$ internally (donor scale irrelevant); $\varepsilon_A$
    must be **molar** (scaled by $\varepsilon_\text{max}$, not peak-normalized).
  - `forster_radius(J, donor_quantum_yield, kappa2=2/3, refractive_index=1.33)`,
    prefactor `_R0_PREFACTOR_NM = 0.02108`, returns Å (internal nm ×10).
  - `forster_radius_from_spectra(...)` convenience (overlap + R0 in one call).
  - `lookup_forster_radius(donor, acceptor, db)` → MMFDB tabulated $R_0$ for a
    named dye pair (`MFDatabase.lookup_forster_radius`).

# Orientation factor $\kappa^2$

$$\kappa^2 = (\cos\theta_{DA} - 3\cos\theta_D\cos\theta_A)^2 \in [0,4].$$

Default is the dynamic isotropic average $\langle\kappa^2\rangle = 2/3$ (code
default `kappa2=2/3`), valid for fast free reorientation vs $\tau_D$. Validity
judged by **anisotropy**: low $r_\infty$ → free rotation → $2/3$ holds; large
$r_\infty$ (sticky dye, ACV regime) → incomplete averaging → dominant residual
distance uncertainty. Couples FRET to
[anisotropy theory](/references/anisotropy-theory.md) and the ACV weighting in
[accessible-volume theory](/references/accessible-volume-theory.md).

# Measuring $E$

- **Intensity/ratiometric** (`fret/__init__.py`, `@nusiance` functions on green
  `Sg` / red `Sr`): `proximity_ratio` $= S_r/(S_g+S_r)$;
  `apparent_fret_efficiency` $= F_r/(F_g+F_r)$ after background+crosstalk;
  `fret_efficiency` adds detection $\gamma$ (`Gfactor`) and quantum yields
  `phiD`/`phiA`: $E = F_a/(F_g/(\gamma\phi_D)+F_a)$;
  `fluorescence_weighted_distance` → $R_{DA,E} = R_0(F_g/(\gamma\phi_D F_a))^{1/6}$;
  `fret_efficency_to_fdfa`/`fdfa2transfer_efficency` for $E \leftrightarrow
  F_D/F_A = (\phi_A/\phi_D)(1/E - 1)$. Apparent → accurate $E$ (leakage $\alpha$,
  direct excitation $\delta$, $\gamma$, $\beta$) is the burst correction algebra;
  calibration factors + light-path priors in `calibration.py` — see
  [fret calibration](/references/fret-calibration.md) and
  [smfret burst analysis](/references/smfret-burst-analysis.md).
- **Lifetime**: $E = 1 - \tau_{DA}/\tau_D$; self-calibrating, no reference. TCSPC
  donor decays resolve a *distribution* of distances. See
  [tcspc lifetime theory](/references/tcspc-lifetime-theory.md).
- **FRET-lines**: `fret/fret_line.py` `FRETLineGenerator` sweeps a model parameter
  and plots fluorescence-averaged vs species-averaged donor lifetime;
  static/dynamic FRET-lines diagnose conformational dynamics and dye artefacts.
  GUI plugin `chisurf/plugins/fret_line/`.
- **(Anti)correlation**: donor–acceptor anti-correlation / filtered-FCS report
  µs–ms exchange between FRET states.

# Ruler → structure

$E$ is a steep calibrated function of $R/R_0$; $R_0$ computable from spectra +
$Q_D$ → nanometre distances (spectroscopic ruler). A network of distances becomes
restraints in integrative modelling, dye linker clouds handled by accessible
volumes ([accessible-volume theory](/references/accessible-volume-theory.md)).

# Sources

- Förster, T. *Zwischenmolekulare Energiewanderung und Fluoreszenz.* Ann. Phys.
  **437**, 55–75 (1948).
- Lakowicz, J. R. *Principles of Fluorescence Spectroscopy*, 3rd ed. (2006), FRET
  chapters (overlap integral, $R_0$ prefactor $0.02108$, $\kappa^2$).
- Clegg, R. M. *Fluorescence resonance energy transfer.* Curr. Opin. Biotechnol.
  **6**, 103–110 (1995).
</content>
