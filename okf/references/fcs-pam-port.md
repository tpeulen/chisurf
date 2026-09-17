---
type: Reference
title: "FCS model catalogue & FLCS filters: PAM port status and gaps"
description: PAM parity status — what ChiSurf's FCS fit-model catalogue, FLCS lifetime filters and image correlation (MIA) gained from using PAM as reference (A/B verified), what is deliberately out of scope, and what is still missing.
tags: [reference, fcs, flcs, mia, image-correlation, diffusion, roadmap]
timestamp: '2026-09-17T00:00:00Z'
---

# FCS model catalogue & FLCS filters — PAM port

PAM (Schrimpf et al. 2018) is used as the reference implementation for ChiSurf's
Fluorescence Correlation Spectroscopy (FCS) fit models and its filtered-FCS
(FLCS) lifetime-filter maths. Ports are **A/B-verified**: each PAM model's MATLAB
`fit` lambda (`junk/PAM/Models/fcs/*.m`) is transcribed verbatim as the reference
and asserted equal, over random parameters, to the ChiSurf implementation.

## Where to pick this up

1. **FLCS `empty_bins` default.** Both PAM filter routines are pinned by
   `test/fitting/test_fcs_filters.py` against `test/data/flcs/`. Open: whether the
   default becomes `"exclude"` and whether the Filter Calculator exposes it (see
   "What is missing"). Measure on a PIE-gated real file before deciding; the
   synthetic fixture exaggerates (it zeroes bins by hand).
2. **Order-dependent Filter Calculator widget tests.** `test_widgets.py` passes
   on its own but 9 of its tests fail when any `test/` file runs first in the same
   session (e.g. `pytest test/fitting/test_flcs_correlation.py
   chisurf/plugins/fcs/fcs_filter_calculator/test/test_widgets.py`):
   `detector_selection.get_selected()` comes back empty, so `test/conftest.py`
   evidently changes the detector/settings state the widget reads. Pre-existing
   (same result with the pre-change `filtered.py`); not fixed.

## What is there (implemented / ported)

### FCS fit-model catalogue (`chisurf/core/models/fcs/models.yaml`)
Thirteen physically-parametrised, **absolute-D** models ported from PAM (x in
seconds; D in µm²/s; w_r/w_z/diam in µm; tau in µs; v_flow in µm/s; freq in kHz;
k in 1/s). PAM's inline SI conversions (`4·D·1e-12·x/(w·1e-6)²`) cancel to the
reduced `4·D·x/w²`; the A/B test validates that simplification.

- `3D diffusion (D, triplet)` — PAM `FCS_D`
- `3D diffusion, 2 components (D, triplet)` — `FCS_D_2Component`
- `3D diffusion, 2 triplet (D)` — `FCS_D_2exp`
- `3D diffusion (tauD, triplet)` — `FCS_TauD`
- `3D anomalous diffusion (tauD, triplet)` — `FCS_TauD_anomalous`
- `3D diffusion + flow (D, triplet)` — `FCS_flow`
- `3D diffusion + background (D, triplet)` — `FCS_D_Background` (`(1-BG/Counts)²`)
- `3D diffusion + afterpulsing (D, triplet)` — `FCS_D_afterpulsing` (additive stretched-exp)
- `3D diffusion + bleaching (tauD)` — `FCS_TauD_Bleaching`
- `Two-focus 3D diffusion (D, triplet)` — `FCS_2Focus_D` (Dertinger absolute D; `diam` = known inter-focus distance; `diam=0` → single focus)
- `FRET-FCCS, 2-state (D)` — `FCS_FRETFCCS` (donor-auto / acceptor-auto / cross with shared 2-state exchange)
- `ns-FCS antibunching + bunching + triplet` — `nsFCS_ab_cd_triplet`
- `Scanning FCS (D, triplet)` — `FCS_Scanning` (periodic sin² term)

All carry the γ = 1/√8 prefactor and (where applicable) the triplet term
`1 + Trip/(1-Trip)·exp(-x/tau_T)`. Verified by `test/fitting/test_fcs_pam_ab.py`
(A/B against PAM + a catalogue-wide parse check) and the two-focus physics test
`test/fitting/test_fcs_2ffcs.py`.

Note: the **two-focus** model is the PAM `FCS_2Focus_D` Gaussian form — PAM
itself uses the Gaussian two-focus MDF, not the full non-Gaussian Dertinger MDF
(see gaps).

### FLCS lifetime filters (`chisurf/core/fluorescence/fcs/filtered.py`)
The core weighted-pseudo-inverse filter maths (`calc_ffcs_filters`,
`F = (Dₙᵀ W Dₙ)⁻¹ Dₙᵀ W`, `W = diag(1/I)`) is A/B-verified against **both** of
PAM's filter routines, run in Octave (verdict 2026-09-17, PAM commit `7319d15d`):

| PAM routine | empty total-decay bins | ChiSurf | agreement |
|---|---|---|---|
| `functions/BurstBrowser/Calc_fFCS_Filters.m` l. 30-32, 54-58, 65-67 | `I=0 → 1`, patterns normalised over all bins, par and perp solved separately | `empty_bins="unit_weight"` (default; unchanged) | filters 7e-16, reconstruction 7e-16 relative |
| `PAM.m` `Update_fFCS_GUI` l. 13911-13916 (stack PIE channels, normalise), 13954-13982 (filters) | dropped: `valid = Decay ~= 0`, patterns renormalised over valid bins, filters 0 elsewhere | `empty_bins="exclude"` (added) | filters 5e-16, reconstruction 2e-16 relative |

The two PAM routines agree to machine precision when no bin is empty and differ
by O(1) when a pattern has weight on empty bins (fixture case `two_species_bg`:
unit weight puts filter values up to 58 on the five empty pre-rise bins, and the
occupied-bin filters differ by up to 6.7). The reason: `I=0 → 1` gives an empty
bin the *largest* weight of any bin. PAM's stacked multi-channel layout is
`calc_ffcs_filters` on the concatenated channels (fixture case
`stacked_par_perp`); the Filter Calculator's "Global (stacked)" mode already does
this. Fixture and generator: `test/data/flcs/` (verbatim PAM excerpts in
`pam_ffcs_filters_reference.m`, so it regenerates without a checkout; `--pam
<root>` re-checks the excerpts). Tests: `test/fitting/test_fcs_filters.py`.

Deliberate differences / not taken:
- BurstBrowser's weighted residual uses the substituted `1` as the measured value
  on empty bins; ChiSurf keeps the measured zero (display-only quantity).
- PAM.m's FCS-tab **afterpulsing correction** (l. 6949-6962: `Decay(Decay==0)=1`,
  baseline `min(smooth(Decay, 250 ps))`, species `[Decay−baseline, flat]`, filter
  on the PIE `From:To` window only) is not ported as a one-click mode: ChiSurf's
  equivalent is a measured/fitted pattern plus `uniform_pattern` as a nuisance
  species, and `smooth` is a MATLAB toolbox function with no Octave A/B.
- PAM's automatic scatter / donor-only columns (BurstBrowser l. 19-29) — see
  "What is missing".

Earlier additions, still in place:

- **Conditioning** — `calc_ffcs_filters` now takes `rcond` (truncated-SVD
  pseudo-inverse) and `tikhonov` (ridge `G + λI`) options to tame
  noise-amplifying filters when patterns are near-collinear (similar lifetimes);
  default behaviour is unchanged.
- **Diagnostics** — `filter_condition_number(...)` returns cond(`Dₙᵀ W Dₙ`) so
  collinear patterns can be detected before use.
- **Afterpulsing removal** — `uniform_pattern(n_bins)` provides the flat
  micro-time pattern to add as an extra "species", giving afterpulse/dark-count-
  free filters (the classic Enderlein trick).
- **Per-photon weighting** — `photon_filter_weights(filters, micro_times)` maps
  each photon's micro-time to its per-species filter weight, the input a weighted
  correlator needs (the core step for wiring filters into correlation).
- **Bug fix** — the legacy `calc_lifetime_filter` no longer divides by zero on
  empty total-decay bins, and its nonstandard global filter renormalisation
  (which broke the `Σ_t R_k(t)·p_j(t) = δ_kj` relation) was removed.

Verified by `test/fitting/test_fcs_filters.py` (orthogonality relation,
amplitude recovery, afterpulse removal, conditioning, zero-bin guard).

**Channel-aware filtered correlation (done).** `filtered.py` now has
`species_filtered_correlation` / `species_weight_streams`: per-photon weights
from a 2-D `(n_species,n_bins)` matrix, a 3-D `(n_channels,n_species,n_bins)`
table, or a `{channel: matrix}` map (par/perp / per-detector via
`correlate.get_weights`), correlating every species auto/cross pair with
`tttrlib.Correlator`. `FilterResult.to_channel_filters` /
`FilterResultMFD.to_channel_filters(par,perp)` build the channel table; the
plugin entrypoint `fcs_correlator/core.py::filtered_correlation_datasets`
emits dataset dicts and `CorrelatorSettingsModel.set_lifetime_filters` wires it
into the correlator model. Tests: `test/fitting/test_flcs_correlation.py`,
`chisurf/plugins/fcs/fcs_correlator/test/test_filtered_core.py`.

**Catalogue additions (done).** Six more PAM FCS correlation models
(`FCS_TauD_Background`, three `FCS_SCCF_*_TauD_anomalous`, `fullFCS_sum/product`)
and a new **PCF experiment type** (pair-correlation distribution fits:
`PCF_LogNormal/LogGaussian/Gamma`) — see the PCF catalogue
`chisurf/core/models/pcf/`.

## Image correlation (PAM's MIA module)

MIA's analysis core is covered, and by a different route than PAM takes: rather
than separate RICS / TICS / iMSD analyses, ChiSurf computes **one spatiotemporal
correlation carpet** and reads the named methods off it. See
[image correlation](/references/image-correlation-theory.md) for the unifying
lag-time identity.

| MIA analysis | ChiSurf |
| --- | --- |
| `Do_1D/2D/3D_XCor` | `compute_ics_carpet` — the 3-D case *is* the carpet |
| `Do_RICS`, `Fit_RICS`, `Calc_RICS_Fit`, `RICSMap` | the `Δ = 0` slice + `ImageCorrelationModel` |
| `Do_TICS`, `Fit_TICS`, `Save_TICS` | `tics_curve()`; fitted jointly with the rest of the carpet |
| `Do_iMSD`, `Fit_iMSD` | model width is `w_r² + 4Dτ^α`; release `alpha` |
| `Do_NB`, `NB_2DHist_BG` | `img_pixel_nb` |
| `Do_Coloc` | `img_coloc` (PRD-67) |
| `Do_Gaussian`, `Fit_Gaussian` | `IcsGaussian2DModel`, `psf_determination` |
| `Do_FLIM` and friends | `img_pixel_phasor`, `img_pixel_mle`, `sm_image_mle` |
| `MIA_Drift` | `img_drift` — and photon streams are corrected photon-by-photon |
| freehand / arbitrary-region / Cellpose ROI | `core/roi/` (`arbitrary_region`, `rois_from_cellpose`) |
| `RICSPE` | `core/experiments/ics/precision.py` + the `rics_precision` calculator |
| `rFRAP` | `core/fluorescence/imaging/frap.py` |
| `Do_FRET` (ratiometric) | `core/fluorescence/imaging/ratio_fret.py` |

`Read_CZI` is **deliberately skipped**, and `FRAP_MEM` (the maximum-entropy FRAP
variant) is deferred; `rFRAP`'s closed form covers the ordinary case.

### RICSPE parity — verified to double precision, with one deliberate deviation

The precision predictor was A/B'd against the unmodified reference kernels run
in Octave, with every intermediate frozen into
`test/data/rics/pam_ricspe_reference.npz` (the generating script is archived
beside it, so the fixture can be regenerated against any PAM checkout).

The scalar block — shape factors, volume, the dwell-time brightness correction
with its `sqrt(1-beta)` singularity refactored as `atanh(z)/z`, the mean count
rate — the ideal correlation grid, and **all 256 entries of the estimator
covariance** agree to ~5e-13, i.e. the round trip through text. That covers the
master-grid slicing that replaced the reference's four nested loops, the
closed-form pair counts, the placement of the shot term, and the symmetrisation.

Exactly one kernel deviates on purpose: **`g3.m` carries a unit bug**. It opens
by converting the lag vectors to microns in place (`rho1 = rho1 .* S`) and then
forms the time lag from the *converted* vector, so every `tau` it uses is
multiplied by the pixel size in microns. The reference's own two-point function,
built a few lines away in `res_covariance.m`, forms `tau` from the raw lag — so
within the reference the two disagree about what `tau` means. The consequence
shows up in a limit: shrink the pixel size while holding the line lag fixed and
the reference's three-point correlation tends to 1, i.e. two time points many
diffusion times apart correlate perfectly. ChiSurf forms `tau` from the raw lag
and uses the scaled vector only for the spatial norms.

The practical effect is small — `g3` enters one of three additive terms on the
covariance diagonal, moving the predicted error by well under its own
Monte-Carlo uncertainty and leaving the recommended dwell time unchanged — but
it is the reason a naive diff against PAM shows a ~0.3 % covariance difference.
Both the parity and the deviation are pinned by
`test/experiments/test_ics_precision_vs_pam.py`.

### GS_likelihood parity — exact on a real spectrum, and a second reference bug

The Gopich-Szabo photon-by-photon likelihood
(`chisurf/core/fluorescence/burst/gopich_szabo.py`, surfaced by the `burst_gs`
plugin) was A/B'd the same way: the reference `GP_logL.m` run unmodified under
Octave, with photons, generators and efficiencies frozen into
`test/data/gopich_szabo/pam_gs_reference.npz`.

Three of the four cases — two states, two states with fast exchange, and a
reversible three-state chain — agree to ~1e-13 relative, i.e. the round trip
through text.

The fourth is a **non-reversible three-state cycle**, and there the two differ by
**23.7 log units** — a factor of ~2e10 in likelihood. This is a genuine bug in
the reference, not a convention difference: `GP_logL.m` takes `real()` of the
transformed emission matrices (`Phi_g`, `Phi_r`) while keeping the eigenvalues
complex, which is self-consistent only when the spectrum is real. A pure
circulation has a complex conjugate pair, and an independent propagation with
`scipy.linalg.expm` — sharing no code with either spectral implementation —
lands exactly on ChiSurf's value, not on the reference's. ChiSurf therefore
keeps the arithmetic complex throughout and takes the real part only of the
final scalar.

The affected schemes are precisely the interesting ones (a driven cycle: a
motor, an ATP-consuming machine); every reversible scheme is unaffected. Both
the parity and the disagreement are pinned by
`test/fluorescence/test_gopich_szabo.py`, so a future change that "restores
agreement with PAM" is caught as the regression it would be.

## What is missing (not implemented)

- **Automatic scatter/IRF and donor-only pattern species.** PAM can auto-append a
  measured scatter/IRF column and a donor-only column as filter species. ChiSurf
  has the pieces — `uniform_pattern` for the flat afterpulsing species, and the
  Filter Calculator fits scatter and background as nuisance columns
  (`decay_fit.py`, `include_scatter`/`include_background`) — but nothing wires a
  fitted scatter or donor-only component back in as a filter species; the user
  adds it manually as a generic pattern file.
- **Model-generated patterns.** Related: `synthetic_decay` can build a decay from
  fitted lifetimes reconvolved with the IRF, but the filter species themselves
  are still file-loaded empirical decays.
- **Default `empty_bins` choice (open decision).** The default stays
  `"unit_weight"` (BurstBrowser, and ChiSurf's behaviour before 2026-09-17).
  `"exclude"` is the physically safer choice whenever a total decay has empty
  bins inside a pattern's support (a PIE-gated total against an ungated
  pattern); switching the default changes filter output for every caller
  (Filter Calculator, `flc_2d.species_filters`, `fcs_lfcs_sim`) and was left for
  the owner to decide. Measure first with `calc_ffcs_filters(..., empty_bins=…)`
  on a real PIE-gated `.ptu`; nothing is exposed in the Filter Calculator GUI yet.
- **Dertinger non-Gaussian MDF two-focus model.** The ported two-focus model is
  the Gaussian form (as in PAM). The fully accurate Dertinger model needs a
  numerically-integrated non-Gaussian detection function (`erf`/quadrature) and
  would be a coded FCS model, not a `models.yaml` string.
- **Guided global-fit preset for absolute-D two-focus.** Fitting the two-focus
  auto+cross curves with shared D/w_r/w_z (diam fixed) is possible through the
  existing global-fit machinery but has no dedicated GUI preset.

## Deliberately not ported

Four of PAM's 26 `Models/fcs` entries are **out of scope by decision**, not
backlog: `fullFCS_pulsed_linear` (needs a coded pulse-train model),
`nsFCS_PDA23_Gauss5`, and `FRET_Gauss4` / `FRET_Beta4` — the last two fit
4-component Gaussian/Beta distributions to **E histograms**, so they belong with
the burst tools rather than in the correlation-curve catalogue. The FCS model
catalogue is considered complete at 22 of 26 (19 FCS + 3 PCF).

## Pointers

- Models: `chisurf/core/models/fcs/models.yaml`; parser
  `chisurf/core/models/parse/parse.py` (`ParseModel`).
- Filters: `chisurf/core/fluorescence/fcs/filtered.py`; plugin
  `chisurf/plugins/fcs/fcs_filter_calculator/`; 2D-FLC consumer
  `chisurf/plugins/fcs/flc_2d/fit/dynamics.py`.
- PAM reference (https://gitlab.com/PAM-PIE/PAM at `7319d15d`; the local
  `junk/PAM` checkout is harvested and deleted, `junk/clone.sh` re-clones it):
  `Models/fcs/*.m`, `functions/BurstBrowser/Calc_fFCS_Filters.m`, `PAM.m`
  `Update_fFCS_GUI`. Filter fixture: `test/data/flcs/`.
- Image correlation: `chisurf/core/experiments/ics/`,
  `chisurf/core/models/ics/`; MIA reference `junk/PAM/functions/MIA/`,
  `junk/PAM/Models/miafit/*.miafit`.
- Tests: `test/fitting/test_fcs_pam_ab.py`, `test_fcs_2ffcs.py`,
  `test_fcs_filters.py` (PAM filter A/B); `test/experiments/test_ics_unification.py`,
  `test_ics_vs_pam.py`.
- FCS plugin group overview: [/plugins/fcs.md](/plugins/fcs.md).
