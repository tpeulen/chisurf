---
type: PRD
prd: "51"
title: "PRD-51: Imaging Correlation — N&B, STICS/TICS, iMSD, Spectral RICS"
description: Extend the landed RICS/STICS correlation carpet with the model-free STICS velocity workflow (immobile filter, per-lag peak tracking, flow vector maps), Number & Brightness, TICS decay fits, and crosstalk-free spectral RICS.
status: in-progress
phase: "unassigned"
resource: chisurf/core/experiments/ics/
tags: [prd, imaging, fcs, ics, stics, tics, imsd]
timestamp: '2026-07-29T00:00:00Z'
---

# Summary

The image-correlation cluster is the largest single group of methods absent versus
the incumbent suite's image-correlation module. **One shared substrate has landed**:
`chisurf/core/experiments/ics/` computes the spatiotemporal correlation array
`G(xi, psi, Delta)`, and `chisurf/core/models/ics/` fits it with a Gaussian
transport model carrying blinking, immobile and flow terms.

That substrate is *not* the methods. **RICS, STICS, TICS and iMSD are different
methods** — different acquisition requirements, different definitions of the lag
time, different estimators, and different observables (see below). Sharing a
correlation routine is a computational convenience, not a methodological identity,
and today's single `IcsModel` conflates them. What remains is to implement each
method as itself: the model-free STICS velocity workflow (immobile Fourier filter
→ per-lag peak *tracking* → flow vector field), iMSD as a peak-*width* readout,
TICS as standalone decay models, plus N&B and crosstalk-free spectral RICS.

Acceptance stays headless and per method: N&B recovers a known brightness, RICS a
known `D`, STICS a known flow **vector field**, iMSD a known MSD curve including a
confined case that a free-diffusion fit cannot represent.

# These are four methods, not four views of one

| | RICS | STICS | TICS | iMSD |
| --- | --- | --- | --- | --- |
| **Input** | raster scan **only** — needs pixel dwell + line time | frame series (scanned *or* camera) | frame series | frame series |
| **Region of `G` used** | `Delta = 0`, intra-frame `xi, psi` | `Delta > 0`, full `xi, psi` map | `xi = psi = 0` | `xi, psi` across all `Delta` |
| **Where the time comes from** | the **scan clock**, `xi*t_pixel + psi*t_line` | the **frame clock**, `Delta*t_frame` | the frame clock | the frame clock |
| **Estimator** | fit the whole map with a scan-convolved model | track the peak **position** vs `Delta` | fit the amplitude **decay** | track the peak **width** `sigma^2(tau)` |
| **Observable** | `D`, `N`, brightness | **velocity vector field** | `tau_D`, flow, blinking/`k_off` | **MSD curve** → free / confined / anomalous |
| **Needs the scan/PSF convolution term `S(xi, psi)`** | **yes** | no | no | no |
| **Assumes a transport model** | yes | no | yes | **no** |

Consequences that the current code gets wrong, and that this PRD exists to fix:

* **STICS is not "RICS with `v_x`/`v_y` released."** STICS estimates velocity by
  following where the correlation peak *moves* between frame lags — model-free, and
  resolved **per sub-region** into a field. Fitting a single global velocity
  parameter to a whole-field correlation is a different (and weaker) measurement:
  it presumes one uniform flow and a transport model, and it cannot produce a map.
* **iMSD is not "RICS with `alpha` released."** iMSD reads the *width* of each
  spatial correlation against lag time and yields an MSD curve whose **shape** is
  the result — a plateau means confinement, curvature means anomalous transport.
  An anomalous-exponent fit presumes the power law that iMSD is supposed to test.
* **RICS's lag times do not transfer.** `tau = xi*t_pixel + psi*t_line` is a
  property of *sequential raster scanning within one frame*. A camera stack has no
  such clock, and the scan-convolution term `S(xi, psi)` does not apply to it —
  so a camera-acquired stack supports STICS/TICS/iMSD but **not** RICS.
* Each method therefore needs its own selectable model and its own view spec, not
  one model with terms switched on and off.

# Status

In progress. Landed: the shared correlation array and one Gaussian transport model.
Not started: STICS as a distinct method (velocity workflow + vector field), iMSD as
a width readout, TICS decay models, N&B, spectral RICS, and the separation of the
four into distinct selectable models.

Parent: [PRD-49](prd-49.md) (Phase 2). Related: PRD-38, PRD-40, PRD-52, PRD-53.

# Motivation

These methods extract oligomerization state, transport maps, and mobility from
image stacks — core quantitative-imaging measurements. ChiSurf can currently
*fit* a flow velocity as a global model parameter, but it cannot produce the
headline STICS deliverable: a spatially resolved flow **vector field** overlaid
on the image, obtained without assuming a transport model.

# Port target — the reference Matlab ICS package

A reference Matlab implementation of the whole ICS/STICS/TICS family is vendored
in-tree at `junk/Image-Correlation-Spectroscopy/` (Wiseman group, ICS Analysis
v1.0, 2006; released open source with the authors' permission — see its
`README.txt`). It is the concrete specification for this port. Its
`tutorial/ICSTutorial.html` is a worked end-to-end example usable as a
regression fixture.

## What the reference has vs. what ChiSurf has

| Reference file | Does | ChiSurf today |
| --- | --- | --- |
| `STICS/stics.m` | the shared `G(xi, psi, Delta)` via per-frame-pair FFT | ✅ `ics_core.compute_ics_carpet` — the *substrate*, not the method |
| `TICS/tics.m` | zero-spatial-lag decay `G(0,0,Delta)` | ✅ `IcsCarpet.tics_curve` |
| `ICS/corrfunc.m`, `gauss2d.m` | 2D correlation + Gaussian form | ✅ `IcsModel` / `IcsGaussian2D` |
| `STICS/immfilter.m` | **immobile-population Fourier filter** (zero the DC temporal frequency) | ❌ only an immobile *fit term* (`N_imm`), which is not the same operation |
| `ICS/gaussfit.m` (`'time'` mode) | fit **each** lag's map, track peak `(x0(tau), y0(tau))` | ❌ no per-lag peak-tracking path |
| `STICS/velocity.m` | regress the peak track over the linear region → `v_x`, `v_y` | ❌ velocity only as a global fit parameter |
| *(spatially resolved STICS)* | sliding sub-region × time-window grid → **flow vector field** | ❌ absent — no sub-region tiling at all |
| `TICS/difffit.m`, `diffusion3d.m`, `diffflowfit.m`, `flowfit.m` | standalone TICS decay models (diffusion, 3D diffusion, diffusion+flow, pure flow) | ❌ the carpet exposes the decay, but there are no selectable TICS decay models |
| `imageManipulation/wnCorr.m` | white-noise/background correction from a user-picked background box | 🚧 background handling exists in `IcsSettings`; not the ROI-picked variant |
| `ICS/autocrop.m`, `imageManipulation/serimcrop.m` | crop / ROI | ✅ `chisurf/core/roi` + `IcsSettings.roi` |
| `simul8tr/` | synthetic stacks (diffusion, flow, blinking, PSF, counting/background noise) | → [PRD-53](prd-53.md) |
| `imageManipulation/rd_img16.m`, `rd_imgser.m` | vendor-specific TIFF/RAW readers | ✅ superseded by the shared image-source seam ([PRD-67](prd-67.md)) |

**Do not port the Matlab structure.** It is one script per method with GUI
handles (`gcbf`, `waitbar`, `ginput`) wired into the numerics — the "select the
end of the linear region by clicking" step in `velocity.m` is interactive by
construction. The port keeps the *physics and the estimators*, and re-expresses
them against the existing carpet: headless functions in
`chisurf/core/experiments/ics/`, fit models in `chisurf/core/models/ics/`, and
AutoForm `view.json` for every UI.

# Open question — does the kernel belong in tttrlib?

The carpet is currently pure NumPy: `n_lags × (n_frames − Delta)` 2D FFTs.
A spatially resolved STICS vector map multiplies that by the number of
sub-regions × time windows, which is where it stops being free. Two candidates:

* **Keep it in ChiSurf (NumPy/FFT).** No new C++ surface; the sub-region loop
  parallelises trivially; FFT plans dominate and NumPy already delegates them.
* **Push the kernel into the companion photon library.** It already owns the
  image-from-stream (CLSM) path that produces these stacks, so a C++ kernel
  would correlate without ever materialising the stack in Python, and would be
  reusable outside ChiSurf.

**Decide by measurement, not by preference** — benchmark a realistic vector-map
job (e.g. 256×256 × 200 frames, 16×16 sub-regions, 20 lags) before writing any
C++. Record the numbers in [benchmarks](/references/benchmarks.md). The prior is
that this is FFT-bound and therefore *not* a language problem — the same
conclusion the decay-fit FFT work reached.

# Scope

- **STICS velocity workflow** (the port above) — immobile filter, per-lag peak
  tracking, linear-region regression, spatially resolved flow vector maps.
- **N&B** — apparent/true brightness & number from pixel intensity mean/variance;
  aggregation-state maps.
- **TICS decay models** — diffusion, 3D diffusion, diffusion+flow, pure flow, as
  selectable fit models over `IcsCarpet.tics_curve`.
- **iMSD** — peak **width** `sigma^2(tau)` vs lag as its own estimator, reported as
  an MSD curve; free / confined / anomalous read from its *shape*, with the
  transport fit optional and downstream of it.
- **Method separation** — split the single `IcsModel` into distinct selectable
  models (RICS / STICS / TICS / iMSD), each with its own view spec, its own lag-time
  definition, and RICS alone carrying the scan-convolution term. A camera-acquired
  stack must not offer RICS.
- **Spectral RICS** — spectral weighting for crosstalk-free multi-colour RICS.

# Reuse

- `chisurf/core/experiments/ics/` (`ics_core.py`, `data.py`, `precision.py`,
  `calibration.py`, `tttr_loader.py`) — the correlation carpet and its timing model.
- `chisurf/core/models/ics/` — the unified fit model and its `view.json`.
- `chisurf/core/roi` — sub-region tiling for the vector map ([shared ROI](/subsystems/gui-autoform.md)).
- The companion photon library's CLSM image-from-stream + mask handling.
- AutoForm + `view.json` for all UIs (PRD-49 AutoForm mandate); reuse
  `image` / `waterfall` / `region_list` sections.
- Vector-field overlay must go through [chiplot](/prds/prd-64.md), not pyqtgraph.

# Definition of Done

- [ ] Immobile Fourier filter as a headless function on the stack, with a test that
      a synthetic static+mobile stack loses its static component.
- [ ] Per-lag Gaussian peak tracking returning `(x0, y0, w, amplitude)` per frame lag.
- [ ] Linear-region regression → `(v_x, v_y)`, with the region chosen by a headless
      criterion (not by clicking), and the interactive picker only as an override.
- [ ] Spatially resolved STICS: sub-region × time-window tiling → flow vector field,
      rendered as a chiplot overlay on the image.
- [ ] N&B: apparent/true `N` and `epsilon` maps; recovers a known brightness on a
      simulated stack.
- [ ] TICS decay models (diffusion / 3D diffusion / diffusion+flow / flow) selectable
      in add-fit and rendered from `view.json`.
- [ ] iMSD implemented as a peak-**width** readout returning `sigma^2(tau)`, with a
      confined-diffusion fixture whose plateau a free-diffusion fit cannot reproduce
      — i.e. the test would fail if iMSD were faked by releasing `alpha`.
- [ ] RICS, STICS, TICS and iMSD are **separate** selectable models, each with its own
      view spec and lag-time definition; the scan-convolution term appears in RICS only.
- [ ] A camera-acquired stack (no pixel/line clock) offers STICS/TICS/iMSD and
      **refuses** RICS, with a test pinning the refusal.
- [ ] STICS recovers a known flow **vector field** (not just a scalar velocity) and
      RICS a known `D`; stacks from [PRD-53](prd-53.md).
- [ ] Spectral RICS weighting removes a known crosstalk on a simulated two-colour stack.
- [ ] Kernel-placement question decided by a recorded benchmark, not by assertion.
- [ ] Docs: the [image-correlation theory](/references/image-correlation-theory.md)
      concept corrected — it currently asserts the four "are not four techniques",
      which overstates a shared correlation routine into a methodological identity
      **and** a numbered `docs/guides/` workflow per method, with a real screenshot.
- [ ] Every control carries a `description`; long help behind a `?` section.
- [ ] `test/experiments/test_ics_unification.py::test_model_slice_width_is_the_imsd`
      renamed — it pins that the *model's* Gaussian width is `w_r^2 + MSD(tau)`, which
      is a property of the model, not the iMSD method. The name is the conflation in
      test form.
- [ ] Model-editor headless checks pass (`/test-model-editor`).

# Non-goals

Phasor imaging ([PRD-52](prd-52.md)); spectral unmixing beyond RICS weighting
([PRD-54](prd-54.md)); particle tracking ([PRD-52](prd-52.md)); simulation itself
([PRD-53](prd-53.md)).

# Relationships

- Child of [PRD-49](prd-49.md) (Phase 2).
- Builds on the landed ICS carpet + model; synthetic validation stacks from [PRD-53](prd-53.md).
- Shares the image-source seam with [PRD-67](prd-67.md) (colocalization).
- All UIs via [GUI & AutoForm](/subsystems/gui-autoform.md); all plotting via [PRD-64](prd-64.md) (chiplot).
- Phasor imaging is [PRD-52](prd-52.md); spectral unmixing beyond RICS weighting is [PRD-54](prd-54.md).
- Theory: [image correlation — RICS, STICS, TICS and iMSD are one method](/references/image-correlation-theory.md).
