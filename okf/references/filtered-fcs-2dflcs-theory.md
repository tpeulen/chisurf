---
type: Reference
title: "Filtered FCS (fFCS/FLCS) and 2D-FLCS: theory mapped to ChiSurf"
description: The micro-time statistical-filter theory behind fFCS/FLCS and 2D-FLCS, and how each piece maps onto ChiSurf's filtered.py, fcs_filter_calculator, and flc_2d code.
tags: [reference, fcs, flcs, 2d-flcs, lifetime, filters, theory]
timestamp: '2026-09-17T00:00:00Z'
---

# Filtered FCS (fFCS/FLCS) and 2D-FLCS — theory ↔ ChiSurf

## Where to pick this up (2D-FLCS, 2026-09-17)

The original MATLAB (T. Kondo; github.com/PremashisManna/2D-FLC-code @082b59c,
with P. Manna's technical note) is fully accounted for in tttrlib
`okf/prds/PRD-036-2d-flc-photon-kernels.md` (table + "The harvest finished"), and
its checkout is deleted. Open, in priority order:

1. **Nothing of the MATLAB is left unported** (2026-09-17, part 2):
   `TK_CreateExpCurve` -> `fit/exp_curve.py`, `TK_MyMain_Search_RiseIRF_2DMEM` /
   `TK_MyMain_Run_Ave2DMEM` (+ `Fit_2DMEM_04`, `GFit_2DMEM`, `MinimizeQ_09`,
   `GFitF_MinimizeQ_04`, `mi_ModelFunction`) -> `fit/minimize_q.py`,
   `fit/workflow_2d.py`; `TK_DisIntLife2Dmap` SKIPPED (display only: `figure`,
   `image(imgaussfilt(...))`, a colormap file `mycmap.dat` that is not even in the
   repository, output `Out` never assigned; its one other effect, `global g2Dmax`, is
   a colour-axis limit). Open from that port: the **local minimizer** is L-BFGS-B with
   an analytic gradient, not `fminsearch` -- same objective and schedule, but trial
   results differ, so the maps are not A/B-able against Octave (only the deterministic
   pieces are, fixture `matlab_exp_curve.npz`); a real-data comparison against a
   published MATLAB result would be the check. **Reference defect reproduced, not
   fixed:** MATLAB `sum` of a one-row slice sums across lifetimes, which corrupts every
   linear bin at `lint_bin_factor = 1` and the last linear bin at the reference's own
   default gate (0.5-12.2 ns, factor 4); the reference fits log matrices, so it did not
   bite there. The rise scan on a simulated stream puts the chi2 minimum at 294 for an
   IRF simulated at 300 (gate offset of one channel plus IRF sampling); 270/330 are 2x
   and 3x worse.
2. **The bootstrap, reproduction and 2D-MEM drivers are API/CLI only.** No backend RPC or GUI
   panel: bootstrap needs one file per molecule, which the single-stream tool
   does not model. A multi-file "molecule set" input is what blocks both. Any
   panel for them (options, a reproduced-vs-data view, an error map) is a new
   surface, so it is an AutoForm `view.json` rendered by emtk (plots/maps in
   hand-written emtk), hosted in the tool — not Qt widgets.
3. **L-curve corner is fragile on this data.** `lifetime_spectrum(reg=None)`
   resolved 0.76/2.91 ns on the recorded MATLAB stream but merged the peaks on
   simulated streams whose histograms agree with it to 1-2% (corner 5e-4 vs
   2e-2). `test_lifetime_spectrum_reference` now fixes `reg=1e-3`. Not fixed.
4. **Library semantics at windows that start at the reference photon.**
   `fdc_scan_*` counts self-pairs and earlier same-tick photons at
   `dT <= ddT/2` / zero lag; chisurf corrects (`core.earlier_same_time_pairs`).
   Moving that into tttrlib needs a C++ build (skipped: disk). Measured +1459
   pairs at `dT = ddT/2` on a stream with 427 repeated ticks.

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
  ($M(t_1,t_2;\tau)$), delegating the photon pass to tttrlib `fdc_scan_*` (port
  of `TK_Create2DFDC_04.m`). The linear matrix is `[1:lint_imax]` of the
  library's (index 0 is always empty; sliced one bin off until 2026-09-17).
- `bootstrap.py` — port of `TK_MyMain_Create2DFDC_cor_SeparateData_BootStrap_v02`:
  per-molecule lag / background / short-lag / 1D matrices, `cor` = lag −
  longest lag, symmetrized, summed; `bootstrap_order` is the MATLAB draw
  (`randperm(N·g)` mod N until `photon_factor` × photons), `bootstrap_2d_fdc` the
  replicate loop with per-element mean/std (the MATLAB leaves repetition to the
  user). Octave A/B bit-identical.
- `fit/reproduct.py` — port of the four `Reproduct` functions: forward models
  `decay_model`/`fdc_model` (shared with the fits), MATLAB chi2/entropy/Q,
  estimates-vector unpacking with fix flags. Octave A/B 2e-16.
- `fit/exp_curve.py` — `TK_ExpMultiDeco_For2DFLC` + `TK_CreateExpCurve`: IRF placed by
  rise points, basis summed over linear/log bins (Octave A/B <= 4e-14, four gates).
  `api.two_d_spectrum`/`fit_mem_2d`/`global_lifetime_mem` refuse a non-uniform axis
  unless given `basis=` + `tau_grid`.
- `fit/minimize_q.py` — `TK_FitF_MinimizeQ_09`/`TK_GFitF_MinimizeQ_04` schedule,
  `TK_mi_ModelFunction` (A/B 5e-16), start distribution and scaling (A/B 3e-14).
- `fit/workflow_2d.py` — `fit_2d_mem_workflow`, `search_irf_rise_2d`,
  `average_2d_mem` (rise-point sequences A/B exact); CLI `rise-search-2d`, `average-2d`.
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
  `test_2d_fdc`, `test_lifetime_recovery`, `test_reproduct`, `test_bootstrap`).
  The data-driven tests simulate the MATLAB reference data set in `conftest.py`
  (was: read the 69 MB `simulated_data.mat`, silently skipped when absent);
  fixtures `test/data/flc_2d/{reference_irf,matlab_reproduct,matlab_bootstrap}.npz`.

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
- Kondo, Gordon, Pinnola, Dall'Osto, Bassi & Schlau-Cohen, PNAS **116**,
  11247–11252 (2019), doi:10.1073/pnas.1821207116 — the application the MATLAB
  was written for.
- P. Manna, *2D-Fluorescence Lifetime Correlation Code: Mathematical Basis,
  Tutorial and Technical Notes* (2020, PDF in github.com/PremashisManna/2D-FLC-code).
  Workflow it prescribes: 1D search (1D-MEM over IRF shifts, average the 4–5 lowest
  χ²) → 2D search (one ΔT, regulator trials ~100, IRF shifts) → average 2D (5 best
  IRF positions, global MEM over all ΔT, ~300 regulator trials; 300→400 changed
  nothing and cost 7000→12000 s) → rate-matrix fit of the species correlations
  (`TK_MyMain_Analyze_03_NotRatio`, fix flags 0/1/2 and n>2 = linked). Notes:
  flat prior on a log-τ grid; peak widths track photon number, not heterogeneity;
  the long lifetime broadens from truncation at the 12.5 ns window. Its
  `DivideNum` parameter is not in the v02 driver.
- Enderlein & Gregor, *Using fluorescence lifetime for discriminating detector
  afterpulsing in FCS*, Rev. Sci. Instrum. **76**, 033102 (2005).
