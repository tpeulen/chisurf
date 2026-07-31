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

In progress. Landed: the shared correlation array, one Gaussian transport model, and
— since 2026-07-31 — the **model-free STICS spine**: per-lag sub-pixel peak tracking
(`IcsCarpet.peak_shift`), the regression that turns a peak track into a velocity
(`IcsCarpet.velocity` → `FlowVector`), and spatial tiling into a vector field
(`flow_map.stics_flow_map` → `FlowMap.quiver`), with a second, independent route to
the same arrows from pair-correlation transit times (`flow_map.pcf_flow_map`).
Two conventions are now pinned by test rather than by comment: the peak moves
*against* the flow, and a peak driven past the tile edge **wraps** — which fits a
clean straight line through a sign-flipped displacement, so such a tile is refused
and counted rather than reported.

Still open on the STICS side: the four immobile filters (only DC removal exists),
the `omegaThreshold` linear-region cutoff, the Ji & Danuser peak-significance gate,
three-stage vector rejection, TOI tiling into a *time series* of maps, the polygon
mask, and STICCS. Not started at all: iMSD as a width readout, TICS decay models,
N&B, spectral RICS, and the separation of the methods into distinct selectable
models.

A measured caveat worth carrying into the port: on a cellular flow that shears
within a tile, the recovered direction is right to ±3° (r = 0.996) while the
**magnitude reads ~20 % low**, and shrinking the tile does not fix it. The same
estimator on a uniform flow is accurate to a few percent. A flow map is therefore a
reliable picture of where the sample is going and a conservative estimate of how
fast — which is exactly what the vector-rejection and significance machinery above
is for.

The reference implementation to port has been surveyed in full (see below): the
estimators, the quality gates and the rejection criteria are all already specified
and published, so this is a port, not a design exercise.

Parent: [PRD-49](prd-49.md) (Phase 2). Related: PRD-38, PRD-40, PRD-52, PRD-53.

# Motivation

These methods extract oligomerization state, transport maps, and mobility from
image stacks — core quantitative-imaging measurements. ChiSurf can currently
*fit* a flow velocity as a global model parameter, but it cannot produce the
headline STICS deliverable: a spatially resolved flow **vector field** overlaid
on the image, obtained without assuming a transport model.

# Port target — the reference Matlab ICS packages

Two vendored copies exist, and **the one to port from is not the obvious one**:

* `junk/Image-Correlation-Spectroscopy/` — the 2006 ICS Analysis v1.0 package.
  Complete and pedagogical (its `tutorial/ICSTutorial.html` is a worked
  end-to-end example, usable as a regression fixture), but it is the *teaching*
  version: one script per method, whole-field, no vector maps.
* **`junk/ICS-Tools/` — the canonical lab repository, and the real target.** It
  contains the 2006 package as one branch **plus `2015-Elvis_Pandzic/STICCSpackage-JoVE/`**,
  which is STICS as actually practiced: ROI×TOI vector mapping, four immobile-filter
  choices, bounded peak fitting, an automated linear-region cutoff, three stages of
  vector rejection, a peak-significance gate, polygon cell masking, batch processing
  — and **STICCS**, the two-channel cross-correlation extension. References: Hebert,
  Costantino & Wiseman, *Biophys. J.* **88**, 3601 (2005); Ashdown *et al.*,
  *J. Vis. Exp.* (2015); Kolin, Costantino & Wiseman, *Biophys. J.* **90**, 628 (2006).

Port from the 2015 package; keep the 2006 tutorial as the fixture.

## What the 2006 reference has vs. what ChiSurf has

| Reference file | Does | ChiSurf today |
| --- | --- | --- |
| `STICS/stics.m` | the shared `G(xi, psi, Delta)` via per-frame-pair FFT | ✅ `ics_core.compute_ics_carpet` — the *substrate*, not the method |
| `TICS/tics.m` | zero-spatial-lag decay `G(0,0,Delta)` | ✅ `IcsCarpet.tics_curve` |
| `ICS/corrfunc.m`, `gauss2d.m` | 2D correlation + Gaussian form | ✅ `IcsModel` / `IcsGaussian2D` |
| `STICS/immfilter.m` | **immobile-population Fourier filter** (zero the DC temporal frequency) | 🚧 `IcsSettings.subtract_average='stack'` removes the time-averaged image, which is the degenerate DC case; the moving-average and Butterworth variants, and the immobile *fit term* (`N_imm`), remain distinct operations |
| `ICS/gaussfit.m` (`'time'` mode) | fit **each** lag's map, track peak `(x0(tau), y0(tau))` | 🚧 `IcsCarpet.peak_shift` fits the peak of each lag's map in closed form (least squares on the log of a windowed, baseline-corrected patch — `window` is `fitRadius`); it returns the position only, not the width or amplitude |
| `STICS/velocity.m` | regress the peak track over the linear region → `v_x`, `v_y` | 🚧 `IcsCarpet.velocity` regresses the peak track and returns a `FlowVector` with a pooled goodness of fit; the `omegaThreshold` linear-region cutoff is not implemented, so the lag range is still the caller's choice |
| *(spatially resolved STICS)* | sliding sub-region × time-window grid → **flow vector field** | 🚧 `flow_map.stics_flow_map` tiles the field (`tile`/`step`, overlapping allowed) into a `FlowMap` of `(vx, vy, quality, amplitude)` with a `quiver()` accessor; **one time window only** — no TOI series, no vector rejection, no polygon mask |
| `TICS/difffit.m`, `diffusion3d.m`, `diffflowfit.m`, `flowfit.m` | standalone TICS decay models (diffusion, 3D diffusion, diffusion+flow, pure flow) | ❌ the carpet exposes the decay, but there are no selectable TICS decay models |
| `imageManipulation/wnCorr.m` | white-noise/background correction from a user-picked background box | 🚧 background handling exists in `IcsSettings`; not the ROI-picked variant |
| `ICS/autocrop.m`, `imageManipulation/serimcrop.m` | crop / ROI | ✅ `chisurf/core/roi` + `IcsSettings.roi` |
| `simul8tr/` | synthetic stacks (diffusion, flow, blinking, PSF, counting/background noise) | → [PRD-53](prd-53.md) |
| `imageManipulation/rd_img16.m`, `rd_imgser.m` | vendor-specific TIFF/RAW readers | ✅ superseded by the shared image-source seam ([PRD-67](prd-67.md)) |

## What the 2015 STICCS package adds — this is the actual algorithm

`stics_vectormapping.m` is the specification. Its pipeline, none of which ChiSurf has:

1. **ROI × TOI tiling.** A spatial window (`ROIsize`, default 16 px) slid by `ROIshift`
   (4 px, i.e. overlapping) crossed with a temporal window (`TOIsize`, 60 frames)
   slid by `TOIshift`. Output is a **time series of vector maps**, not one map.
2. **Immobile filtering — four choices, not one.** `FourierWhole` (zero the temporal
   DC, add the mean back), `MovingAverage` (subtract a running mean over `MoveAverage`
   frames, default 21), `butterIIR` (zero-phase 6th-order Butterworth high-pass,
   cutoff `2/(t_frame * n_frames)`), `none`. These are **not equivalent**: the
   moving-average and Butterworth variants remove anything *slower* than their
   cutoff, which is what you want when the "immobile" fraction is really a slow
   drift. The 2006 one-liner is only the degenerate Fourier case.
3. **Bounded Gaussian fit.** `gaussfit(..., fitRadius)` weights only pixels within
   `fitRadius` (8 px) of the peak. Fitting the whole ROI map is both slower and
   wrong — distant structure pulls the centroid.
4. **Automated linear-region cutoff — `omegaThreshold`.** Truncate the lag series at
   the first lag whose fitted beam waist exceeds a threshold (10 px). Once the peak
   has spread that far its position is meaningless. **This is the headless criterion
   the 2006 `velocity.m` asked the user to click for** — it already exists and does
   not need inventing.
5. **Peak-significance gate.** `correlationSignificance.m` implements the Ji &
   Danuser (*J. Microsc.*, 2005) test: reject a correlation function whose global
   maximum is not clearly dominant over the other regional maxima — with the
   deliberate subtlety that two maxima belonging to *one* broad peak must still pass.
6. **Three-stage vector rejection.** (a) `vectorOutlier` — compare each vector to the
   median of its 8 nearest neighbours against a threshold scaled by the std of its 24
   nearest; (b) drop NaNs; (c) reject magnitudes beyond 3σ, **iterated twice**,
   because the first pass's mean and std are themselves contaminated by the outliers.
7. **A physical velocity ceiling.** `thresholdV = sqrt(ROIsize^2/2) * pixelSize /
   (t_frame * tauLimit)` — a peak cannot be tracked further than the ROI half-diagonal
   within the lag window, so anything faster is an artefact, not a measurement.
8. **Polygon cell mask** (`DetermineCellMaskFromAverageImage`, `roipoly`) selecting
   which ROIs are computed at all — correctness *and* the dominant speedup.
9. **STICCS — the two-channel extension.** `sticcs_vectormapping.m` produces **four**
   vector maps per TOI: channel-1 auto, channel-2 auto, and both cross-correlations
   12 and 21. The two cross maps are *not* redundant: an inter-channel `timeDelay`
   (sequential-scan acquisition) makes them asymmetric, and that asymmetry is the
   interaction/co-transport signature. This is a distinct method, previously not in
   PRD-51's scope, and the natural partner to [PRD-67](prd-67.md) colocalization.

## What the other vendored ICS tools add

| Tool | Contributes |
| --- | --- |
| `junk/pysimfcs/` | The N&B and RICS reference, in Python. Formulas below. |
| `junk/ipcf/` | Pair-correlation (pCF) over multi-gigabyte series in overlapping chunks — the out-of-core/chunking reference if vector-map cost becomes the problem. pCF itself is [PRD-54](prd-54.md). |
| `junk/Imaging_FCS/` | Arbitrary pixel binning + ROI for imaging FCS/ICCS, TIRF/SPIM fit models, and **FCS diffusion laws** (the `tau_D` vs area intercept that distinguishes free / meshwork / domain diffusion) — a distinct readout none of the above provides. |
| `junk/Correlescence/`, `junk/FCSlib/`, `junk/PAM/`, `junk/quickfit3/` | Not yet surveyed for this PRD; check before implementing N&B or the diffusion laws. |

## What pysimfcs pins down — the formulas to port

`junk/pysimfcs/analysis_utils.py` (594 lines, NumPy/SciPy only) is a readable Python
reference. Concretely:

**N&B, photon counting** (`n_and_b.ipynb`, `var`/`covar`):

```
B = var/avg - 1            # the -1 removes the shot-noise floor
N = avg/B
```

**Cross N&B (ccN&B)** — hetero-interaction between two channels, and an easy thing to
get subtly wrong:

```
covar  = <Ia*Ib> - <Ia><Ib>
coavg  = sqrt(avg_a * avg_b)
Bcross = covar/coavg       # NO -1: shot noise is uncorrelated between channels
```

**N&B, analog** (`n_and_b_analog.ipynb`) — not a variant of the above but a different
formula plus its own calibration:

```
avg_corr = (avg - offset)/S
B        = var/(S*avg) - 1
```

`S` (gain) and `offset` come from a **calibration measurement**: image a
non-fluctuating intensity gradient, plot per-pixel variance against mean, and read the
slope and intercept. That is a workflow of its own, not a settable number.

**Map post-processing.** Both paths threshold to NaN *before* Gaussian-smoothing the
maps (σ≈2 px) — hence `gaussFilterNaN`, which zero-fills, smooths, then restores NaN.
Smoothing across a masked edge without this leaks background into the map. The same
helper is what the STICS vector maps need for their rejected (NaN) vectors.

**Detrending** (`detrendStackLinearSeg`) is **segmented**, not one line per pixel: the
stack is cut into `segments` time chunks and a per-pixel line is fitted and subtracted
within each. `maintain_intensity=True` adds the mean back — **required**, because `B`
is `var/avg` and detrending without restoring the mean changes the denominator.
`getStackTrends` does the per-pixel least-squares in closed form over the whole stack
at once (no Python loop over pixels) — port that shape, not a per-pixel `polyfit`.

**RICS by profiles** (`ricsfunc`, `getricshalf`) — fit the horizontal (pixel-time) and
vertical (line-time) single-side profiles **simultaneously as one concatenated
vector**, with `skipg0=True` dropping the zero-lag point (shot-noise/afterpulsing
contaminated). Three PSF forms are offered: 3D Gaussian, Gaussian-Lorentzian²,
and 2D Gaussian.

**Also worth taking:** `avgquadrants` (average the four quadrants of a 2D correlation
map — a real SNR win for isotropic RICS/ICS, and it would **destroy** STICS, whose
whole signal is the peak being off-centre; gate it per method, never apply by
default); `binmultilog`/`carpetbml` (log-binning of a correlation, bin size doubling
every `tauwidth` points) for TICS display and fit weighting; `paircorrelation` for
pCF; `polyContains` for the cell polygon mask.

**The reference has defects — port with tests, not by transcription.** In `ricsfunc`
the multi-component branches reference undefined names (`hxvals`, `vxvals`), so any
fit with more than one component raises `NameError`; and the vertical radial term is
built from `xvals[:fitsize]` where it should use `xvals[fitsize:]` (benign only
because both halves currently carry identical values). Whatever we port must have a
multi-component RICS test, which is exactly what the reference never ran.

**Do not port the Matlab structure.** Both packages wire GUI handles (`gcbf`,
`waitbar`, `roipoly`, `inputdlg`) into the numerics, and the 2015 driver hard-codes
Windows paths and writes `.mat`/PDF side effects from inside the analysis. The port
keeps the *physics and the estimators* and re-expresses them headlessly:
`chisurf/core/experiments/ics/` for the estimators, `chisurf/core/models/ics/` for
the fit models, AutoForm `view.json` for every UI, and the cell polygon supplied as
a `chisurf/core/roi` region rather than drawn mid-run.

**But do port its judgement.** The 2006 package asks the user to *click* the end of
the linear region; I had planned to invent a headless criterion for that. No need —
`omegaThreshold`, the significance gate, the three rejection stages and the velocity
ceiling are exactly that judgement, already worked out and validated in a published
method. Reproduce them; do not substitute something simpler and call it equivalent.

# Open question — does the kernel belong in tttrlib?

The carpet is currently pure NumPy: `n_lags × (n_frames − Delta)` 2D FFTs.
STICS vector mapping multiplies that by ROIs × TOIs, and the reference defaults make
the multiplier concrete: 16-px ROIs shifted by 4 px means **~16× overlap**, so a
512×512 field is ~15 000 ROIs *per time window*, each with its own `tauLimit`-deep
carpet and per-lag fit. The polygon mask is what makes this tractable at all. Two
candidates:

* **Keep it in ChiSurf (NumPy/FFT).** No new C++ surface; the sub-region loop
  parallelises trivially; FFT plans dominate and NumPy already delegates them.
* **Push the kernel into the companion photon library.** It already owns the
  image-from-stream (CLSM) path that produces these stacks, so a C++ kernel
  would correlate without ever materialising the stack in Python, and would be
  reusable outside ChiSurf.

**Decide by measurement, not by preference** — benchmark the reference's own defaults
(512×512 × 300 frames, `ROIsize` 16, `ROIshift` 4, `TOIsize` 60, `TOIshift` 1,
`tauLimit` 21) before writing any C++. Record the numbers in
[benchmarks](/references/benchmarks.md). The prior is that this is FFT-bound and
therefore *not* a language problem — the same conclusion the decay-fit FFT work
reached — and that the algorithmic wins (mask early, reuse FFT plans across ROIs of
equal size, batch the per-lag fits) land before any language change would.

# Scope

- **STICS velocity workflow** (the port above) — ROI×TOI tiling, the four immobile
  filters, bounded per-lag peak tracking, `omegaThreshold` cutoff, regression,
  significance gate, three-stage vector rejection, velocity ceiling, and a time
  series of flow vector maps.
- **STICCS** — the two-channel extension: four vector maps per time window (two auto,
  two cross), with the inter-channel acquisition delay carried explicitly so the 12/21
  asymmetry is interpretable.
- **N&B** — brightness & number maps from pixel mean/variance; **photon-counting and
  analog** variants (the analog path needs its own gain/offset calibration from a
  gradient measurement); **ccN&B** cross-brightness between two channels; B-vs-N
  histogram gating with back-mapping to pixels; NaN-aware map smoothing; and
  segmented per-pixel **detrending** with mean restoration as a required pre-step
  (a bleaching correction, distinct from the immobile filter).
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
- `chisurf/core/roi` — sub-region tiling and the cell polygon ([ROI subsystem](/subsystems/roi.md)).
- The companion photon library's CLSM image-from-stream + mask handling.
- AutoForm + `view.json` for all UIs (PRD-49 AutoForm mandate); reuse
  `image` / `waterfall` / `region_list` sections.
- Vector-field overlay must go through [chiplot](/prds/prd-64.md), not pyqtgraph.

# Definition of Done

- [ ] All four immobile filters headless (`FourierWhole` / `MovingAverage` /
      `butterIIR` / `none`), with a test that distinguishes them: a stack whose
      static component *drifts slowly* must be cleaned by the moving-average and
      Butterworth filters and **not** by DC removal. One filter is not enough.
- [ ] Per-lag Gaussian peak tracking returning `(x0, y0, w, amplitude)` per frame lag,
      weighted within `fitRadius` of the peak, with a test that distant structure
      outside the radius does not move the fitted centre.
- [ ] `omegaThreshold` cutoff + linear regression → `(v_x, v_y)`, fully headless; the
      interactive picker only as an override.
- [ ] Peak-significance gate (Ji & Danuser 2005), including the case it is designed
      for: two regional maxima belonging to one broad peak must still **pass**.
- [ ] Three-stage vector rejection — neighbour-median (8 nn) vs 24-nn std, NaN drop,
      and 3σ magnitude **iterated twice** — with a test that the second iteration
      changes the result (otherwise the iteration has been silently dropped).
- [ ] Velocity ceiling `sqrt(ROIsize^2/2)*pixelSize/(t_frame*tauLimit)` computed and
      applied, not left to the user to remember.
- [ ] Spatially resolved STICS: ROI×TOI tiling → a **time series** of vector maps,
      rendered as a chiplot overlay on the image; ROI selection driven by a
      `chisurf/core/roi` polygon, which must also skip the excluded ROIs (the speedup).
- [ ] STICCS: four vector maps per time window (auto 1, auto 2, cross 12, cross 21)
      with the inter-channel delay carried explicitly, and a test that 12 and 21 are
      **not** forced equal.
- [ ] N&B: `B = var/avg - 1`, `N = avg/B` maps; recovers a known brightness on a
      simulated stack; **analog** variant `B = var/(S*avg) - 1` with `S`/`offset` from a
      gradient calibration (a workflow, not a settable number); B-vs-N histogram gating
      that back-maps a selected region onto pixels.
- [ ] ccN&B cross-brightness `covar/sqrt(avg_a*avg_b)`, with a test pinning that the
      `-1` shot-noise term is **absent** from the cross channel — copying the auto
      formula here is the obvious mistake and silently biases every result.
- [ ] Segmented per-pixel detrending with mean restoration, closed-form and vectorised
      over the stack; test on a bleaching stack that `B` is recovered only after
      detrending, and that omitting the mean restoration breaks `B` — pinning that it
      is not interchangeable with the immobile filter.
- [ ] Map smoothing is NaN-aware (threshold to NaN, then smooth without leaking
      background across the mask edge); shared with the STICS vector maps' rejected
      vectors.
- [ ] `avgquadrants` quadrant averaging available for isotropic RICS/ICS and **blocked
      for STICS**, with a test that it is not applied where the peak is off-centre.
- [ ] RICS profile fit (horizontal + vertical concatenated, `G(0)` skipped) with a
      **multi-component** test — the branch the reference implementation never ran and
      that raises `NameError` there.
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
([PRD-53](prd-53.md)); pair-correlation analysis ([PRD-54](prd-54.md), with
`junk/ipcf/` as its chunking reference).

**Parked with a home, not a hand-wave:** imaging FCS / ICCS with arbitrary pixel
binning, and the **FCS diffusion laws** from `junk/Imaging_FCS/` (`tau_D` vs binned
observation area; the intercept separates free from meshwork-hindered and
domain-partitioned diffusion). Genuinely distinct readouts, and **no PRD owns them** —
checked, not assumed. They are now rows in the [PRD-49](prd-49.md) parity matrix
marked *no owning PRD*, so the gap is visible in the roadmap rather than buried in
this PRD's non-goals. Give them a PRD before anyone starts them; do not let them
drift into PRD-51 by accident, since they share only the input data, not the method.

# Relationships

- Child of [PRD-49](prd-49.md) (Phase 2).
- Builds on the landed ICS carpet + model; synthetic validation stacks from [PRD-53](prd-53.md).
- Shares the image-source seam with [PRD-67](prd-67.md) (colocalization).
- All UIs via [GUI & AutoForm](/subsystems/gui-autoform.md); all plotting via [PRD-64](prd-64.md) (chiplot).
- Phasor imaging is [PRD-52](prd-52.md); spectral unmixing beyond RICS weighting is [PRD-54](prd-54.md).
- Theory: [image correlation — RICS, STICS, TICS and iMSD are one method](/references/image-correlation-theory.md).
