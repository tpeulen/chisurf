---
type: Subsystem
title: Fluorescence Domain
description: Shared fluorescence algorithms used by fitting models, plugins, readers, and imaging tools.
resource: chisurf/core/fluorescence/
tags: [core, fluorescence, tcspc, fcs, fret, imaging]
timestamp: '2026-07-05T00:00:00Z'
---

# Scope

`chisurf/core/fluorescence/` is the Qt-free scientific kernel for fluorescence
calculations. It sits below the [models](/subsystems/models.md), plugin GUIs,
and [data IO](/subsystems/data-io.md): plugins collect inputs and render
results, while this package implements the numerical operations.

| Subpackage | Role |
| --- | --- |
| `tcspc/` | Decay convolution, pile-up/background/correction helpers, IRF estimation, and phasor calculations. |
| `fcs/` | Correlation, channel setup handling, fFCS filters, normalization, and curve merging. |
| `fret/` | Forster/FRET utilities and FRET-line generation for lifetime/E overlays. |
| `burst/` | Burst statistics, BVA, background, count-rate and change-point helpers, and non-burst IRF/background extraction (`irf_bg.extract_irf_background`). |
| `anisotropy/` | Anisotropy decays/integrals and orientation-factor calculations. |
| `imaging/` | Shared pixel-map helpers for intensity, Number & Brightness, micro-time histograms, and phasor maps. |
| `curation/` | Fluorescence curation helpers, including AI-assisted triage. |
| `dyes.py` | The one seam through which tools read reference-dye properties (diffusion coefficient `D(25 °C, water)`) from [MMFDB](/architecture/mmfdb.md); cached, alias-tolerant, with the shipped MMFDB table as fallback. No dye data is duplicated in ChiSurf. |

# Reuse pattern

The preferred boundary is: keep numerical code here or in a small plugin
`core/`/`api/` package; keep Qt widgets in plugin `gui/`; expose server-friendly
operations through manifest `services` when long-running or scriptable. This is
the same split used by the [TTTR plugins](/plugins/tttr.md), [imaging plugins](/plugins/imaging.md),
[calculator plugins](/plugins/calculator.md), and [FCS plugins](/plugins/fcs.md).

# Design objective: one intensity/decay computation path

ChiSurf should converge on one central, Qt-free intensity/decay infrastructure
inside `chisurf/core/fluorescence/`. It owns the forward computation from a
fluorescence model and detector/light-path definition to detector-resolved
intensities, TCSPC decays, and reusable species patterns. Instrument response,
polarization, pile-up, background/scatter, detector efficiencies, spectral
crosstalk, and excitation/emission mixing belong in that path.

Finite-photon observation belongs at the boundary of this path, after the
expected detector decay is computed. `sample_decay_shot_noise` provides the
shared Poisson sampler: it accepts expected counts directly or normalizes an
ideal decay to an explicit photon budget, and supports deterministic seeds for
tests and persisted synthetic projects. This keeps the forward-model pattern
separable from measurement noise while allowing noisy reference patterns when
that is the intended experiment.

Nuisance decay shapes are also shared infrastructure rather than GUI-local
approximations. `afterpulse_decay_pattern` defines the normalized constant
microtime basis used for afterpulsing/dark counts, while
`scattered_light_decay_pattern` validates, windows, and normalizes an IRF as a
scattered-light basis. Forward models, unmixing, and FLCS filter construction
should consume these definitions consistently.

`optimize_synthetic_scatter_pattern` supplies the no-measured-IRF path. It
reuses `tcspc.irf.synthetic_irf`, searches a bounded prompt/width grid against
one detector decay, and non-negatively refits the molecular, constant, and IRF
bases for every candidate. This is intentionally detector-local: a shared IRF
must not silently replace distinct detector or polarization responses.

Fitting models, simulators, FLCS/FCS filter tools, correlation tools, imaging
plugins, and exporters must consume this shared computation rather than carry
private approximations. Existing fits are first-class pattern sources: a tool
may read a fit's lifetime/rate/distance spectrum, but detector-resolved patterns
must be recomputed by the central model path (or loaded as a snapshot produced
by it). New decay mathematics should be added centrally and exposed through a
serializable service/API contract before a GUI or plugin depends on it.

This is a target architecture. Today, decay generation is split between TCSPC
models, simulator widgets, and plugin-local helpers; migrations should reduce
that duplication incrementally without bypassing the established model
correction stack.

# Examples

- `fret.fret_line.FRETLineGenerator` sweeps TCSPC FRET model parameters and
  produces FRET-efficiency/lifetime lines reused by the FRET-line plugin.
- `tcspc.phasor` implements phasor coordinates used by calculators and
  per-pixel FLIM tools.
- `imaging.pixel_maps` caches expensive TTTR/CLSM loads and writes standard
  imaging HDF5 tables consumable by downstream analysis.

See also [fitting](/subsystems/fitting.md), [data model](/subsystems/data-model.md),
and [plugin system](/architecture/plugin-system.md).
