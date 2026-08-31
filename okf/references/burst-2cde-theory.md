---
type: Reference
title: "FRET-2CDE and ALEX-2CDE — kernel-density burst dynamics/heterogeneity filters"
description: The two-channel kernel density estimator (2CDE) of Tomov et al. 2012 — the per-photon KDE/nbKDE over photon arrival times, the FRET-2CDE within-burst dynamics score, and the ALEX-2CDE donor/acceptor brightness-heterogeneity purity score — mapped onto ChiSurf's burst_2cde plugin and the tttrlib.TwoCDE engine, with the exact formulas the reference NumPy fallback implements.
tags: [reference, bursts, 2cde, fret, alex, dynamics, purity, kde, pedagogy]
timestamp: '2026-07-24T00:00:00Z'
---

# FRET-2CDE and ALEX-2CDE — kernel-density burst filters

2CDE (**two-channel kernel density estimator**; Tomov, Best, Doose, et al.,
*Biophys. J.* **102**, 1163–1173, 2012, doi:10.1016/j.bpj.2011.11.4025) turns two
photon streams of a single-molecule FRET burst into a single per-burst number
that reports either **within-burst FRET dynamics** (FRET-2CDE) or **within-burst
brightness heterogeneity / impurity** (ALEX-2CDE). It is model-free and
bin-free: it operates directly on photon macro times.
This note records the algebra and how it maps onto the ChiSurf implementation;
the user-facing counterpart is `docs/concepts/burst_2cde.md` and its workflow
guide `docs/guides/01_fret_2cde.md`. See the sibling reference
[/references/smfret-burst-analysis.md](smfret-burst-analysis.md) for how the
burst stream, channels and $(E, S)$ are produced upstream.

## Photon-rate KDE primitive

The building block is a kernel density estimate of the local photon **rate**
around a photon, summed over a chosen channel and evaluated in *time* (not in
photon index). For the $i$-th photon of channel $X$ evaluated over channel $Y$
(Tomov eq. 4):

$$
\mathrm{KDE}_{X_i}^{Y} =
\sum_{j}^{N_{CHY}} \exp\!\left(-\frac{\lvert t_{(CHX)_i}-t_{(CHY)_j}\rvert}{\tau}\right)
\quad\text{(Laplace / symmetric-exponential kernel).}
$$

The self-channel term is de-biased (photon excluded, small-$N$ correction) into
the **nbKDE** (Tomov eq. 5):

$$
\mathrm{nbKDE}_{X_i}^{X} =
\left(1+\frac{2}{N_{CHX}}\right)
\sum_{j,\,j\ne i}^{N_{CHX}} \exp\!\left(-\frac{\lvert t_{(CHX)_i}-t_{(CHX)_j}\rvert}{\tau}\right).
$$

Kernel choice and its consequences (from the FRETBursts reference notes):

- **Laplace** (original Tomov): strong dependence of the estimate on the
  evaluation position; sampled *at* photon positions it always sits on the peak
  and over-estimates the rate — hence the explicit $(1+2/N)$ nbKDE correction.
- **Gaussian** $\exp(-(t_i-t_j)^2/2\tau^2)$: far weaker position dependence,
  accurate for rates above $\sim 1/(2\tau)$ cps; below that it depends on where
  the KDE is evaluated. ChiSurf exposes it as an alternative kernel.

$\tau$ is the kernel time constant: short enough to resolve intra-burst change,
long enough to gather several photons per kernel; default in ChiSurf is
$100\ \mu\mathrm{s}$, and $\sim 40\ \mu\mathrm{s}$ is a common tighter choice.
The KDE is evaluated over the **full photon stream** (`_kde_reference(ts, tau,
axis=macro, kernel)`) and only the resulting per-photon densities are sliced per
burst — restricting the KDE to the burst slice would starve edge photons of
legitimate neighbours and inflate 2CDE for short bursts. The burst enters through
the $(E)_D$ / $(1-E)_A$ averages and the small-$N$ factors, which use the burst's
own photon counts.

## FRET-2CDE (dynamics)

Donor- and acceptor-weighted efficiency estimates (Tomov eqs. 6, 7):

$$
(E)_D = \frac{1}{N_{CHD}}\sum_{i=1}^{N_{CHD}}
\frac{\mathrm{KDE}_{D_i}^{A}}{\mathrm{KDE}_{D_i}^{A}+\mathrm{nbKDE}_{D_i}^{D}},
\qquad
(1-E)_A = \frac{1}{N_{CHA}}\sum_{i=1}^{N_{CHA}}
\frac{\mathrm{KDE}_{A_i}^{D}}{\mathrm{KDE}_{A_i}^{D}+\mathrm{nbKDE}_{A_i}^{A}},
$$

$$
\mathrm{FRET\text{-}2CDE} = 110 - 100\,[(E)_D + (1-E)_A] \quad\text{(Tomov eq. 8).}
$$

Interpretation: when D and A brightness rise and fall *together* (static burst),
$(E)_D+(1-E)_A\approx 1$ and FRET-2CDE $\approx 10$, independent of the actual
$E$. When the molecule switches FRET state mid-burst, D and A brightness become
**anticorrelated in time**, the sum departs from 1, and FRET-2CDE rises (30–100
for clear ms dynamics). Practice: static baseline $\approx 10$; flag dynamic
above a $\approx 10$–$12$ cutoff. It is the KDE-based complement to Burst
Variance Analysis (`burst_bva`), which detects the same dynamics via excess
shot-noise variance.

## ALEX-2CDE (heterogeneity / purity)

On ALEX/PIE data the two streams are donor-excitation ($D_{ex}$) and
acceptor-excitation ($A_{ex}$). Cross-over-self brightness ratios (Tomov
eqs. 10, 11):

$$
BR_{D_{ex}} = \frac{1}{N_{CHA_{ex}}}\sum_{i=1}^{N_{CHD_{ex}}}
\frac{\mathrm{KDE}_{D_{ex,i}}^{A}}{\mathrm{KDE}_{D_{ex,i}}^{D}},
\qquad
BR_{A_{ex}} = \frac{1}{N_{CHD_{ex}}}\sum_{i=1}^{N_{CHA_{ex}}}
\frac{\mathrm{KDE}_{A_{ex,i}}^{D}}{\mathrm{KDE}_{A_{ex,i}}^{A}}.
$$

ChiSurf's engine combines these as

$$
\mathrm{ALEX\text{-}2CDE} = 100 - 50\,(BR_{D_{ex}} - BR_{A_{ex}}),
$$

which is the form `tttrlib.TwoCDE` implements. ChiSurf carried a NumPy port of
it until 2026-08-31; that port is gone, and the paragraph under *ChiSurf
mapping* records why. (Tomov eq. 12 writes the score with a sum of
the two ratios; the difference form used here is the FRETBursts/ChiSurf library
convention that yields a low value for pure single-pair bursts — treat the
ChiSurf implementation as authoritative for ChiSurf outputs.) Low ALEX-2CDE =
balanced, throughout-the-burst donor and acceptor brightness = one clean donor +
acceptor. High ALEX-2CDE flags donor-only/acceptor-only contamination, acceptor
blinking/bleaching mid-burst, or two coincident molecules. Used as a purity
gate: keep bursts below a $\approx 10$–$15$ cutoff before building $E$–$S$
histograms.

## ChiSurf mapping

- **Plugin**: `chisurf/plugins/burst/burst_2cde/` — client/backend split.
  - `core/computation.py`: dispatch only. `compute_2cde` groups bursts per
    source file and hands each to `tttrlib.TwoCDE`, which takes τ in **seconds**.
    A stream empty in a burst yields `NaN`.

    **There is no NumPy path any more.** `_kde_reference`, `_fret_2cde_numpy`
    and `_alex_2cde_numpy` were deleted on 2026-08-31 after an A/B on a real
    file (`test/data/tttr/BH/132/BH_SPC132.spc`, 120 bursts of 400 photons):
    three of the four variant/kernel combinations agreed with the compiled
    engine to **4e-16**, and the fourth — ALEX with a Gaussian kernel — differed
    on **every burst**, because `_alex_2cde_numpy` took no `kernel` argument and
    always used Laplace. `_compute_file_numpy` accepted `kernel` and dropped it
    on the ALEX branch. The parity test never caught this because it never
    passed a kernel; the replacement asserts instead that the two kernels give
    *different* answers, which is the property that was violated.

    The τ conversion went with it: `_macro_ticks` existed only because the NumPy
    kernels worked in ticks.
  - `api/models.py`: `TwoCdeSettings` (donor/acceptor channels + inclusive
    micro-time ranges, `acceptor_excitation_*` streams for ALEX, `tau`, `kernel`
    ∈ {laplace, gaussian}, `variant` ∈ {fret, alex}) and `TwoCdeResult`.
  - `backend/services.py`: RPC services `burst_2cde.jobs.compute` (long-running),
    `burst_2cde.workflow.prepare`, `burst_2cde.contract.describe`.
  - CLI `2cde compute`; guided-workflow one-liner `Bursts.two_cde(...)`.
- **Engine**: `tttrlib.TwoCDE` (base `tttrlib.BurstFeature`) — parallel over
  bursts, bit-exact against the NumPy reference; selected when `hasattr(tttrlib,
  "TwoCDE")`, else the NumPy fallback runs (`_compute_file_numpy`).
- **Persistence**: `write_2cde_analysis` writes one `<stem>.2c4` tab-separated
  companion per TTTR under a `2c4/` subfolder (the `…4` burst-companion family
  alongside `bg4`/`bv4`); ndX and the burst browser join it to the burst
  table by stem. Columns are `FRET-2CDE` / `ALEX-2CDE`.

## Provenance / bit-exactness

The NumPy path is the canonical reference and the C++ `TwoCDE` is validated
against it (see the memory note on numpy/C++ bit-exact parity: FMA contraction,
`np.histogram` binning, sliding-vs-recomputed sums). Any change to the kernel
cutoff, the nbKDE correction, the τ→ticks conversion, or the ALEX combination
must keep the two paths in lockstep and be checked in
`chisurf/plugins/burst/burst_2cde/tests/test_2cde.py`.
