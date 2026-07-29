---
type: Reference
title: Use case — CLSM Generator, a FLIM image with known lifetimes
description: Simulate a confocal photon stream from an intensity image plus a per-detector lifetime map, so that every pixel-wise FLIM analysis can be checked against a ground truth it did not produce.
tags: [usecase, imaging, clsm, flim, simulation, lifetime, ground-truth]
timestamp: '2026-07-29T00:00:00Z'
---

# Use case: CLSM Generator — a FLIM image whose lifetimes you already know

**Goal:** produce a synthetic confocal photon stream in which *every pixel's
intensity and fluorescence lifetime were chosen by the user*, so that the
pixel-wise analyses documented elsewhere — the
[FLIM pixel maps and pixel-wise MLE](/usecases/flim-pixel-maps-mle.md) pipeline,
[molecule-wise MLE](/usecases/molecule-wise-lifetime-mle.md),
[phasor](/usecases/flim-pixel-maps-mle.md), the
[drift](/usecases/image-drift-correction.md) and
[FRC](/usecases/frc-resolution.md) estimators — can be validated against a truth
they did not compute. It is the imaging counterpart of
[Simulate a TCSPC decay and recover its lifetimes](/usecases/tcspc-simulate-and-recover.md),
and the per-pixel counterpart of the
[simulated acquisition](/usecases/acquisition-simulated-measurement.md).

**Tool:** `Imaging → Simulate → CLSM Generator`
(`chisurf/plugins/microscopy/clsm_generator`, AutoForm over
`generator.view.json`; engine
`chisurf.core.fluorescence.imaging.simulate.simulate_clsm_from_maps`, which
raster-scans a `tttrlib` `SimEngine`/`SimScanner` sample).

**Data:** no repo file is needed — the inputs *are* the ground truth and the user
authors them. This run used a 24 × 24 two-population phantom written with numpy:
a bright disc (relative intensity 1.0, τ = 1.0 ns) and a dimmer disc
(intensity 0.5, τ = 3.5 ns) on an empty background, saved as `intensity.npy` and
`lifetime.npy`; plus a 12 × 32 rectangular variant and a second-detector map
(τ = 2.0 / 4.0 ns) for the multi-channel path.

## Steps

1. Open the tool. It is a two-tab dock: **Inputs** (form) and **Maps** (image
   browser). It opens on *Inputs*.
2. **Intensity image** — pick a 2-D `.tif`/`.npy`/`.npz` of relative per-pixel
   brightness. The info line becomes `Intensity 24×24; 0 lifetime map(s) loaded.`
3. **Lifetime map(s)** — `➕ Files` one fluorescence-lifetime map **in ns per
   detector channel**, matching the intensity shape. The info line counts them.
4. Expand the collapsed **▶ Simulation** panel and set the acquisition:
   *Pixel size (µm)*, *Dwell*, *Micro-time channels*, *Channel width (ns)*,
   *Brightness*, *IRF centre*, *IRF σ*, *τ levels*, *Intensity levels*.
   The excitation period is `Micro-time channels × Channel width` — **set it to
   at least ~5 × your longest lifetime** (see RF-961; the shipped defaults give
   8.192 ns).
5. Press **🧪 Generate**. It runs on a worker thread; the info line goes
   `Generating CLSM photon image…` then `Generated N photons (D detector(s)).`
6. Click the **Maps** tab (it is not raised for you — RF-963) and step through
   *Intensity (input)*, *Lifetime (input)* and *Reconstructed intensity* in the
   left-hand list.
7. Press **💾 Save** and choose a path. Use **`.ptu`** or **`.npz`** — `.spc`
   and `.ht3` are offered but produce unreadable files (RF-960). An
   `<stem>_intensity.tif` of the reconstruction is written beside it.
8. Re-open the `.ptu` in a downstream tool as a `CLSMImage` with the markers the
   generator emits: `marker_frame_start=[4]`, `marker_line_start=1`,
   `marker_line_stop=2`, `use_pixel_markers=True`, `marker_pixel=8`,
   `n_pixel_per_line = n`, `settings={"n_lines": n}`.

## Expected

- The reconstructed intensity image reproduces the input intensity **up to
  Poisson noise and the PSF blur** — the ratio of two regions' mean counts equals
  the ratio of their input intensities, and the pixel geometry is unchanged.
- The photons in a region's pixels carry a mono-exponential decay of the τ that
  region was given, convolved with the Gaussian IRF, so
  `⟨micro-time⟩ − IRF centre ≈ τ`.
- The saved stream re-opens as a valid TTTR file and rebuilds the same image.

## Observed (last run: 2026-07-29)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, tttrlib 0.27.0 with
`SimEngine`) through the real `ClsmGeneratorTool`: widgets enumerated, the
**🧪 Generate** and **💾 Save** `QToolButton`s clicked, the *Maps* tab raised and
each browser row selected, screenshots grabbed and read at every step.

**The physics is right, and the `.ptu` round trip is exact.**

- 24 × 24 phantom, defaults: **0.5 s**, `Generated 9379 photons (1 detector(s))`.
- Intensity fidelity: mean counts 103.06 in the `I = 1.0` disc against 50.00 in
  the `I = 0.5` disc — a ratio of **2.061** against a true 2.0. 18 of 9379 counts
  land outside the discs, which is the 0.3 µm PSF on a 0.5 µm pixel, as it should
  be.
- Lifetime fidelity **at an adequate excitation period** (256 × 0.128 ns =
  32.768 ns): `⟨t⟩ − IRF = 1.005 ns` against a true 1.0, and `3.402 ns` against a
  true 3.5.
- Round trip: the saved `.ptu` re-opens with all 10 004 events, rebuilds to a
  `(1, 24, 24)` `CLSMImage` summing to **9379** — *identical* to the exported
  `_intensity.tif` (`np.array_equal` True) — and the reloaded stream returns
  **1.005 ns** and **3.402 ns** for the two regions. The ground-truth loop closes.
- The image browser is correct and legible: both discs appear in the right place
  with the right colour scale in the input, the lifetime map and the
  reconstruction (`11_browser_*.png`).

**What is wrong is everything around it.**

- **Two of the four offered save formats are unreadable.** The dialog filter
  (`tool.py:101`) and the Save tooltip both advertise `.npz / .ptu / .spc /
  .ht3`. Writing `.ht3` produces a 40 744-byte file and `.spc` a 40 020-byte
  file, both reported as `Saved photon stream to loop.ht3` — and both re-open
  with **0 events**. `tttrlib`'s `TTTR.write` emits PTU records whatever the
  extension: `.ptu` → 10 004 events, `.ht3`/`.spc`/`.hdf`/`.t3r` → 0. **RF-960.**
- **The shipped defaults cannot represent an ordinary lifetime.** `n_micro = 256`
  and `dt = 0.032 ns` give an excitation period of **8.192 ns**. The τ = 3.5 ns
  region comes back at **2.582 ns — 26 % short** (the truncated-exponential mean
  for that window is 2.627 ns, so the loss is exactly the window, not noise);
  its decay is still at 10.9 % of peak at the last channel, against 0.05 % at
  32.768 ns. τ = 1.0 ns is fine (0.992). The panel's own info text promises "the
  photon image reproduces the input intensity and lifetime" and warns about
  nothing. A user calibrating a FLIM analysis on this would blame the analysis.
  **RF-961.**
- **A non-square image changes shape.** `n_pixel = max(h, w)`: a 12 × 32 input
  is simulated and reconstructed as **32 × 32**. The *Maps* browser then shows a
  12 × 32 input beside a 32 × 32 "reconstruction", the exported TIFF is 32 × 32,
  and a pixel-by-pixel comparison against the truth needs an undocumented crop.
  No message. **RF-962.**
- **Generate shows nothing.** The view-model sets `current_view = "recon"`
  (`view_model.py:148`) but the dock stays on *Inputs*; the reconstruction lives
  on a *Maps* tab that is never raised. Pressing the tool's primary button
  appears only to change one line of italic text (`04_generated.png` is
  indistinguishable from `03_lifetime_loaded.png` apart from that line).
  **RF-963.**
- **An empty simulation is reported as a success.** An all-zero intensity image
  and an all-NaN lifetime map both pass `can_generate()` and return
  `Generated 0 photons (1 detector(s))` in the same wording as a good run, with
  `has_result()` True — so **💾 Save** writes a photon-free file. **RF-964.**
- **A file that cannot be loaded is accepted in silence.** A missing path and a
  corrupt `.npy` (verified: 31 bytes of text) both leave the path sitting in the
  *Intensity image* box while the info line reverts to the generic "Load an
  intensity image…" instruction. Nothing says the box's contents were rejected.
  **RF-965.**
- **Two detectors in, one image out.** Two lifetime maps give two *input* browser
  entries (`Lifetime d0`, `Lifetime d1`) but still a single *Reconstructed
  intensity*, summed over both routing channels (18 552 counts over channels 0
  and 1). The per-detector images the simulation just produced cannot be looked
  at. **RF-966.**

Screenshots: `01_opened.png`, `03_lifetime_loaded.png`, `04_generated.png`,
`10_maps_tab.png`, `11_browser_{0,1,2}_*.png`, `20_simulation_expanded.png`.

## UX / UI suggestions

- **Show the excitation period.** `Micro-time channels × Channel width` is the
  one number that decides whether the simulation can represent the user's map,
  and it is nowhere on screen. Put a read-only `period = 8.192 ns` beside those
  two boxes, and colour it when it is below ~5 × the largest finite τ in the
  loaded maps (which the tool has already read).
- **Give the parameters units.** *Dwell* has no unit in label or tooltip
  ("simulator macro-time units"); *IRF centre* and *IRF σ* are in **micro-time
  channels** (10.00 and 1.60 = 0.320 ns and 0.051 ns at the defaults) but read
  like nanoseconds next to "Channel width (ns)". Show the ns equivalent inline.
- **Cap the info box.** `generator.view.json:14` sets `"height": 64`, but
  AutoForm's `InfoWidget` treats `height` as a *minimum* and only `max_height`
  caps it (`builtin.py:929-934`) — measured **192 px** of blank white above the
  fields. Add `"max_height": 64`.
- **Rebalance the panel.** The lifetime `path_list` claims **410 px** for what is
  normally one or two entries, while the *Simulation* panel — the part the user
  actually tunes — is collapsed to a 27 px bar. Expand *Simulation* by default
  and cap the list.
- **Pair the parameters.** The two-column flow puts *IRF σ* in the left column
  and *IRF centre* in the right, on different rows, and splits *τ levels* from
  *Intensity levels* the same way. Group each pair on one row.
- **Progress for long runs.** 32 × 32 took 0.11 s, 64 × 64 **1.24 s**, 128 × 128
  **7.47 s** — so 256 × 256 is ~30 s — behind a single static
  `Generating CLSM photon image…` with no bar, no ETA and no cancel. The work is
  a per-pixel loop, so it is trivially reportable.
- **Widen the browser list.** `"list_width": 180` clips
  "Reconstructed intensit[y]" (`11_browser_2_*.png`).
- **Scale the image axes.** The browser draws pixel indices although *Pixel size
  (µm)* is known — label the axes in µm or draw a scale bar.
- **Record the provenance.** The saved stream keeps nothing about the maps or the
  parameters that produced it, so the ground truth has to be tracked by hand —
  and the marker configuration needed to re-open it as a `CLSMImage`
  (frame `[4]`, line `1`/`2`, pixel `8`, `use_pixel_markers`) is written nowhere.
  Save a small sidecar JSON, or push the result straight into the session the way
  the other simulators do.
- **Warn about a 3-D map.** `load_image_map` collapses a 3-D stack by *summing
  the leading axis* — sensible for an intensity stack, meaningless for a lifetime
  stack (four 2 ns planes become 8 ns). Verified: a `(4, 8, 8)` input loads as
  `(8, 8)`. Say so, at least for the lifetime input.

## Bugs filed

- RF-960 — `.spc` / `.ht3` save writes unreadable files and reports success.
- RF-961 — default excitation period 8.192 ns silently truncates any τ ≳ 2 ns.
- RF-962 — a non-square intensity image is padded to a square reconstruction.
- RF-963 — **Generate** never raises the *Maps* tab, so the result is invisible.
- RF-964 — a 0-photon simulation is reported in the success wording and saved.
- RF-965 — an unloadable input file is accepted silently.
- RF-966 — a multi-detector run offers only one, summed, reconstruction view.
