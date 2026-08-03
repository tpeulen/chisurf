---
type: Reference
title: Use case — single-particle tracking to a diffusion coefficient
description: Detect diffraction-limited particles in every frame of a movie, link them into trajectories, and fit D (and optionally the anomalous exponent) from the ensemble MSD — validated against the tool's own ground-truth simulator.
tags: [usecase, imaging, microscopy, tracking, diffusion, msd]
timestamp: '2026-07-27T00:00:00Z'
---

# Use case: particle tracking — from spots to a diffusion coefficient

**Goal:** follow individual particles through a movie and turn their
trajectories into a **diffusion coefficient**. Three stages, each exposed
separately because each fails in its own way: *detect* the spots in every frame,
*link* them into trajectories by exact global assignment (Hungarian, with gap
closing), and fit `MSD = 4·D·τ^α + 4·σ²` to the count-weighted ensemble MSD with
uncertainties from resampling whole tracks.

Where it sits: the imaging counterpart of an FCS measurement. FCS gives D from
the fluctuations of a population; tracking gives it per particle and shows *why*
the number is what it is (confinement, directed motion, identity swaps). It
belongs after *Drift* in the Image Tools order — a drifting sample looks exactly
like directed motion, and no amount of tracking separates the two afterwards.

**Tool:** *Imaging → Particle Tracking*
(`chisurf.plugins.microscopy.img_tracking.gui.tool:ImgTrackingTool`, plugin id
`img_tracking`); also the **Tracking** panel of Image Tools. CLI `img-tracking`;
RPC `img_tracking.jobs.track` / `img_tracking.jobs.simulate`. Docs:
`docs/guides/50_particle_tracking.md`, `docs/concepts/particle_tracking.md`.

**Data:**
- the tool's own **simulator** (fold-out *Simulate instead*), which is the only
  way to know the right answer: 8 Brownian particles, 60 frames, 256 px field,
  **true D = 0.5 px²/frame**;
- a real image stack — `test/data/rics/RICS_EGFPGFP.tif` (50 × 300 × 300 uint16,
  max 24 counts; RICS data, i.e. deliberately *not* trackable, which is what
  makes it a good negative control);
- a photon stream — `test/data/clsm/PQ_Olympus_MFIS.ht3` (CLSM frames from the
  scan markers, 5 detector channels, 256 × 256).

## Steps

1. Open the tool. Left is a **Settings** dock (*Movie*, the collapsed *Simulate
   instead*, then the numbered *1. Detect*, *2. Link*, *3. Transport*); right is
   a **Report** panel over a **Views** dock with five tabs (Movie, Trajectories,
   MSD, Track lengths, Tracks). The toolbar carries ▶ Track, 📂 Open, 💾 Export
   CSV and a **?** help button at the far right.
2. Press **▶ Track** with nothing loaded: the status bar answers *"Load an image
   stack, or tick Simulate."* — no dialog, no traceback.
3. **Learn the tool on a known answer.** Unfold *Simulate instead*, tick
   **Simulate**, leave the defaults (True D 0.5 px²/frame, 8 particles, 60
   frames, 256 px, amplitude 250, background 10, seed 1) and press **▶ Track**.
4. Read the **Report**: detections per frame, track count and median length, then
   `D ± error`, `alpha`, the localisation error, and a *"Read with care"* block
   listing the reasons the number should not be quoted as-is.
5. Walk the **Views** tabs: *Movie* (every detection marked; scrub the frame
   slider and the markers should follow the particles), *Trajectories* (y
   inverted, image coordinates), *MSD* (log–log; free diffusion is a straight
   line of slope 1), *Track lengths*, and the per-track *Tracks* table
   (#, points, first–last frame, net displacement).
6. **Calibrate.** Set *3. Transport* → **Pixel size [µm]** and **Frame interval
   [s]** and re-run; D changes from px²/frame to physical units.
7. Ask whether the motion is anomalous: tick **Fit anomalous exponent**, re-run,
   and read α *with* its error bar before concluding anything.
8. **Now the real file.** Untick Simulate, drag `RICS_EGFPGFP.tif` onto the
   window (or 📂 Open). The report says *"Loaded … Press Track."* Set **Max
   frames** to a handful for a first look, press **▶ Track**, and sweep
   **Threshold [σ]** until the detections-per-frame in the report match what you
   can see in the Movie view.
9. Repeat with a photon stream (`.ht3`/`.ptu`): the same drop → Track path works,
   `info.kind` becomes `tttr` and `channel_names` lists the detectors; the
   **Channel** spin selects which one to track in.
10. **💾 Export CSV** writes every linked detection as `track,frame,y,x,intensity`.

## Expected

- The simulated run recovers the true D within its stated uncertainty, and says
  out loud when the run is too thin to trust.
- Detections track the particles in the Movie view; the MSD is a straight
  slope-1 line; the trajectory plot shows no long-range jumps (those are identity
  swaps).
- A real file that contains no trackable particles produces *no* number, and says
  which stage came up empty.
- Units in the report follow the calibration actually entered.

## Observed (last run: 2026-07-27)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) by instantiating
`ImgTrackingTool`, setting the AutoForm-bound controls, triggering the toolbar
actions and waiting on the view-model's `computed` event; screenshots read at
every step.

**The good.** The core science is right and fast.

- Simulation, defaults: `60 frames, 480 detections (8.0 per frame) / 8 tracks,
  median length 60, longest 60 / D = 0.5038 ± 0.1 px²/frame` against a true
  0.5 — 0.8 % from truth — in **1.7 s**, and it still prints *"only 8 tracks
  contributed — D from this few is uncertain by tens of per cent however tight
  the curve looks"*. This matches the number in the shipped guide exactly.
- Full calibration behaves: pixel 0.1 µm + interval 0.05 s gives
  `D = 0.10077 µm²/s`, exactly `0.5 · 0.1² / 0.05`.
- Fitting α returns `D = 0.3836 ± 0.22, alpha = 1.09 ± 0.21` and warns that α is
  unresolved and that D now carries a 58 % standard error — the degeneracy the
  help text warns about, demonstrated rather than asserted.
- The whole pipeline runs off the UI thread with a live status bar
  (`detecting particles (5 %)` → `linking … detections` → `fitting transport`),
  and the status bar ends on `N tracks, D = … ± …`. 50 frames × 300 × 300 with
  77 796 detections took 58 s and never froze the window.
- Error paths are clean: a channel the file lacks gives *"channel 5 does not
  exist; the file has 1 (ch0)"*; exporting before a run raises the honest
  *"run the tracker before exporting"*; a 2-frame movie says no track is long
  enough rather than crashing.
- `.ht3` photon streams load through the same drop path (`kind: tttr`, 5 channel
  names) and detections land on the structure in the Movie view.

**The bad.** Four things a user would trip over, all filed:

- With **only one** of the two calibrations entered, the report labels D in
  µm²/s regardless. Simulated D = 0.5 px²/frame with the pixel size left at its
  default 1 and the interval at 0.05 s is reported as `D = 10.08 ± 2 µm²/s` —
  the number is px²/s (RF-418).
- The Report panel is pre-formatted text with **no wrapping**, so the 280-character
  "what to do next" sentence is cut off at the panel edge and needs a horizontal
  scrollbar — at 1500 px *and* at 1920 px wide (RF-419).
- On the real TIFF at the default 5σ the tool found **0 detections in 50 frames**
  and then advised *"lower min_length or improve the linking … a larger max
  linking distance"* — advice about stage 2 when stage 1 produced nothing
  (RF-420).
- Pushed to 1σ on that same file, the tool returns `D = 1.407 ± 0.35 px²/frame`
  from 1550 detections per frame of pure noise, 1215 of 21 954 tracks (5.5 %) and
  a median track length of 3 — with **no** "Read with care" block at all
  (RF-421).

**The interesting.** Two ground-truth checks worth keeping:

- Crowding is the failure mode the tool documents, and it bites hard: 200
  particles at true D = 5 px²/frame (so ≈4.5 px per frame against a 5 px linking
  distance) returns `D = 2.812 ± 0.98`, **44 % low**, with median track length 2
  and only 138 of 3187 tracks used. Only the generic 35 %-standard-error note
  fires; nothing says the trajectories were shattered.
- On the RICS file the detector has a cliff rather than a slope: 5σ → 0
  detections, 3σ → 9, 2σ → 794, 1σ → 15 505 (over 10 frames). There is no
  guidance in the UI for where on that cliff to stand.

## UX / UI suggestions

- **Show the detection count while sweeping the threshold.** The 5σ → 1σ cliff
  (0 → 1550 detections/frame) is invisible until a full run finishes. A live
  "detections in frame N at this threshold" readout beside *Threshold [σ]*, or a
  one-frame preview button, would turn a blind sweep into a decision.
- **Say what a zero means.** `localisation error = 0 px` is a clamped negative
  fit offset ("unresolved"), not a measurement of perfect localisation — print
  *"unresolved"* rather than `0`.
- **Warn on a shattered length distribution.** `MsdFit.warnings()` checks the
  track count, the relative error and α, but never the *shape* of the track-length
  distribution or the fraction of tracks that survived `min_track_length` — which
  is precisely what the tool's own guide says biases D low (see RF-421).
- **Print the units in the status bar too.** `8 tracks, D = 0.5038 ± 0.1` carries
  no unit at all, and it is the line a user reads first.
- **Label the MSD axes with units.** `lag` and `MSD` become seconds and µm² once
  calibrated; the axis titles never change.
- **The settings grid overflows at the tool's own minimum width.** At 1500 × 950
  (the tool sets a 1040 × 680 minimum) the whole right-hand column of every
  settings row — Threshold, Min separation, Max gap, Frame interval, Tracks drawn
  — is cut off at the dock edge and reachable only through a horizontal
  scrollbar. It is only comfortable at ≥1900 px. One column, or a width-aware
  wrap, would fix it.
- **The Report dock does not defend its height.** After switching view tabs (with
  a persisted dock layout) it shrank to ~90 px and clipped `alpha = 1 (fixed)`
  mid-line, so the primary result is behind a scrollbar.
- **Give the tracks table a sensible last column.** `Net [px]` stretches to fill
  the whole width with its header centred hundreds of pixels away from its
  values.
- **Offer a "simulate what my setup can resolve" shortcut.** The simulator is the
  tool's best feature and is hidden inside a collapsed fold-out named *Simulate
  instead*; a user who has never read the guide will not find it before pointing
  the tool at real data.

## Bugs filed

- RF-418 — D is labelled µm²/s when only one of pixel size / frame interval is
  calibrated (S2).
- RF-419 — the Report panel does not wrap, so the guidance is clipped (S3).
- RF-420 — zero detections are diagnosed as a linking problem (S3).
- RF-421 — no warning when the fit rests on a small, shattered minority of
  tracks (S3).
