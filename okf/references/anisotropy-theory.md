---
type: Reference
title: "Time-resolved fluorescence anisotropy — polarized VV/VH decay fitting"
description: The physics behind ChiSurf's time-resolved anisotropy analysis — polarized excitation/detection (VV/VH/VM), the anisotropy function r(t), the G-factor and channel-mixing corrections, the fundamental anisotropy r0, the rotational-correlation-time decay with a residual r-infinity, the Perrin equation linking rho to hydrodynamic volume/viscosity, and how the anisotropy rides on the intensity decay in a combined VV/VH fit — mapped onto chisurf's anisotropy kernels and lifetime models.
resource: chisurf/core/fluorescence/anisotropy/decay.py
tags: [reference, tcspc, anisotropy, polarization, vv-vh, rotation, perrin, pedagogy]
timestamp: '2026-07-24T00:00:00Z'
---

# Time-resolved fluorescence anisotropy — polarized VV/VH decay fitting

Fluorescence **anisotropy** measures the depolarization of emission as a
fluorophore rotates during its excited-state lifetime. It is the science/pedagogy
layer for chisurf's polarized-decay analysis — the anisotropy parameter group in
`chisurf/core/models/tcspc/anisotropy.py`, the VV/VH decay kernels in
`chisurf/core/fluorescence/anisotropy/decay.py`, and the combined-fit wiring in
`chisurf/core/models/tcspc/lifetime.py`. It sits alongside, and reuses, the
lifetime/reconvolution machinery documented in
[/references/tcspc-lifetime-theory.md](/references/tcspc-lifetime-theory.md):
anisotropy is never fit on its own, it rides on the intensity decay.

The user-facing counterpart is `docs/concepts/anisotropy.md`
(`concept-anisotropy`); this note keeps the chisurf-specific mapping and the code
seams. Terminology and formulas follow J. R. Lakowicz, *Principles of
Fluorescence Spectroscopy* (3rd ed., 2006), anisotropy chapters, and the Perrin
(Stokes–Einstein–Debye) rotational relation.

# Polarized channels: VV, VH, VM

Photoselection by a polarized excitation pulse creates an anisotropic excited
population. Two polarizer settings record it:

- **VV = $I_\parallel$** — emission polarized parallel to excitation.
- **VH = $I_\perp$** — emission polarized perpendicular.

The magic-angle setting **VM** ($54.7^\circ$) yields the anisotropy-free
intensity decay $I(t) = I_\parallel + 2I_\perp$; this is the pure lifetime decay.

chisurf's `Anisotropy.polarization_type` takes `vm`, `vv`, `vh`, or `vv/vh`.
In a fit group the polarization is assigned by group position
(`set_polarization_by_group_position`): a single fit gets `vm` (magic angle, all
rotation parameters auto-fixed); a stacked two-channel dataset gets `vv/vh`; a
two-fit group gets `vv` (index 0) and `vh` (index 1). The stacked VV/VH file
layout (two decays concatenated in one column) is the historic "jordi" format,
documented at [/references/vv-vh-decay-format.md](/references/vv-vh-decay-format.md).

# The anisotropy function and the G-factor

$$
r(t) = \frac{I_\parallel - G\,I_\perp}{I_\parallel + 2\,G\,I_\perp}
$$

The **G-factor** $G = S_\parallel / S_\perp$ corrects the detection system's
polarization bias (gratings/mirrors/detector transmit the two polarizations
unequally). It is measured from a depolarized reference and must be right or the
whole $r(t)$ curve shifts and biases $r_0$/$r_\infty$. In chisurf `g` is a
`FittingParameter` on the `Anisotropy` group, fixed by default (default `1.0`),
and — like `l1`/`l2` — is default-linked from the first fit to the others in a
VV/VH group (`_link_group_anisotropy_parameters`).

Two **channel-mixing** factors $l_1, l_2$ model imperfect-polarizer cross-talk
(defaults `l1=0.00308`, `l2=0.00368`):

$$
I_{\parallel,\mathrm{m}} = (1-l_1)I_\parallel + l_1 I_\perp, \qquad
I_{\perp,\mathrm{m}}     = l_2 I_\parallel + (1-l_2)I_\perp .
$$

These appear directly in `vm_rt_to_vv_vh` / `calculcate_spectrum` as the
`vv_j = vv*(1-l1) + vh*l1`, `vh_j = vv*l2 + vh*(1-l2)` mixing.

# Fundamental anisotropy r0 and the rotation spectrum

At $t=0$: $r_0 = \tfrac{2}{5}\big(\tfrac{3\cos^2\theta-1}{2}\big)$, set by the
absorption–emission dipole angle $\theta$; range $[-0.2, 0.4]$. chisurf default
`r0 = 0.38` (fixed).

The depolarization is a sum of exponentials in rotational correlation times,

$$
r(t) = \sum_i \beta_i e^{-t/\rho_i}, \qquad \sum_i \beta_i = r_0 .
$$

In code the components are `(_bs, _rhos)` pairs added via `add_rotation(b, rho)`;
`Anisotropy.b` normalizes the amplitudes and rescales to `r0`, `Anisotropy.rho`
returns the correlation times, and `rotation_spectrum` interleaves them as
$[\beta_1,\rho_1,\dots]$ — the exact analogue of the lifetime spectrum. A
**hindered/residual** anisotropy is a $\rho\to\infty$ component,
$r(t) = (r_0 - r_\infty)e^{-t/\rho} + r_\infty$, whose $r_\infty/r_0$ gives the
restricted-cone order parameter.

All interleaved pairs contribute. `vm_rt_to_vv_vh` previously strode the flat
spectrum with `range(0, n_anisotropies, 2)` where `n_anisotropies` was already
`len//2`, so only $(\beta_1,\rho_1)$ was ever read and every further rotation
component was silently dropped; fixed to iterate all `n_anisotropies` pairs. Only
this time-domain helper was affected — `calculcate_spectrum` (the fitting path)
composes spectra through `elte2`/`e1tn` and always handled every component.

# Perrin equation: rho, volume, viscosity

For a spherical rotor,

$$
\rho = \frac{\eta V}{k_\mathrm{B} T} = \frac{1}{6 D_r},
$$

and in steady-state form the **Perrin equation**

$$
\frac{r_0}{r} = 1 + \frac{\tau}{\rho} = 1 + \frac{k_\mathrm{B}T\,\tau}{\eta V}
$$

shows only motions on the lifetime scale $\tau$ are visible in the anisotropy.
chisurf reports this via `LifetimeModel.steady_state_anisotropy`, computed from
the interleaved product of the lifetime and rotation spectra
($\sum a_i\beta_j\tau_i\rho_j/(\dots) \big/ \sum a_i\tau_i$). The rotational
analogue of translational diffusion in FCS (rotational-diffusion terms in
diffusion-and-rotation FCS models) is the same $D_r$; see
[/references/fcs-model-theory.md](/references/fcs-model-theory.md).

# Coupling to the intensity decay (combined VV/VH fit)

The anisotropy is never fit as the raw ratio (noisy, non-Poisson). chisurf
reconstructs the two polarized decays from the magic-angle decay $f_\mathrm{VM}$
(the lifetime spectrum) and the rotation spectrum:

$$
f_\parallel(t) = f_\mathrm{VM}(t)\,(1 + 2 r(t)), \qquad
f_\perp(t)     = f_\mathrm{VM}(t)\,(1 - G\,r(t)).
$$

This is exactly `vm_rt_to_vv_vh` (time-domain) and `calculcate_spectrum`
(spectrum-domain, used by `Anisotropy.get_decay`). Both channels are then
reconvolved with the IRF and fit jointly against the measured VV and VH
histograms, lifetimes shared across channels, `g`/`l1`/`l2` linked. For
`vv/vh` the spectrum kernel returns the stacked `hstack([vv_mixed, vh_mixed])`
so one model curve serves both channels; for a two-fit group each fit computes
its own polarization. Fitting the shape difference between the channels (not the
ratio) is what lets $\rho_i$ shorter than the IRF be recovered.

## Code seams

- `chisurf/core/fluorescence/anisotropy/decay.py` —
  `vm_rt_to_vv_vh` (time-domain VV/VH from VM + rotation spectrum + `g`,`l1`,`l2`)
  and `calculcate_spectrum` (spectrum-domain, returns VV, VH, or stacked VV/VH).
- `chisurf/core/models/tcspc/anisotropy.py` — `Anisotropy` FittingParameterGroup:
  `r0`/`g`/`l1`/`l2` params, `_bs`/`_rhos` rotation components, `add_rotation`,
  `rotation_spectrum`, `polarization_type` + group-position assignment + VM
  auto-fix + cross-fit linking, plus VV/VH diagnostics extractors.
- `chisurf/core/models/tcspc/lifetime.py` — `steady_state_anisotropy`, the
  `r(t)` plot mode from VV/VH channels, and `get_decay` calling into the
  anisotropy group.
- `chisurf/core/models/tcspc/lifetime.view.json` — the editor `Anisotropy`
  section (polarization choice, rotation `(b,rho)` table), collapsed under VM.

## References

- J. R. Lakowicz, *Principles of Fluorescence Spectroscopy*, 3rd ed. (2006),
  anisotropy chapters — steady-state and time-resolved anisotropy, $r_0$, the
  Perrin equation, hindered rotors, the G-factor.
- F. Perrin, rotational depolarization (Stokes–Einstein–Debye rotational
  relation, $\rho = \eta V / k_\mathrm{B}T$).
- M. Koshioka, K. Sasaki, H. Masuhara, "Time-Dependent Fluorescence
  Depolarization Analysis in Three-Dimensional Microspectroscopy", *Applied
  Spectroscopy* 49 (1995) 224–228 — the VV/VH mixing form used in the kernels.
