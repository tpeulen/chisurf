---
type: PRD
prd: "76"
title: "PRD-76: PSF fitter — recovering the real detection profile from saturation FCS"
description: Make the detection profile a first-class, swappable, fittable object — saturation FCS gains Gauss-Lorentz/diffraction/measured/free-form profiles instead of the hard-coded 3-D Gaussian, and a power series is fitted globally to recover the real profile (and with it V_eff, gamma and absolute concentrations) rather than assuming one.
status: draft
phase: "unassigned"
resource: chisurf/core/fluorescence/fcs/
tags: [prd, fcs, psf, mdf, saturation, calibration, effective-volume, gamma-factor, power-series]
timestamp: '2026-08-04T00:00:00Z'
---

# Where to pick this up

Nothing is implemented yet. The order below is the intended one, and each item
says what it unblocks.

1. **The profile seam first (§1–§3).** Every other item depends on
   `saturated_curve_shape` taking a profile object instead of `w0, z0`. Until
   that lands, "more PSF shapes" and "fit the PSF" are the same work done twice.
2. **Take the power-scaling trap seriously when doing §3.**
   `excitation_rate_peak` hard-codes the *Gaussian* peak flux density
   `2*Phi_total/(pi*w0^2)`. Reusing it with a non-Gaussian profile does not
   fail — it silently rescales the excitation rate by a shape-dependent factor,
   so every recovered rate constant and cross-section comes out wrong while the
   curve still fits. The peak must be derived from the profile's own focal-plane
   area integral (§3.2).
3. **Measure the bias before building the fitter.** Simulate a curve from the
   Enderlein MDF (`enderlein.mdf`, already in the tree) or the tttrlib vectorial
   PSF, fit it with the Gaussian model, and record how far `N`, `V_eff` and `D`
   move. That number is the whole justification for §4 and belongs in this PRD
   once taken. Re-derive it with `pixi run` inside the `arm64` env.
4. **Then the fitter (§4) on simulated series, then on a real one.** The real
   series needs a reversibility check first (§7, hysteresis = bleaching, not
   saturation) or the recovered profile is a bleaching artefact.
5. **Not yet attempted, so not yet reverted:** nothing here has been tried and
   abandoned. The one approach deliberately *not* taken is a per-curve
   (non-global) PSF fit — §5 says why it cannot work.

# Summary

Every FCS model in ChiSurf describes the detection volume with two numbers,
`w_r` and `w_z`, under a 3-D-Gaussian assumption. The saturation engine
(`chisurf/core/fluorescence/fcs/saturation.py`) is no exception: it builds the
excitation profile from `_gaussian_psf`, derives the peak excitation rate from
the Gaussian peak flux density, and integrates on a grid sized in beam waists.
A real confocal detection profile — the molecule detection function (MDF), i.e.
excitation beam × collection efficiency through a finite pinhole — is not a
3-D Gaussian, and the difference propagates into every absolute quantity FCS
reports: `V_eff`, the concentration behind `N`, the `gamma` factor relating `N`
to molecular brightness, and the `D` inferred from `tau_D`.

This PRD does two things, which are one thing:

1. **Make the profile a swappable object.** Saturation FCS (and the analytic
   models beside it) get a `DetectionProfile` seam with several implementations
   — Gaussian, Gaussian beam with real axial divergence, the Enderlein
   Gauss–Lorentz MDF already in `enderlein.py`, a scalar/vectorial diffraction
   PSF from the optics engine already used by the PSF calculator, a *measured*
   profile from a bead scan, and a **free-form basis** whose shape parameters
   can be fitted.
2. **Fit the profile from the data.** A **power series** of FCS curves on a
   calibration dye, fitted globally against one photokinetic scheme (the
   machinery in `power_series.py`), constrains the profile's *shape* — because
   saturation flattens the profile progressively with power, and how `V_eff`,
   `tau_D` and the counts-per-molecule respond to that flattening depends on
   how the real profile falls off. That is the measurement this PRD turns into
   a tool: **the PSF fitter**.

The output is a calibrated, storable detection profile that the rest of the
suite consumes instead of `w_r`/`w_z`.

# Motivation

## The Gaussian is a fitting convenience, not the instrument

The 3-D Gaussian is used because it makes `G(tau)` analytic. It is known to be
a poor description of a confocal spot: the axial profile of a focused beam is
Lorentzian in `z`, the pinhole imposes an axial-position-dependent collection
efficiency `kappa(z)`, and a high-NA focus has diffraction structure that no
Gaussian reproduces. `enderlein.py`'s own module docstring says this plainly,
and `GeneralFCSModel` already offers an `"mdf"` diffusion mode for exactly that
reason — but the **saturation** path, which is the one that models the physics
at high power, is still Gaussian-only.

What the mismatch costs is not the curve shape (a wrong profile is absorbed by
a wrong `tau_D` and a wrong `N` — the fit still looks good) but the **absolute
numbers**:

- `V_eff = pi^1.5 w0^2 z0` is wrong, so the concentration behind `N` is wrong.
- The `gamma` factor (0.3536 for a 3-D Gaussian, different for every other
  profile) is wrong, so the molecular brightness and every PCH/N&B quantity
  derived from it is wrong.
- `D = w0^2/(4 tau_D)` inherits the error in `w0`.
- In a *global* fit across a power series, the wrong profile does not just bias
  the optics parameters — it leaks into the photokinetic rates, because the
  scheme is inferred from how the curve distorts with power and that distortion
  is profile-dependent.

## A bead scan does not answer this

ChiSurf already measures a PSF: the `psf_determination` plugin fits 3-D
Gaussians to bead scans, and `psf_calculator` computes scalar/vectorial PSF
volumes from NA, wavelength and immersion index. Neither is the quantity FCS
needs:

- A bead scan measures the **imaging** PSF of a fluorescent sphere, convolved
  with the bead size, usually on a different detection path and without the
  confocal pinhole configuration used for FCS.
- A computed PSF is the **excitation** field, not the MDF; it knows nothing
  about the pinhole, the magnification, or the emission wavelength's own
  collection efficiency.
- Neither sees the alignment state of the instrument on the day of the
  measurement, which is exactly what an FCS calibration is for.

They are excellent **priors and starting values** (§4.4), not the answer.

## Saturation is the probe, and it is already in the tree

At low power, `G(tau)`'s shape is degenerate in the profile: a wide range of
profiles fit one curve after `tau_D` and `N` adjust. Raising the power breaks
that degeneracy, because saturation acts *pointwise*: the bright centre
saturates first, the profile flattens toward a top hat, and the detection
volume expands. The engine already computes this (`saturated_curve_shape`
returns the shape with amplitude `V_0/V_eff`, the volume expansion) — the
observable consequences are

- `V_eff(P)` grows, seen as an apparent `N(P)` that rises with power;
- `tau_D(P)` grows, because the expanded volume takes longer to cross;
- the counts per molecule `CPM(P)` bends away from linear.

**How fast each of these responds to power depends on how much volume sits at
each intensity level — i.e. on the profile's fall-off.** A Gaussian, a
Gauss–Lorentz MDF and a diffraction-limited spot with side lobes flatten at
different rates. So a power series measures the profile, provided the
photokinetics are fitted at the same time — which is precisely what
`power_series.build_power_series_fit` was built to do (one
`FCSKineticsModel` per curve, scheme and optics linked, power fixed per curve).

This PRD adds the missing half: let the *optics* in that global fit be
something richer than two numbers, and let its shape be a fitted quantity.

# Design

## 1. One profile seam

New module `chisurf/core/fluorescence/fcs/profiles.py` defining a
`DetectionProfile` protocol. A profile is asked for its value on a
rotationally-symmetric `(r, z)` grid and for the scalars that the engine
currently derives from `w0, z0`:

```
class DetectionProfile(Protocol):
    def evaluate(self, r, z) -> np.ndarray        # normalized to 1 at (0, 0)
    def grid(self, n_r, n_z) -> tuple[r, z]       # its own convergent extent
    def focal_area_integral(self) -> float        # ∫∫ evaluate(r, 0) dA  (m^2)
    def v_0(self) -> float                        # ∫∫∫ evaluate dV       (m^3)
    def g_diff(self, tau, D) -> np.ndarray | None # analytic form, or None
    def parameters(self) -> FittingParameterGroup # what a fit may vary
```

Three points about this contract:

- **`focal_area_integral` replaces the Gaussian algebra.** It is what converts
  a measured total power to a peak excitation rate for *any* shape (§3.2).
- **`grid` belongs to the profile, not the engine.** `GRID_EXTENT_WAISTS = 5`
  is a Gaussian-specific truncation (§7).
- **`g_diff` returning `None` is normal.** Only the Gaussian and the Gaussian
  sum have closed forms; everything else goes through the numerical
  autocorrelation the engine already has (`fcs_numerical_g_diff`).

## 2. The profiles that ship

| Profile | Shape parameters | Where the physics comes from |
| --- | --- | --- |
| `Gaussian3D` | `w_r`, `w_z` | today's `_gaussian_psf` — the reference and the default |
| `GaussianBeam` | `w_r`, `lambda_ex`, `n` | real axial divergence `w(z) = w0 sqrt(1 + (lambda z / (pi w0^2 n))^2)`; `w_z` stops being free |
| `EnderleinMDF` | `w_0`, `R_0`, pinhole, magnification, `lambda_ex`, `lambda_em`, `n` | reuse `enderlein.py` (`mdf`, `Optics`) unchanged — it is already the Gauss–Lorentz MDF |
| `DiffractionPSF` | `NA`, `n`, `lambda`, polarization, scalar/vectorial | the optics engine behind `psf_calculator` (`CLSMSuperRes.psf_volume`), azimuthally averaged onto `(r, z)` (§7) |
| `MeasuredProfile` | interpolation + scale only | a bead stack or an averaged PSF from `psf_determination`, or a previously fitted profile reloaded |
| `GaussianSumProfile` | `n_components` × (`a_i`, `w_i`, `s_i`) | **the fittable free-form profile** (§4.2) |

`GaussianBeam`, `EnderleinMDF` and `DiffractionPSF` are the "sat FCS should
support more different PSFs" half of the request; `GaussianSumProfile` plus §4
is the "recover the real PSF" half.

## 3. The saturation engine takes a profile

`saturation.py` changes from "a Gaussian with `w0, z0`" to "a profile":

### 3.1 Signature

`saturated_curve_shape(..., w0, z0, ...)` becomes
`saturated_curve_shape(..., profile: DetectionProfile, ...)`, with a
`Gaussian3D(w_r, w_z)` constructed at the call sites that still pass two
numbers, so `FCSKineticsModel`, the `fcs_saturation_calc` plugin, its CLI and
its RPC service keep working unchanged. `compute_power_sweep`,
`fit_single_component` and `fit_two_components` follow.

### 3.2 The peak excitation rate must come from the profile

`excitation_rate_peak` currently computes
`sigma_abs * 2 * Phi_total / (pi * w0^2)`. The factor `2/(pi w0^2)` is `1/∫∫
gaussian dA` — Gaussian-specific. The general form is

```
k_exc(0,0) = sigma_abs * Phi_total / profile.focal_area_integral()
```

which reduces to the current expression for a Gaussian. **This is the single
most dangerous line in the change**: get it wrong and nothing raises — the
curve still fits, and the extinction coefficient, the rate constants and the
saturation power all come back scaled by a shape-dependent constant. A
guardrail test asserts the Gaussian profile reproduces the old value exactly,
and that a profile with twice the focal area halves the peak rate.

### 3.3 Volume reference and the zero-power limit

`v_0 = pi^1.5 w0^2 z0` becomes `profile.v_0()`, computed by quadrature on the
profile's own grid. The `power_W = 0` branch returns `profile.g_diff(tau, D)`
when the profile has a closed form, and otherwise the *numerical*
autocorrelation of the unsaturated profile — not the Gaussian. That branch is
currently documented as "the exact zero-power limit"; with a non-Gaussian
profile the Gaussian would no longer be a limit of anything.

### 3.4 Cache keys

`FCSKineticsModel`'s shape cache keys on `(power, extinction, matrices,
brightness, w_r, w_z, D)`. It must key on the profile's identity **and its
shape parameters**, or a fitted profile will silently reuse a stale curve while
the optimiser moves its parameters — the failure mode where a fit "converges"
because the model stopped responding.

## 4. The PSF fitter

### 4.1 What it is

A workflow, not a new optimiser: build the global power-series fit that
`power_series.py` already assembles, and add the profile's shape parameters to
`SHARED_PARAMETERS` (they describe the instrument, so they are the same for
every curve, exactly like `w_r`/`w_z` today). Power stays fixed per curve; `N`,
`b`, `bg` stay local.

### 4.2 The free-form profile

`GaussianSumProfile` represents the radial profile as a sum of Gaussians,
`U(r, z) = Σ_i a_i exp(-2 r^2 / w_i(z)^2)` with `w_i(z)` following the beam
divergence of component `i`. Two reasons for this basis rather than a spline or
a pixel grid:

- **It stays cheap.** Each Gaussian pair has an analytic diffusion
  autocorrelation, so the unsaturated limit and the low-power part of the
  series never touch the FFT path; only the saturated profile needs the
  numerical route.
- **It is regularizable.** Positivity (`a_i > 0`) and a monotone-decreasing
  radial profile are expressible as bounds and ordering constraints, and
  smoothness is a prior on the `a_i` — which the parameter-prior machinery from
  [PRD-61](prd-61.md) already supports, no new code.

`n_components` is chosen by model comparison, not by hand: 1 component *is* the
Gaussian, and each additional component must earn its degrees of freedom
(reduced chi², and the evidence/posterior tooling from
[PRD-70](prd-70.md) where available).

### 4.3 The observables it fits

The fitter is multi-observable — this is what makes the profile identifiable:

| Observable | What it constrains |
| --- | --- |
| `G(tau)` shape of every curve in the series | `tau_D(P)`, hence how the volume grows with power |
| `G(0)` / `N(P)` across the series | `V_eff(P)`, the volume expansion directly |
| counts per molecule `CPM(P)` | the fraction of the volume at low intensity — the profile's tails, which `G(tau)` is least sensitive to |
| two-focus / dual-focus separation, when available | an **absolute length scale**, independent of `D` |
| a calibration dye with a literature `D` | breaks the `D` ↔ `w_r` degeneracy |

`CPM(P)` is the addition worth stressing: the correlation curve is dominated by
the bright centre, while the saturation of the *total* count rate is dominated
by how much of the molecule's dwell time is spent in the wings. Fitting both
together is what separates "the profile is broad" from "the dye saturates
early".

### 4.4 Priors from the instrument

`psf_determination` (bead scan) and `psf_calculator` (NA/wavelength optics)
supply starting values and Gaussian priors for `w_r`, the axial ratio and the
NA-implied divergence. A "seed from bead scan" / "seed from optics" action on
the fitter, not a hard constraint — the point of the measurement is to let the
data disagree with the optics on paper.

## 5. Identifiability — stated up front

A per-curve profile fit **cannot work**, and this must be said before anyone
tries it: for a single curve, profile shape, `tau_D` and `N` trade off almost
exactly. The power series is not an accuracy improvement over a single curve,
it is the difference between an identifiable and an unidentifiable problem.

Even with a series, two degeneracies survive and must be reported rather than
hidden:

1. **`sigma_abs * P` versus `w_r`.** The peak excitation rate depends on the
   ratio `sigma_abs * Phi / area`; a smaller waist and a smaller cross-section
   produce the same saturation behaviour. Only the *shape* of the profile is
   determined by the series on its own. Anchoring the absolute scale requires
   an independent input — a known `D` for the calibration dye, a known
   extinction coefficient, or a two-focus separation. The fitter must refuse to
   report an absolute `V_eff` when none of the three is supplied, rather than
   reporting a number that is really a restatement of the assumed
   cross-section.
2. **Dark-state relaxation versus a fast diffusion component**, already named
   in `power_series.py`'s docstring. Unchanged by this PRD, but it interacts:
   an over-flexible profile can absorb a bunching term. The
   [PRD-68](prd-68.md)/[PRD-69](prd-69.md) posterior tooling (parameter
   correlations, profile scans) is the right way to show it, and the fitter
   surfaces the profile-parameter correlation block by default.

## 6. What consumes the recovered profile

The result is not a plot — it is a calibration other analyses use:

- **`V_eff` and `gamma`** for absolute concentrations and molecular brightness,
  consumed by the FCS models, PCH and N&B ([PRD-51](prd-51.md)).
- **A `MeasuredProfile`** loadable by `GeneralFCSModel`'s `"mdf"` mode and by
  `FCSKineticsModel`, so an ordinary fit runs on the calibrated profile.
- **A stored calibration record** — profile type, parameters, the series it
  came from, the dye and the date — registered in MMFDB like any other result,
  so the instrument state at the time of a measurement is recoverable later.
- **The brightness work**: [PRD-73](prd-73.md) and [PRD-75](prd-75.md) both
  divide by volume-dependent quantities; a wrong `gamma` biases the
  brightness-weighted amplitude.

## 7. Traps that will not announce themselves

- **Grid truncation.** `GRID_EXTENT_WAISTS = 5` is safe for a Gaussian, whose
  tail is negligible there. A Gauss–Lorentz axial profile falls off as `1/z^2`
  and a diffraction PSF has `~1/r` ring structure — truncating those makes
  `V_eff` **grid-dependent**, i.e. the answer changes when you change `n_r`.
  Every profile must therefore ship a convergence test (double the extent,
  `V_eff` moves less than a stated tolerance) as part of its contract, in the
  spirit of the existing warning in `emission_profile` about a non-decaying
  emission profile.
- **Rotational symmetry is assumed by the transform.** `fcs_numerical_g_diff`
  works on an `(r, z)` grid. A vectorial PSF with **linear** polarization is
  elliptical in the focal plane and is *not* rotationally symmetric; feeding it
  in azimuthally averaged is an approximation that must be documented, and
  circular polarization (already the `psf_calculator` default) is the supported
  case. Anything else needs a 3-D transform, which is out of scope here.
- **Saturation flattening mimics a broad profile.** A single high-power curve
  cannot distinguish "the profile is intrinsically flat-topped" from "the dye
  is saturated". Only the *power dependence* separates them, because the
  intrinsic shape does not change with power and the flattening does. A fitter
  that is handed one curve must say so instead of fitting.
- **Bleaching and flow masquerade as saturation.** Both reduce the apparent
  brightness at high power and both distort the curve. The protocol therefore
  requires an **ascending-then-descending** power series; hysteresis between
  the two branches is bleaching, and the fitter should flag it rather than
  fitting it as photophysics.
- **Detector dead time and afterpulsing** distort `G(tau)` at short lag and the
  count rate at high power — the same place saturation lives. The existing
  correction paths must be applied before the fit, and the fitter should warn
  when the count rate enters the dead-time-dominated regime.

## 8. Surfaces

- **Core:** `profiles.py`, the `saturation.py` refactor, and the fitter builder
  beside `power_series.py`. All Qt-free and headless-testable.
- **CLI:** a `csc`-reachable subcommand taking a folder of correlation curves
  plus their powers and writing the recovered profile and its uncertainties —
  the headless path is a requirement, not a follow-up.
- **RPC:** the fit as a backend service, following the plugin client-server
  standard.
- **GUI:** the `fcs_saturation_calc` plugin gains a *PSF* mode — profile picker,
  the series table (file, power), the seed-from-bead-scan/optics actions, and
  plots of the recovered radial/axial profile against the Gaussian it replaces,
  plus `V_eff(P)`, `tau_D(P)` and `CPM(P)` with the fit overlaid. AutoForm
  view.json, every control with a `description`, a `?` help section and a
  `gui/guide.json` guided tour driven by a **generated demo series** (simulate
  from a known profile, so the tour needs no user data). Screenshot-verified,
  per the project rule.
- **Docs:** `docs/concepts/fcs-detection-profile.md` (what the MDF is, `V_eff`
  and `gamma` for each profile, the saturation-as-probe argument, citations)
  and a numbered `docs/guides/NN_psf_from_fcs.md` walking a real series through
  the GUI, the CLI and the Python API.

# Definition of done

- [ ] `DetectionProfile` seam with the six profiles of §2, each with a
      convergence test for `V_eff`.
- [ ] `saturation.py` takes a profile; Gaussian path is **bit-for-bit
      unchanged** (regression test against the current outputs).
- [ ] `focal_area_integral` peak-rate derivation, with the guardrail test of
      §3.2.
- [ ] Cache keys include the profile's shape parameters (§3.4).
- [ ] Recovery test: simulate a series from an Enderlein MDF or a diffraction
      PSF, fit with `GaussianSumProfile`, recover `V_eff` and the radial profile
      within a stated tolerance; fit with `Gaussian3D` and **record the bias**
      in this PRD.
- [ ] Degeneracy test: the fitter refuses to report an absolute `V_eff` without
      an anchoring input (§5.1), and reports the profile/rate correlation block.
- [ ] Bleaching check: an ascending/descending series with simulated bleaching
      is flagged, not fitted.
- [ ] Headless CLI + RPC service + AutoForm GUI with `?`, guide and a generated
      demo; screenshots inspected.
- [ ] Concept page + numbered guide, cross-linked and registered in their
      indexes; plugin catalogue regenerated.
- [ ] Recovered profile is loadable by `GeneralFCSModel` and `FCSKineticsModel`
      and registered as an MMFDB calibration record.

# Relationships

- Builds directly on [PRD-74](prd-74.md) (the saturation/bunching modes) and the
  power-series global fit it introduced.
- Supplies the volume and `gamma` that [PRD-73](prd-73.md) and
  [PRD-75](prd-75.md) assume.
- Uses the parameter priors of [PRD-61](prd-61.md) for profile regularization
  and the posterior tooling of [PRD-68](prd-68.md)/[PRD-69](prd-69.md)/
  [PRD-70](prd-70.md) to report the degeneracies of §5.
- Consumes the bead-scan and optics PSFs from the `psf_determination` and
  `psf_calculator` plugins as priors, and hands `gamma` to the imaging
  correlation work in [PRD-51](prd-51.md).
- Extends the FCS model consolidation of [PRD-62](prd-62.md): the `"mdf"`
  diffusion mode becomes one instance of the general profile seam rather than a
  special case.

# References

- Enderlein, Gregor, Patra, Dertinger, Kaupp (2005), *Performance of fluorescence
  correlation spectroscopy for measuring diffusion and concentration*,
  ChemPhysChem 6, 2324 — the Gauss–Lorentz MDF and why the Gaussian biases
  absolute numbers. [10.1002/cphc.200500414](https://doi.org/10.1002/cphc.200500414)
- Widengren, Rigler (1996), *Mechanisms of photobleaching investigated by FCS*,
  Bioimaging 4, 149 — the power-series protocol.
- Dertinger et al. (2007), *Two-focus FCS: a new tool for accurate and absolute
  diffusion measurements*, ChemPhysChem 8, 433 — the external length scale of
  §4.3. [10.1002/cphc.200600638](https://doi.org/10.1002/cphc.200600638)
- Nagy, Wu, Berland (2005), *Observation volumes and gamma-factors in two-photon
  fluorescence fluctuation spectroscopy*, Biophys. J. 89, 2077 — `gamma` is
  profile-dependent. [10.1529/biophysj.104.052779](https://doi.org/10.1529/biophysj.104.052779)
- Richards, Wolf (1959), Proc. R. Soc. Lond. A 253, 358 — the vectorial
  diffraction PSF behind the optics engine.
