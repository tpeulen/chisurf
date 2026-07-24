---
type: Reference
title: "Filtered FCS (fFCS/FLCS) and 2D-FLCS: theory mapped to ChiSurf"
description: The micro-time statistical-filter theory behind fFCS/FLCS and 2D-FLCS, and how each piece maps onto ChiSurf's filtered.py, fcs_filter_calculator, and flc_2d code.
tags: [reference, fcs, flcs, 2d-flcs, lifetime, filters, theory]
timestamp: '2026-07-24T00:00:00Z'
---

# Filtered FCS (fFCS/FLCS) and 2D-FLCS — theory ↔ ChiSurf

This note is the **theory reference** for the micro-time statistical-filter family
of correlation methods and the exact map onto ChiSurf's implementation. For the
**port status and remaining gaps** (what was verified against the reference
implementation, what is still missing) see the companion
[/references/fcs-pam-port.md](/references/fcs-pam-port.md) — this note complements
it (theory + code map) and does not repeat the status ledger. Ordinary
(unfiltered) FCS theory is in [/references/fcs-model-theory.md](/references/fcs-model-theory.md);
the FCS plugin group overview is [/plugins/fcs.md](/plugins/fcs.md). The
user-facing page is `docs/concepts/filtered_fcs.md`.

## Core idea

Every photon carries a **micro-time** $t$ (TCSPC arrival time relative to the
excitation pulse). Species that share a diffusion time can still differ in their
micro-time fingerprint — the fluorescence-decay pattern. Filtered FCS assigns each
photon a per-species **weight** (filter value) from its micro-time and correlates
the *weighted* streams, so the resulting curves are species-selective. Names for
one idea:

- **FLCS** — fingerprint is a lifetime pattern (Böhmer 2002; Kapusta 2007).
- **fFCS / species-FCS** — MFD generalisation where the pattern may also encode
  polarisation/spectrum, and the outputs are species auto- **and** cross-CFs
  (Felekyan 2012).
- **2D-FLCS** — two-dimensional lifetime–lifetime extension with *unknown*
  patterns recovered by inversion (Ishii & Tahara 2013).

## The filter maths

Normalised patterns are the columns of $D$ (rows = micro-time bins, columns =
species); $I(t)$ is the measured total decay; the Poisson weight is
$W=\mathrm{diag}(1/I)$. The filter matrix is the **weighted pseudo-inverse**

$$F = (D^\mathsf{T} W D)^{-1} D^\mathsf{T} W,$$

one row $F_s(t)$ per species. Filters can be negative; they obey the orthogonality
relation $\sum_t F_s(t)\,p_{s'}(t)=\delta_{ss'}$. Per-photon weights $w_s(t)$ feed
a multi-tau correlator to give species auto/cross correlations.

**Afterpulse removal.** Detector afterpulsing / dark counts are uncorrelated with
the pulse → flat micro-time distribution. Adding a uniform pattern
$1/N_\text{bins}$ as an extra "species" yields afterpulse-free fluorescence
filters (Enderlein trick) — reaches sub-µs lag with a single detector.

**Conditioning.** Filter quality is set by the normal matrix $D^\mathsf{T}WD$.
Near-collinear patterns (similar lifetimes) → ill-conditioned inverse → large
alternating-sign, noise-amplifying filters. Mitigate with truncated-SVD
(`rcond`) and/or Tikhonov ridge $(D^\mathsf{T}WD+\lambda I)^{-1}$. The condition
number is a cheap pre-flight diagnostic.

## 2D-FLCS

At each lag $\tau$, measure the 2-D fluorescence-decay correlation matrix
$M(t_1,t_2;\tau)$ = joint distribution of the first and second photon micro-times.
Invert (severely ill-posed) to a lifetime–lifetime map $P(\tau_1,\tau_2)$ via
**MEM** (Skilling–Gull entropy) or **Tikhonov**. Diagonal peaks = static
heterogeneity; off-diagonal peaks growing with $\tau$ = dynamic interconversion.
For a two-state exchange the resolved species auto-CFs decay and the cross-CF is
anti-correlated with rate $k=k_{12}+k_{21}$.

## Code map

Core filter maths — `chisurf/core/fluorescence/fcs/filtered.py`:

- `calc_ffcs_filters(experimental_decay, species_decays, rcond=, tikhonov=)` —
  the $F=(D_\text{norm}^\mathsf{T}WD_\text{norm})^{-1}D_\text{norm}^\mathsf{T}W$
  filter with `W=diag(1/I)`; returns `(filters, reconstruction, weighted_residuals)`.
  `_ffcs_normal_matrix` builds the normalised $D$, weight $W$, `dw = DₙᵀW` and
  `g = DₙᵀWDₙ` pieces.
- `uniform_pattern(n_bins)` — flat pattern for the afterpulse-free "species".
- `filter_condition_number(...)` — `cond(DₙᵀWDₙ)` collinearity diagnostic.
- `photon_filter_weights(filters, micro_times)` — per-photon → per-species weight
  streams (single filter set).
- `species_weight_streams` / `species_filtered_correlation` — channel-aware
  generalisation: 2-D `(n_species,n_bins)`, 3-D `(n_channels,n_species,n_bins)`,
  or `{channel: matrix}` (par/perp / per-detector via `correlate.get_weights`);
  correlates every species auto/cross pair with `tttrlib.Correlator` (uses
  `set_weights`, not native `set_filter`, so the two correlator sides can carry
  *different* species filters).
- `calc_lifetime_filter(...)` — legacy Enderlein/Kapusta filter (kept; zero-bin
  guard added, nonstandard renormalisation removed).

Interactive filter design — `chisurf/plugins/fcs/fcs_filter_calculator/`
(client/backend split; AutoForm `*.view.json` gui_parts; CLI; example notebooks
incl. MFD polarisation-resolved).

2D-FLCS — `chisurf/plugins/fcs/flc_2d/`:

- `core.py` — 2D-FDC (fluorescence-decay-correlation) matrix builder
  ($M(t_1,t_2;\tau)$), numba/log-binned (port of `TK_Create2DFDC_04.m`).
- `fit/ilt.py`, `fit/mem_1d.py`, `fit/mem_2d.py`, `fit/global_mem.py` — MEM /
  inverse-Laplace inversion to $P(\tau_1,\tau_2)$. `mem_2d.solve_mem_2d` uses the
  Skilling–Gull entropy with an analytic-gradient L-BFGS-B (replacing the old
  Nelder-Mead), ramped regulator (port of `TK_FitF_MinimizeQ_09.m`).
- `fit/dynamics.py` — once species are resolved, `species_filters` (thin wrapper
  over `calc_ffcs_filters`) + `filtered_correlation` read out interconversion;
  `fit_relaxation` fits $k=k_{12}+k_{21}$. `fit/kinetics.py`, `fit/gaussian.py`.
- `simulate.py` — validation simulator (static heterogeneity vs exchange).

## Pointers

- User page: `docs/concepts/filtered_fcs.md`; guide `docs/guides/17_filtered_fcs.md`.
- Port status / gaps: [/references/fcs-pam-port.md](/references/fcs-pam-port.md).
- Tests: `test/fitting/test_fcs_filters.py`, `test/fitting/test_flcs_correlation.py`,
  and the `flc_2d/test/` suite (`test_mem`, `test_dynamics`, `test_kinetics`,
  `test_2d_fdc`, `test_lifetime_recovery`).

## Cited

- Böhmer, Wahl, Rahn, Erdmann & Enderlein, *Time-resolved fluorescence correlation
  spectroscopy*, Chem. Phys. Lett. **353**, 439–445 (2002).
- Kapusta, Wahl, Benda, Hof & Enderlein, *Fluorescence Lifetime Correlation
  Spectroscopy*, J. Fluoresc. **17**, 43–48 (2007).
- Felekyan, Kalinin, Sanabria, Valeri & Seidel, *Filtered FCS: species auto- and
  cross-correlation functions highlight binding and dynamics in biomolecules*,
  ChemPhysChem **13**, 1036–1053 (2012).
- Ishii & Tahara, *Two-dimensional fluorescence lifetime correlation spectroscopy*
  (parts 1 & 2), J. Phys. Chem. B **117**, 11414–11422 & 11423–11432 (2013).
- Enderlein & Gregor, *Using fluorescence lifetime for discriminating detector
  afterpulsing in FCS*, Rev. Sci. Instrum. **76**, 033102 (2005).
