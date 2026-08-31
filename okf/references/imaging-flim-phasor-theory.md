---
type: Reference
title: FLIM and the phasor approach — theory mapped to chisurf
description: Theory note on fluorescence-lifetime imaging (FLIM) and the phasor transform (universal semicircle, lever-rule fractions, calibration, FRET-by-phasor), mapped to the chisurf implementation.
resource: chisurf/core/fluorescence/imaging/pixel_maps.py
tags: [tcspc, flim, phasor, imaging, fret, clsm]
timestamp: '2026-07-24T00:00:00Z'
---

# Purpose

This note records the theory behind **fluorescence-lifetime imaging (FLIM)** and
the **phasor approach**, and maps each piece to where chisurf implements it. It
backs the user-facing concept page `docs/concepts/imaging_flim_phasor.md`
(`(concept-imaging-flim-phasor)`) and the CLSM guide `docs/guides/24_scan_images.md`.

# From TTTR to a lifetime image

A confocal scanning (CLSM) image has no camera frame: it is reconstructed from a
**TTTR photon stream** whose frame / line / pixel markers place each photon at a
scan position. A pixel is the set of photons recorded while the focus sat there;
their **micro times** (TCSPC delays after the pulse) accumulate into a per-pixel
decay $I(t)$. The intensity image is photon count per pixel; the lifetime image
summarizes each pixel's decay shape.

- Reconstruction engine: `tttrlib.CLSMImage` (`img.fill(tttr)`, `img.intensity`,
  `img.get_pixel_decays()`).
- Per-pixel FLIM tooling lives in the `microscopy/` plugin group; see
  [PRD-49](/prds/prd-49.md) (parity roadmap) and [PRD-52](/prds/prd-52.md)
  (phasor-FLIM imaging, the dedicated sub-PRD).

Two ways to reduce a pixel decay to an observable:

- **Fitting** — per-pixel maximum-likelihood exponential fits
  (`chisurf/plugins/microscopy/img_pixel_mle/`, `sm_image_mle/`, same `2I*` harness
  as burst MLE). Accurate but photon-hungry and slow.
- **Phasor** — a fit-free linear transform of the whole decay to one point.

# The phasor transform

Sine/cosine moments of the decay, normalized by its integral:

$$
g(\omega) = \frac{\int I(t)\cos(n\omega t)\,\mathrm{d}t}{\int I(t)\,\mathrm{d}t},
\qquad
s(\omega) = \frac{\int I(t)\sin(n\omega t)\,\mathrm{d}t}{\int I(t)\,\mathrm{d}t}.
$$

$\omega = 2\pi f$ is the laser repetition angular frequency; $n$ is the harmonic.
$(g, s)$ are the normalized real/imaginary parts of the decay's Fourier component —
brightness cancels, so the phasor encodes decay *shape*. The mapping is reciprocal:
a phasor-space ROI back-projects to exact image pixels.

**chisurf implementation** — the transform itself is the photon library's, and
chisurf holds no second copy of it:

- `tttrlib.DecayPhasor.compute_phasor_bincounts(bincounts, frequency, …)` for a
  decay histogram and `DecayPhasor.compute_phasor(micro_times, …, idxs)` for a
  selection of photons. `frequency` is in **cycles per micro-time channel**, so
  the physical $\omega = 2\pi f$ of the formula above becomes
  `frequency = f · dt`, and harmonic $n$ is just `n · f`. Photon positions are
  bin **indices**, i.e. left edges.
- `tttrlib.StreamingPhasor` for a live stream (used by the acquisition pipeline),
  `CLSMImage.get_phasor` per pixel, reached through
  `chisurf/core/fluorescence/imaging/pixel_maps.py::phasor_maps` / `phasor_frames`.
- IRF calibration (rotation + scaling onto the universal circle) is
  `DecayPhasor.g(g_irf, s_irf, g_exp, s_exp)` and `DecayPhasor.s(...)`; a
  degenerate `(0, 0)` IRF phasor raises rather than returning `nan`.

An in-tree `phasor_giw` / `phasor_siw` / `class Phasor` existed in
`core/fluorescence/tcspc/phasor.py` until 2026-08-31. It was unreachable — its
only consumer, `PhasorWidget`, was itself never instantiated — and it integrated
with `np.trapz` rather than summing, which half-weights the first and last
channel. On 2048 channels of `EasyTau300/215-268 D0.dat` the compiled transform
reproduces the definition to **8e-17** while the trapezoid form is off by
**~1e-4** in $(g, s)$ at 1, 2 and 4 cycles per window. Deleted, along with the
widget and its `.ui`.

Per-pixel `g,s` maps and phasor-plot tooling live in
`chisurf/plugins/microscopy/img_pixel_phasor/` (RPC surface: `phasor.describe`,
`phasor.apparent_lifetime`, `phasor.filter`, `phasor.component_fraction`,
`phasor.unmix`, `phasor.cursor_mask`, `phasor.pseudo_color`, `phasor.overlays`),
with `img_pixel_micro_time/` for the underlying per-pixel micro-time maps.

# Universal semicircle

A single exponential of lifetime $\tau$ maps to
$g = 1/(1+(\omega\tau)^2)$, $s = \omega\tau/(1+(\omega\tau)^2)$, which obey

$$
\left(g-\tfrac12\right)^2 + s^2 = \left(\tfrac12\right)^2 .
$$

All mono-exponentials lie on the **semicircle of radius $\tfrac12$ centred at
$(\tfrac12,0)$** (the *universal circle*, independent of sample). $\tau=0$ at
$(1,0)$, $\tau\to\infty$ at $(0,0)$; short lifetimes right, long lifetimes left,
apex at $\omega\tau=1$. Because the transform is linear, a mixture's phasor is the
intensity-weighted vector sum of its components, so **multi-exponential pixels fall
inside the arc** on the chord/polygon of their pure components.

# Lever-rule fractions

For a two-component pixel on chord $\overline{P_1P_2}$:

$$
f_1 = \frac{|P-P_2|}{|P_1-P_2|}, \qquad f_2 = 1-f_1 .
$$

Closer to a vertex ⇒ larger fractional-intensity contribution. Three components ⇒
barycentric weights inside triangle $P_1P_2P_3$. This is graphical unmixing — no
model, no starting values, no convergence (`phasor.component_fraction`,
`phasor.unmix`).

# Calibration

The IRF (laser-pulse width + detector/electronics timing) rotates and scales raw
phasors off the ideal circle. A one-point calibration against a **reference dye of
known single lifetime** $\tau_\text{ref}$ derives the fixed rotation+scaling that
map the measured reference onto its ideal circle position; the same correction is
applied to every pixel. No deconvolution needed.

# Fit-free FLIM and FRET-by-phasor

- Apparent phase/modulation lifetime read from angle/radius; cluster segmentation
  by cursors + back-projection (`phasor.cursor_mask`, `phasor.pseudo_color`).
- FRET shortens the donor lifetime, moving the donor phasor off its unquenched
  position toward shorter lifetime along a **FRET trajectory** (a curve, since
  unquenched donor + background + autofluorescence each have their own phasor).
  Per-pixel $E$ is the projection onto that trajectory — fit-free. In chisurf the
  FRET phasors come from `Phasor.set_fd0_fda_et` (`fd0`, `fda`, `et`).

Phasors give speed, robustness, model-free overview (segmentation, screening,
state separation); explicit multi-exponential fits still win for resolving actual
per-pixel amplitudes/lifetimes. The two are complementary.

# Related concepts

- User page: `docs/concepts/imaging_flim_phasor.md`.
- CLSM guide: `docs/guides/24_scan_images.md`.
- FCS correlation concept (companion single-molecule/confocal analysis):
  `docs/concepts/fcs_correlation.md`.

# References

- Digman MA, Caiolfa VR, Zamai M, Gratton E. *The phasor approach to fluorescence
  lifetime imaging analysis.* Biophys J 94(2): L14–L16 (2008).
  doi:10.1529/biophysj.107.120154.
- Jameson DM, Gratton E, Hall RD. Foundational phasor (polar-plot) treatment of
  lifetimes and polarization.
- Colyer RA, Siegmund OHW, Tremsin AS, Vallerga JV, Weiss S, Michalet X. Phasor
  (AB polar-plot) imaging with a widefield photon-counting detector.
- Malacrida L, Ranjit S, Jameson DM, Gratton E. *The phasor plot: a universal
  circle to advance fluorescence lifetime analysis and interpretation.*
  Annu Rev Biophys 50: 575–593 (2021).
</content>
