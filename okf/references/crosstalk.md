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

Convention: a mixing matrix `M` has shape `(n_sources, n_detectors)` with
`M[i, j]` = contribution of source `i` to detector `j`; the forward model is
`measured = Mᵀ @ sources` and the inverse recovers the sources.

## What is there (implemented)

- `matrix_from_payload(payload, rows, columns)` — build an ordered NumPy matrix
  from a light-path-calculator crosstalk payload (`{rows, columns, values}` as
  returned by `lightpath_simulator…get_crosstalk_matrices()`), with optional
  label subsetting/reordering.
- `apply_mixing(M, sources)` / `invert_mixing(M, measured, nonneg=, rcond=)` —
  forward mixing and the (pseudo-inverse or NNLS) inverse correction, both
  broadcasting over trailing pixel/burst axes.
- `correct_three_cube(IDD, IDA, IAA, donor_leak, direct_excitation, gamma)` —
  Gordon/Nagy three-cube **ratiometric FRET** correction
  (`Fc = IDA − d·IDD − a·IAA`) with `three_cube_fret_efficiency`
  (`Fc/(Fc+γ·IDD)`); recovers a known `E` from synthesized channels.
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
