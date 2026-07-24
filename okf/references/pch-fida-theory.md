---
type: Reference
title: PCH / FIDA theory and its ChiSurf mapping
description: Photon-counting-histogram and fluorescence-intensity-distribution-analysis theory (molecular brightness and occupancy from the amplitude of intensity fluctuations) and where each equation lives in the ChiSurf codebase.
resource: chisurf/core/models/pch/
tags: [pch, fida, brightness, single-molecule, fluctuation-spectroscopy, fcs, n-and-b]
timestamp: '2026-07-24T00:00:00Z'
---

# Purpose

Reference note for the **photon-counting histogram (PCH)** and
**fluorescence-intensity distribution analysis (FIDA)** models in ChiSurf: what
they measure, the equations, and the exact source locations. The user-facing
version is `docs/concepts/pch_fida.md`; this note keeps the code mapping and
citations for maintainers. The workflow guide is `docs/guides/04_fida_pch.md`.

# What PCH/FIDA measure

FCS reads the *temporal* structure of intensity fluctuations; PCH and FIDA read
their *amplitude* structure — the histogram `P(k)` of how many photons land in
a fixed sampling bin. That histogram separates two quantities a mean-intensity
trace cannot: the **molecular brightness** `ε` (counts per molecule per second)
and the mean **number of molecules** `N` in the detection volume. Brightness is
independent of diffusion time and concentration, so it resolves
stoichiometry/oligomerization (monomer vs. dimer at equal concentration) that
FCS alone leaves degenerate.

The signature is a **super-Poissonian** histogram: broader than a Poisson of the
same mean, because a random number of molecules occupy random positions in a
non-uniform detection volume.

# Equations and their code locations

## Moments / Number & Brightness (Qian & Elson 1990)

Mean and excess variance:

    <k> = ε N T
    Var(k) − <k> = ε² γ₂ N T           (γ₂ = 1/2^{3/2} for a 3-D Gaussian)

Apparent brightness `B = Var(k)/<k>`; for a photon-counting detector
`ε = B − 1` and `N = <k>/ε`. This is the low-order truncation of PCH/FIDA. The
QuickFit3 N&B help (`junk/quickfit3/plugins/numberandbrightness/`) gives the
detector-specific forms, including the EM-CCD excess-noise factor `F²` used for
analog detectors — not the confocal photon-counting path ChiSurf uses.

## Single-species PCH (Chen, Müller, Berland & Gratton 1999)

Single-molecule histogram = Poisson emission at local brightness
`ε·PSF(r)`, integrated over the PSF-weighted detection profile:

    p1(k) = (1/V) ∫_V  [ε PSF(r)]^k / k!  · exp(−ε PSF(r))  dr

ChiSurf uses the 3-D Gaussian profile `PSF ∝ exp(−2x²)`.
- `chisurf/plugins/pch/api/algorithms.py::compute_p1` / `pch_single_species`
  (numba, integrates over `x_vals` on `[0,5]` with the `exp(-2 x²)` weight).

Open-volume occupancy is Poisson(N), so the observed histogram is the
Poisson-weighted stack of self-convolutions of `p1`:

    P(k) = Σ_n Poisson(n; N) · (p1)^{∗n}(k)

- `pch_open_system` (Poisson.pmf weights × `convolve_pch_numba` repeated
  self-convolution).

## Multiple species — successive convolution

Independent species add counts, so histograms convolve:

    P = P1 ∗ P2 ∗ … ∗ P_S

- `pch_mixture` (FFT convolution `scipy.signal.fftconvolve` of per-species
  `pch_open_system`).

## FIDA — generating function (Kask, Palo, Ullmann & Gall 1999)

Probability generating function `G(ξ) = Σ_k P(k) ξ^k` turns convolutions into
products and the spatial integral into an exponent:

    G(ξ) = exp{ Σ_i N_i ∫₀¹ w(x) [ e^{(ξ−1) q_i x} − 1 ] dx  +  (ξ−1) λ_bg }

- `w(x)` = spatial brightness profile `dV/dx`, normalised `∫w dx = 1`; ideal
  3-D Gaussian gives `w(x) ∝ (−ln x)^{1/2} / x`
  (`chisurf/core/models/pch/fida.py::dvdx_gaussian`). A **non-ideal PSF**
  is handled by adjusting `w(x)` (Kask 1999 spatial corrections) — this is the
  key advantage over Gaussian-only PCH.
- `λ_bg` = mean background per bin.
- `P(k)` = Taylor coefficients of `G`, recovered by evaluating on the complex
  unit circle and inverse-FFT: `chisurf/core/models/pch/fida.py::fida_pch`.
- Fit: `fit_fida` — Levenberg–Marquardt on the multinomial residuals
  `fida_residuals` = `(n_bins·p_k − counts_k)/√(n_bins p_k (1−p_k))`, reduced
  χ² over `k_max − n_params`. Ported from Fretica `FPCHFida` / `FPCHFidaFit`.

# Relation to FCS and N&B

- **N&B** = first two moments of `P(k)`; PCH/FIDA fit the whole shape and so
  tolerate multiple species and background.
- **FCS** amplitude `G(0) ∝ 1/N` gives `N`; with the mean intensity,
  `ε = (I − B)/N` gives an *average* brightness entangled with the diffusion
  model. PCH/FIDA give a brightness *distribution* at one time scale,
  independent of diffusion — the stoichiometry axis FCS lacks. See
  `okf/references/fcs-model-theory.md` and `docs/concepts/fcs_correlation.md`.

# Plugin surface

`chisurf/plugins/pch/` (manifest `id: pch`, v2.0.0) exposes the analysis as a
client-server plugin:
- `pch.load_tttr` — TTTR metadata (channels, resolutions).
- `pch.compute` — bins the photon stream into `bin_time_us` intervals and
  histograms counts into `P(k)`; optional micro-time gate.
- `pch.fit` — multi-species fit returning per-species `epsilons`, `avg_Ns`,
  `fractions`, χ² statistics.
Backend `backend/services.py`, pure math in `api/algorithms.py`, GUI client
`gui/client.py` + `gui/tool.py`, CLI `pch analyze` / `pch refit`.

# References

- Chen, Y., Müller, J. D., Berland, K. M. & Gratton, E. (1999). The photon
  counting histogram in fluorescence fluctuation spectroscopy. *Biophys. J.*
  **77**, 553–567.
- Kask, P., Palo, K., Ullmann, D. & Gall, K. (1999). Fluorescence-intensity
  distribution analysis and its application in biomolecular detection
  technology. *PNAS* **96**, 13756–13761.
- Qian, H. & Elson, E. L. (1990). Distribution of molecular aggregation by
  analysis of fluctuation moments. *PNAS* **87**, 5479–5483.
