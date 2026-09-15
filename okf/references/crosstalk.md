---
type: Reference
title: "Spectral crosstalk / linear-mixing core"
description: The shared Qt-free crosstalk-matrix utility behind the light-path calculator, ratiometric/sensitized-emission FRET, phasor unmixing and DDEM.
tags: [reference, fret, crosstalk, imaging, roadmap]
timestamp: '2026-07-15T00:00:00Z'
---

# Spectral crosstalk / linear mixing

Spectral crosstalk — donor bleed-through into the acceptor channel, direct
acceptor excitation, detector mixing — is a single linear-algebra problem that
recurs across ChiSurf. Rather than a per-consumer reimplementation, it is
centralised in a Qt-free core, `chisurf/core/fluorescence/crosstalk.py`.

> **Placement, 2026-09-04.** The *definition and the algebra* moved to bff —
> owner: "excitation and emission crosstalk matrix definition must be in bff
> not in chisurf" (the compute/display line applied to calibration). They are
> `IMP.bff.CrosstalkMatrix` and the `crosstalk_apply/invert/shuffle` kernels
> (`imp.bff` `include/CrosstalkMatrix.h`; log entry 2026-09-04 (28) there,
> including the ported Lawson–Hanson NNLS). The **scalar three-cube** is
> tttrlib's (`SpectralCrosstalk`, its registered and A/B-validated owner):
> `correct_three_cube` forwards to it — same-day check against tttrlib found
> the numpy twin, parity was exact, the twin is gone (duplication register,
> PRD-105 phase 4). tttrlib's `invert_mixing_ridge` is the superseded twin of
> bff's ridge path, not the owner. `chisurf/core/fluorescence/crosstalk.py`
> is the Qt-free numpy **adapter**: payload → labelled matrix → ndarray,
> reshape, cast. The backend pin
> `test/architecture/test_bff_is_the_backend.py::
> test_the_crosstalk_matrix_definition_is_bffs` holds the line.

Convention: a mixing matrix `M` has shape `(n_sources, n_detectors)` with
`M[i, j]` = contribution of source `i` to detector `j`; the forward model is
`measured = Mᵀ @ sources` and the inverse recovers the sources. Rows and
columns are labelled; labels are how a payload built against one instrument
description is ordered for another consumer, and a requested label the matrix
does not carry contributes zeros — a missing element of a light path is a
dark element, not a broken one.

## What is there (implemented)

- `matrix_from_payload(payload, rows, columns)` — build an ordered NumPy matrix
  from a light-path-calculator crosstalk payload (`{rows, columns, values}` as
  returned by `lightpath_simulator…get_crosstalk_matrices()`), with optional
  label subsetting/reordering.
- `apply_mixing(M, sources)` / `invert_mixing(M, measured, nonneg=, ridge=)` —
  forward mixing and the (least-squares or NNLS) inverse correction, both
  broadcasting over trailing pixel/burst axes (the solves are bff's).
- `correct_three_cube(IDD, IDA, IAA, donor_leak, direct_excitation, gamma)` —
  forwards to `tttrlib.correct_three_cube_batch` (Gordon/Nagy three-cube
  **ratiometric FRET** correction, `Fc = IDA − d·IDD − a·IAA`), broadcasting
  over pixel/burst arrays like the rest; the engine's denominator guard is
  adopted (efficiency 0 where `Fc + γ·IDD ≤ 0`). `three_cube_fret_efficiency`
  stays the local elementwise helper (its `denom != 0` contract is its own).
- Bug fix: `chisurf/core/fluorescence/intensity.py::nusiance` used the Python-2
  `func_globals` attribute, so the whole scalar FRET-correction API
  (`fret/__init__.py`: `fret_efficiency`, `fg_fr`, …) raised `AttributeError` at
  call time. Now `__globals__`; the corrections (background, `crosstalk`
  leakage, `gamma`) work again.
- Tests: `test/fitting/test_crosstalk.py` (mixing round-trip, image-stack
  broadcasting, NNLS, three-cube `E` recovery, decorator fix).

## The consumers (why it is general)

- **Light-path calculator** already *builds* the forward matrix
  (`get_crosstalk_matrices()` → excitation / emission / detected). This core is
  the inverse/apply side of that same matrix.
- **Ratiometric FRET (rFRET)** — `correct_three_cube` supplies the missing
  three-cube (IDD/IDA/IAA) correction with direct-excitation (`a`) and
  donor-leak (`d`) terms that the scalar `fret/__init__.py` model lacked.
- **Sensitized-emission / DDEM** — the corrected `Fc` is the sensitized-emission
  signal; energy-migration (DDEM/PDDEM, `chisurf/core/models/tcspc/pddem.py`)
  is the same donor↔acceptor coupling problem and can reuse `apply/invert`.
- **Phasor-FLIM spectral unmixing** — `img_pixel_phasor.analysis.phasor_unmix`
  solves the same constrained linear inverse; `invert_mixing(nonneg=True)`
  mirrors its NNLS.

## What is missing (not implemented)

- **NOT a standalone `img_pixel_rfret` plugin — that is redundant with ndxplorer.**
  ChiSurf already exports all three PIE channels per pixel (IDD/IDA/IAA as
  `S prompt green/red (kHz)` + `S delayed yellow (kHz)`, `pixel_maps.py:443` →
  `img_pixel_intensity`), and ndx's derived-column engine
  (`modules/ndxplorer/.../data_source.py::compute_values`, `mfd.equations.yaml`)
  already computes corrected `FRET efficiency(PIE)`, `R_FRET`, stoichiometry and
  their pixel maps with editable background/`alpha`(leakage)/`gamma`/`beta`
  (direct-excitation) constants. Per-pixel derived quantities are ndx's job by
  design. So the non-redundant ChiSurf-side deliverable is small: a helper that
  turns the **light-path crosstalk matrix** (`get_crosstalk_matrices()` →
  `matrix_from_payload`/`invert_mixing`) into the `alpha`/`d`/`gamma` factors (the
  one thing ndx cannot originate — it only takes hand-typed constants), and
  optionally writes a pre-corrected `Fc`/`E` column into the existing imaging
  export (`pixel_maps.py`) that ndx then visualises.
- Refactor `img_pixel_phasor.phasor_unmix` to delegate to `invert_mixing` so the
  intensity-FRET and phasor paths share one inverse-mixing helper.
- Wire DDEM/PDDEM sensitized-emission through the crosstalk core.
- Add `alpha`/`beta` (direct-excitation / excitation-crosstalk) and a saturation
  term to the scalar `fret/__init__.py` functions as thin wrappers over
  `correct_three_cube` (the core already supersedes the scalar model).
- Focus/factor calibration: derive `d`, `a`, `gamma` from donor-only /
  acceptor-only reference samples rather than entering them by hand.

## Pointers

- Core: `chisurf/core/fluorescence/crosstalk.py`; decorator
  `chisurf/core/fluorescence/intensity.py`; scalar model
  `chisurf/core/fluorescence/fret/__init__.py`.
- Forward matrix: `chisurf/plugins/core/lightpath_simulator/backend/simulator.py`.
- Phasor unmix: `chisurf/plugins/microscopy/img_pixel_phasor/analysis.py`.
- Tests: `test/fitting/test_crosstalk.py`.
