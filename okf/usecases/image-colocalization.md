---
type: Reference
title: Use case — two-channel colocalization (Pearson / Manders / Costes / objects)
description: Load a two-channel image, subtract background, derive Costes thresholds, read the colocalization coefficient set, check registration with van Steensel, test significance with the Costes randomization, gate a population in the intensity scatter, restrict to a painted ROI, and count objects for punctate signal.
tags: [usecase, imaging, colocalization, manders, costes, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: two-channel colocalization

**Goal:** answer "do these two stainings sit in the same places?" with numbers a
referee will accept — not one Pearson value, but the coefficient set (Pearson,
Manders overlap and split, Li ICQ, Spearman) computed on a **stated background
and a stated threshold**, plus the two checks that make it defensible: van
Steensel's registration profile (is the correlation real, or a chromatic shift?)
and Costes' randomization test (is it more than two dense stainings give by
chance?). For punctate signal the same window answers the other question —
how many spots of A have a partner in B.

**Data:**

- `test/data/clsm/PQ_Olympus_MFIS.ht3` — the shipped two-colour confocal FLIM
  scan (68 MB, 15.6 M photons, 40 frames × 256 × 256). Routing channels 0/1 are
  the *green* parallel/perpendicular detectors, 4/5 the *red* pair, ch2 is
  empty. This is the file the guide's "PCC ≈ 0.99" refers to.
- A camera-style stack is easiest to reason about because the truth is known by
  construction. The one used here is the pair from
  `examples/scripts/colocalization.py`, written to a two-channel ImageJ TIFF:
  three Gaussian blobs (σ = 6 px) on a background of 8, channel B = 0.8 × A,
  Gaussian noise σ = 3 → whole-image PCC = **0.9403** exactly; plus a punctate
  pair with **30 spots in A**, **25 in B**, of which **20 are partners** 1 px
  apart (so the truth is fraction A-with-partner = 0.667, B-with-partner = 0.80).

**Tool:** *Imaging → Colocalization* (`chisurf/plugins/microscopy/img_coloc`,
display name **Imaging:Colocalization**, `ImgColocTool`) — a standalone dock
tool, **not** one of the Image Tools steps, with a toolbar (**▶ Run**,
**📉 Estimate background**, **💾 Export CSV**, **?**), a single-column Settings
dock and nine result tabs. Headless twin: `img-coloc` (CLI).

## Steps

1. Open **Imaging → Colocalization**. Check the **Setup** combo at the top: it
   comes up on the *last setup used anywhere in ChiSurf*, not on
   `— raw detector channels —`. For a TIFF the setup is ignored; for a photon
   stream it decides what "Channel A/B" mean, so either pick the setup that
   matches the instrument or clear it (see RF-337).
2. Drop the image on the window (or use **📂** on the **Image** row). Loading
   **runs the analysis immediately** — no need to press Run. The 68 MB HT3 is
   read and reconstructed in ~2 s, the TIFF instantly.
3. Pick the pair in **Channel A** / **Channel B**. Without a setup these are the
   file's routing channels (`ch0 … ch5`) or the TIFF's channels; with one, the
   named windows. **Press ▶ Run after changing them** — picking a channel does
   *not* recompute (RF-336). For the HT3 the informative pair is `ch0` (green)
   vs `ch4` (red); `ch0` vs `ch1` is the two green detectors and serves as a
   positive control.
4. Leave **Frame** at `-1` (sum every frame — the 40 frames of the HT3 are what
   makes the per-pixel statistics usable).
5. Open **Background / thresholds**. **Auto background** is on by default and
   fills **Background A/B** from the 5 % quantile after the run. Tick
   **Costes thresholds** and press **▶ Run** again: **Threshold A/B** fill in
   with the values from the orthogonal-regression search, and the coefficients
   change a lot — on the synthetic pair Pearson goes 0.954 → 0.991 and Manders
   M1 0.97 → 0.58, because M1 is now the fraction of A's intensity that sits in
   the thresholded overlap rather than in every pixel.
6. Read the **Coefficients** tab. It is the whole report: the coefficients, the
   thresholds and backgrounds that produced them, and the pixel counts.
7. Check registration: open **Significance / profile**, set **van Steensel
   shift (px)** = 12, **▶ Run**. The *van Steensel CCF* tab must peak at shift 0
   (it does for both files here), and the *CCF map (2-D)* tab shows the same in
   both directions — use it, because a purely vertical offset leaves the 1-D
   profile peaking at zero.
8. Test significance: tick **Costes randomization test**, set **Block (px)** to
   the PSF width (4), leave **Randomizations** 200 and **Seed** 0, **▶ Run**.
   *Costes p-value* = 1 and *Costes random PCC mean* ≈ 0 mean the correlation is
   far outside what block-scrambling gives. On these images it costs ~1 s.
9. Restrict to a region (optional): open **Region of interest**, set
   **Brush (px)**, and paint on the *Channel A* map. Everything recomputes on
   the stroke — background, Costes thresholds, the profiles and every
   coefficient — and *ROI area fraction* appears in the table. **🧽 Clear ROI**
   restores the whole image.
10. Gate a population (optional): open **Scatter gate**, tick **Gate active**
    and either type **A min/max**, **B min/max** or drag the blue rectangle on
    the *Intensity scatter* tab. Three extra rows appear — *Gate: Pearson PCC*,
    *Gate: Manders MOC*, *Gate: pixels* — and the gated pixels brighten in
    *Colocalized pixels*. **🧹 Clear gate** drops the gate.
11. Punctate signal: open **Objects (punctate signal)**, tick **Object
    analysis**, **▶ Run**. Read *Objects in A/B*, *fraction A with B partner*
    and the median nearest-neighbour distances; the *Objects* tab maps
    1 = A only, 2 = B only, 3 = both. **The shipped defaults are too permissive**
    — raise **Smoothing (σ px)** to 1, **Min size (px)** to 9 and tick **Split
    touching objects** before believing the counts (RF-342).
12. **💾 Export CSV** writes the source path, the channel pair and every metric
    key/value.

## Expected

- The synthetic pair reports *Pearson PCC (all pixels)* = 0.9403 — exactly the
  value `np.corrcoef` gives on the two arrays.
- On the HT3, `ch0` vs `ch1` (green ∥ vs green ⊥, the same structure twice)
  gives PCC ≈ 0.995 / MOC 0.997 / M1 0.998; `ch0` vs `ch4` (green vs red) gives
  PCC ≈ 0.971 / MOC 0.980 / M1 0.976 — the "≈ 0.99" the guide quotes.
- van Steensel peaks at shift 0, the 2-D CCF peak at (0, 0).
- Costes p-value = 1 with a random-PCC mean ≈ 0.
- A ROI over the nucleus reports its area fraction exactly (4900/65536 =
  0.07477) and a *lower* PCC (0.933) than the whole frame, because the bright
  nucleus alone has less dynamic range than nucleus-plus-background.
- Object analysis on the punctate pair recovers 30 / 25 objects and partner
  fractions 0.67 / 0.80.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through the real
`ImgColocTool` — file drops, toolbar actions, combo picks, typed gates, a
painted ROI — with every result tab screenshotted and inspected.

- **The physics is right and it is fast.** Every number above reproduced.
  Whole-image PCC matched `np.corrcoef` to all four printed digits; the ROI area
  fraction was exact; the Costes threshold search, the randomization test, the
  van Steensel profile and the 2-D CCF all behaved. The 68 MB / 15.6 M-photon
  HT3 loads, reconstructs and computes the full coefficient set in **~2 s**, and
  adding the Costes test (200 randomizations) plus a 12 px CCF costs **~1 s**
  more. **📉 Estimate background** is correctly idempotent — pressing it three
  times in a row does not drift the background.
- **Changing the channel pair silently keeps the old result.** After picking
  *Channel B* = `ch4` in the combo the table still read `Pearson 0.9953` (the
  `ch0` vs `ch1` result), the status line still said `ch0 vs ch1`, and both
  channel maps still showed the old pair — while the form said `ch0` / `ch4`.
  Only **▶ Run** brought it to 0.9721. Nothing marks the result stale. → RF-336.
- **A detector setup nobody picked was already applied.** The window opened with
  **Setup = BS** (a Becker & Hickl SPC-130 definition: `green` = ch 8,0,3 gated
  to raw micro-time 0–4095; `red` = ch 9,1,2 gated 0–2048). On the HT3 that
  makes "green" a micro-time-truncated `ch0` and **"red" a micro-time-truncated
  `ch1`** — the *other green* detector — and the tool reports
  `green vs red · PCC = 0.992`, a plausible number under the wrong label, while
  the file's actual red detectors (ch4, ch5) are never touched. Nothing in the
  window shows what a window means; the summary line under the combo says only
  "green, red, yellow". → RF-337.
- **Leica PTU scans are unusable here**, the same way they are in Image Tools:
  `Leica_SP5.ptu` reconstructs as **1 frame × 7921 lines × 256 px**
  (`WARNING: no complete frames; salvaging …` on stderr only), the status line
  reads `256×7921 px`, only `ch0` carries photons and every coefficient is
  `n/a`. The colocalization tool has no marker or reading-routine control at
  all. → RF-161 (through `build_clsm_windowed` this time).
- **The channel list offers channels that cannot work.** For `Leica_SP5.ptu` it
  lists `ch0, ch1, ch2, ch4, ch6` — `ch4`/`ch6` are the *frame-marker* channels
  and all four of them hold zero photons. The default pair is simply
  "first, second", i.e. `ch0` vs `ch1`, so the automatic first run is guaranteed
  to produce `Pixels above threshold = 0` and a wall of `n/a`. → RF-338.
- **A gate rectangle is drawn even with gating off.** On first sight of the
  *Intensity scatter* a prominent blue rectangle covers a large part of the
  cloud, although `Gate active` is unticked, the gate region list is empty and
  no `Gate:` rows exist in the table. → RF-339.
- **The "PCC vs intensity" tab is unreadable.** Three profiles share one x axis
  with two different units: the two intensity curves run to 240 while the *vs
  A/B ratio* curve lives on 0.55 … 1.83 and collapses into the left-hand pixel
  column. That third curve is also un-guarded — 13 of its 30 bins report
  |PCC| = 1 from a handful of pixels and 10 bins are empty. → RF-340.
- **The painted ROI overlay is opaque white**, so the moment you start outlining
  a cell on the *Channel A* map you can no longer see the cell (`50_roi_channels`).
  The analysis underneath is correct. → RF-341.
- **Object analysis over-counts badly out of the box.** With the shipped
  defaults (Smoothing 0, Min size 4, Split off) the punctate pair reported
  **130 objects in A and 261 in B** against a truth of 30 and 25, and partner
  fractions 0.331 / 0.180 against 0.667 / 0.800 — the segmentation is counting
  noise clumps, and the *Objects* map shows the >100 specks plainly. Smoothing
  1 px + Min size 9 px + Split touching recovers **29 / 26** objects and
  0.655 / 0.731. → RF-342.
- **The two channel maps are drawn at different magnifications.** In the
  *Channels* tab the Channel A pane is about half the width of the Channel B
  pane, so two 256×256 images are shown at ~2× different scale — in the one view
  whose purpose is comparing them side by side. → RF-343.
- **The headline line evaporates.** `results_text`
  (`PQ_Olympus_MFIS.ht3 · 256×256 px · ch0 vs ch4 · PCC = 0.972`) is the only
  place the file, the size and the analysed pair are stated, it lives in the
  status bar, and it is posted with an 8-second timeout — after that the window
  shows a table of numbers with nothing saying what they belong to.
- Headless limitation: **💾 Export CSV** opens a modal save dialog, so the
  button was exercised through `ColocViewModel.export_csv` rather than the
  dialog; everything else was driven through the widgets.

## UX / UI suggestions

- **Recompute on a channel pick, or mark the result stale.** Dropping a file
  auto-runs and changing the setup auto-runs; changing the channel pair does
  not. Either make it consistent, or grey the coefficient table and title the
  tabs "(stale — press Run)" whenever a setting has changed since the result.
- **Show what a detector window means.** `green — ch 0,1 · mt 0–31250` under the
  combo (and in the Channel A/B combo entries) would have made the
  wrong-setup trap self-evident. Warn when a window's channels are absent from
  the loaded file instead of returning an all-zero image.
- **Keep the run summary.** Put the file / size / channel pair / PCC line in a
  permanent header above the tabs rather than in an 8-second status message; it
  is what the user copies into a figure caption.
- **Report progress from inside the compute.** `compute()` calls its progress
  callback exactly twice (10 % "Loading image…", 90 % "Computing coefficients…"),
  so everything between — the Costes threshold search, 200 randomizations, the
  CCF plane, the object segmentation — is one opaque step. Push a fraction per
  randomization at least; the current wiring already carries it to the status bar.
- **Label the scatter axes.** The *Intensity scatter* plane has no ticks or axis
  titles on either axis, so the gate rectangle cannot be related to the typed
  **A min/A max** values by eye. Same for the *CCF map (2-D)* tab, where the
  reader is expected to judge a Δx/Δy offset off an unlabelled square.
- **Don't autoscale a bounded quantity.** The *van Steensel CCF* y axis reads
  `PCC (x0.001)` with ticks 300 … 900; a correlation coefficient should be
  plotted on its own 0 … 1 scale. (The same pattern was noted for the phasor
  `s` axis in [FLIM pixel maps](/usecases/flim-pixel-maps-mle.md).)
- **Nine tabs do not fit.** At 1500 px the tab bar already clips *PCC vs
  intensity* and hides *Objects* / *Object distances* behind a ► arrow. Group
  them (Maps / Correlation / Objects) or let the bar wrap.
- **Give the object defaults a fighting chance.** Min size 4 px with no
  smoothing counts noise. Default to Smoothing 1 px / Min size 9 px, or report
  the object-size distribution so an over-count is visible.
- **Say how the numbers were made, in the CSV.** The export writes the metric
  dictionary but not `auto_threshold`, `frame`, the background quantile, the
  gate or the ROI — precisely the settings the concept page says a defensible
  report must state.
- **Consider adding it to the Image Tools hub.** Colocalization is the only
  `img_*` imaging plugin that is not reachable from *Spectroscopy → Image Tools*
  (drift, tracking, intensity, N&B, micro-time, phasor and pixel-MLE all are),
  so a user working the imaging pipeline never meets it.

## Bugs filed

- RF-336 — a channel pick does not recompute; the table, maps and status line
  keep the previous pair's result under the new labels.
- RF-337 — a remembered detector setup is applied at open and its windows are
  never shown or checked against the file; "green vs red" on the shipped HT3 is
  really green ∥ vs green ⊥, micro-time-truncated.
- RF-338 — the channel list offers zero-photon and marker routing channels, and
  the default pair is "first, second", so the automatic first run on a Leica
  file can only be empty.
- RF-339 — the scatter gate rectangle is drawn while gating is off.
- RF-340 — *PCC vs intensity* plots two incompatible x units on one axis and
  does not guard the profile bins against tiny pixel counts.
- RF-341 — the painted-ROI overlay is opaque and hides the map being outlined.
- RF-342 — the object-analysis defaults over-count objects 4–10× on a
  realistically noisy punctate image.
- RF-343 — the *Channels* tab renders the two maps at ~2× different scale.
- RF-161 (existing) — Leica PTU scans reconstruct with a bogus geometry; it
  reaches this tool through `build_clsm_windowed` as well.
