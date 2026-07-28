---
type: Reference
title: Use case — FRC resolution (how fine a detail did this image actually resolve?)
description: Measure the resolution an acquisition achieved by Fourier ring correlation — of a TIFF stack or of a confocal photon stream — by splitting it into two independent halves and reading the frequency at which their correlation falls through the 1/7, ½-bit or 2σ threshold.
tags: [usecase, imaging, resolution, frc, clsm, tiff, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: FRC resolution — the resolution measured from the image itself

**Goal:** answer *"how fine a detail does this image actually support?"* without a
bead, a calibration slide or a model of the point-spread function. The
[PSF from a bead scan](/usecases/psf-bead-scan.md) measures what the *instrument*
can do under ideal conditions; Fourier ring correlation measures what *this*
acquisition achieved — drift, photon budget, sample and all. It is the number
that belongs in a figure caption next to a scale bar, and the natural check after
[drift correction](/usecases/image-drift-correction.md): drift blurs the summed
image and the FRC faithfully reports the blur, so an uncorrected stack measures
the stage rather than the microscope.

The method rests entirely on the **split**. The image is cut into two
statistically independent halves of the same object, the two are Fourier
transformed and correlated ring by ring, and the frequency at which that
correlation falls into the noise is the resolution. Correlating an image with
itself — or with a filtered copy of itself — returns the filter, not the
resolution.

**Data used this run:**

* `test/data/rics/RICS_EGFPGFP.tif` — 2.7 MB TIFF, **50 frames × 300 × 300 px**,
  one channel. A camera-style stack; the even/odd split is the natural one.
* `test/data/clsm/PQ_Olympus_MFIS.ht3` — 68 MB PicoQuant HT3 (Olympus MFD),
  reconstructed by the shared image reader into **40 frames × 256 × 256 px**,
  routing channels `ch0 ch1 ch2 ch4 ch5`. A real cell; `ch2` is empty.
* `test/data/clsm/Leica_SP5.ptu` and `Leica_SP8.ptu` — used only to check what
  happens when the scan geometry cannot be auto-detected (see *Observed*).

**Tool:** *Imaging → FRC Resolution*
(`chisurf/plugins/microscopy/img_frc`, `ImgFrcTool`) — an `AutoForm` over
`frc.view.json` with a **Settings** dock on the left and, on the right, the
headline resolution, the FRC curve against its threshold, the two half images and
the ring-by-ring table. Also reachable as the **Resolution** step of
**Spectroscopy → Image Tools**, after *Drift*. Headless equivalents: the
`img-frc` CLI and the RPC method `img_frc.resolution.compute`.

## Steps

1. Open **Imaging → FRC Resolution** (or the **Resolution** step of *Image
   Tools*). The window opens with an empty **Image** box and the info panel
   reading *"Load a TIFF stack or a photon stream, choose how to split it into
   two independent halves, and press Measure."*
2. **Image** — browse, pick an MMFDB entry, or drop a file on the window. The
   status line immediately reports what was read, e.g.
   `50 frames, 1 channel(s), 300x300 px (image).` for the TIFF and
   `40 frames, 5 channel(s), 256x256 px (tttr).` for the HT3. **Read this line**
   — it is the only place the reconstructed scan geometry is shown.
3. **Split into halves by** — *Even / odd frames* (default) for any stack of ≥ 2
   frames; *First / second half* when consecutive frames are not independent (it
   also exposes bleaching); *Two channels* when the acquisition has one frame but
   two detectors that saw the same structure; *Two files* for two repeated
   acquisitions.
4. **Channel** — pick the brightest, most structured one. The combo is filled
   from the file (`ch0 … ch5` for a photon stream, `ch0` for a one-channel TIFF).
5. **Pixel size [nm]** — optional; `0.00` leaves the answer in pixels. It scales
   the result linearly (6.329 px × 50 nm = 316.5 nm — verified exactly).
6. **Criterion** — *Fixed 1/7* unless you have a reason. On this TIFF the three
   disagree by ~18 %: 6.329 px (1/7), 7.458 px (½-bit), 6.720 px (2σ), so the
   criterion belongs beside any number you quote.
7. Optionally open **Estimator** for the ring width, the smoothing and the TIFF
   axis order. Both of the first two move the answer: ring width 0 / 0.01 / 0.05
   cyc/px → 150 / 50 / 10 rings and 6.329 / 6.214 / 5.205 px; smoothing 1 / 3 /
   25 / 51 rings → 6.808 / 6.329 / 5.967 / 5.205 px.
8. Press **▶ Measure**. It runs off the UI thread; the status bar shows
   `Measuring…` → `Reading image… (10 %)` → the result.
9. Read the headline — `6.329 px`, *"Criterion fixed_1/7, crossing at 0.15799
   1/px (period 6.329 px)"*, *"50 frames, image source, 150 rings"* — and check
   the curve: it must start at 1, decay, and cross the threshold once.
10. Open **Diagnostics → Halves** and confirm both halves show the *same*
    structure. If one is empty or shows something else, the split is wrong and
    the number is meaningless.
11. **Diagnostics → Rings** lists frequency, period, FRC, threshold and the
    Fourier-pixel count per ring.
12. **💾 Export CSV** writes `frequency_1/nm,correlation,threshold,ring_pixels`.

## Expected

- A monotone-ish FRC curve from 1 down into the noise, one crossing, and a
  resolution of a few pixels for a real acquisition.
- The two half images look alike; the second is noisier by construction.
- The reported number changes with the criterion and the smoothing, and scales
  linearly with the pixel size.
- A split that cannot be made is refused with a message naming what to do
  instead.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through
`ImgFrcTool`: file picked, split/channel/criterion/pixel-size/estimator fields
set through the AutoForm bindings, **▶ Measure** and **💾 Export CSV** triggered
from the toolbar, every dock visited and eight screenshots inspected.

**The estimator itself is right, fast and honest.** Every measurement finished in
under 1 s including the file read. The TIFF returned 6.329 px (1/7), the HT3
4.656 px on `ch0` and 4.101 px on the brighter `ch1` — a brighter detector
resolving finer, as it should. The even/odd halves of the HT3 carry 1 682 333 and
1 682 381 photons: a genuinely even split. The pixel-size conversion is exact.
Two copies of the *same* file under a *Two files* split correctly return
correlation 1.0 in every ring and no crossing rather than a fake resolution. Both
impossible splits are refused with the right advice (*"a frame split needs at
least two frames; this source has 1 — use a channel split or a second file"*,
*"split='two_files' needs a second file"*), the CSV is written with a correct
header, and **Export CSV** before any measurement says *"Nothing to export yet"*
instead of writing an empty file. The photon-stream path is the highlight: a
68 MB HT3 becomes a recognisable cell in ~1 s and its two halves sit side by side
under *Diagnostics*.

What surrounds that estimator is weaker.

- **A setting is displayed that is not the one used.** With an HT3 loaded, the
  **Second channel** combo shows `ch0` while the model holds `""`; a *Two
  channels* run then correlates `ch0` with `ch1` (3.799 px — identical to
  `analyse(channel=0, channel_2=1)`), whereas the displayed pair `ch0`/`ch0` is
  an explicit error in the same code. Nothing in the headline, the status line or
  the CSV records which pair was actually correlated. Selecting the *last*
  channel with the same untouched combo fails with *"channel 5 is out of range;
  the source has 5"* — an index-vs-name message naming a channel that does exist
  in the list. **RF-664.**
- **An empty detector is reported as a possible triumph.** `ch2` of the HT3 has
  zero photons. The panel says *"No crossing … Either the two halves agree
  everywhere — the image is resolved beyond what this sampling can show — or the
  split did not produce independent halves."* Neither is true, and the FRC curve
  is drawn as a solid line at exactly 0 because the all-NaN correlation is
  `nan_to_num`'d before plotting — an undefined correlation rendered as a
  measured one. **RF-665.**
- **The two halves are drawn at different magnifications** at the window sizes a
  user actually works in: the sibling docks measure 269 px and 432 px wide at a
  1700 px window, so the same 300 × 300 arrays appear ~2.2× apart. That defeats
  the panel's own stated purpose ("both should show the same structure"). At the
  minimum 900 × 600 they are equal. **RF-666.**
- **The frequency axis never says what it is in.** The label is the static
  *"spatial frequency (1/nm or 1/px)"* although the result knows which, and the
  plot backend appends a `(x0.001)` multiplier that is clipped at 1500 px width
  and gone entirely at the tool's own minimum size, where the axis reads
  *"atial frequency (1/n"* over ticks `0 … 5`. **RF-667.**
- **Measure is never disabled.** Three clicks started three concurrent
  `compute()` calls on the same view model (peak concurrency 3, measured), each
  writing `_result` and `_status`. **RF-668.**
- **The GUI does not take the RPC path its own docstring claims.** A spy client
  passed to `FrcViewModel` recorded zero calls: `compute()` calls `core.analyse`
  in-process. **RF-669.**
- **A mis-reconstructed scan is measured without comment.** `Leica_SP8.ptu` is
  auto-detected as a **14 × 512 px** single frame (the reader logs
  *"no complete frames; salvaging 1 frame(s) with 14 line(s)"* to the console
  only) and a two-channel split on it returns a confident **33.27 px**;
  `Leica_SP5.ptu` becomes 7921 × 256. The status line shows the odd geometry but
  nothing flags it, and the panel offers no scan-marker settings with which to
  fix it. This is the already-filed **RF-161** reaching a sixth Image Tools step.

### Screenshots inspected

`01_empty` (opening state), `03_tiff_measured` (TIFF, 6.329 px),
`05_pixel_size_nm` (316.5 nm), `10_wide_window` (1900 px — the half-size
disparity), `12_ht3_measured` (photon stream, the cell), `21_empty_channel`
(the flat zero curve on an empty detector), `30_SP8_channels` (the salvaged
14 × 512 scan measured as 33.27 px), `40_min_size` (900 × 600 — clipped axis).

## UX / UI suggestions

- **Say the result is stale.** Changing the criterion, the split or a channel
  leaves the previous headline and curve in place with no hint that they were
  computed under different settings. Grey the result, or badge it *"settings
  changed — press Measure"*, when a bound field changes after a run.
- **Record what was measured in the result.** The headline gives frames, source
  kind and ring count but not the split or the channel(s). Add
  *"even/odd split, channel ch0"* — it is what makes an exported number
  quotable, and it would have made RF-664 visible to the user.
- **Show only the controls the split uses.** *Second channel* and *Second file*
  are always enabled; they apply to exactly one split each. Disable or hide them
  otherwise, and give *Second channel* a real default rather than an implicit
  neighbour.
- **The Settings dock is too wide.** It takes ~38 % of the window at every size
  tested for a seven-row form, leaving several hundred pixels of blank column
  while the FRC plot is squeezed to ~150 px at the minimum size. Give it a
  sensible initial width and let the result area have the rest.
- **Offer the three criteria at once.** They differ by ~18 % on the same curve
  and the user is asked to choose before seeing any of them. A one-line
  "1/7: 6.33 px · ½-bit: 7.46 px · 2σ: 6.72 px" under the headline would settle
  the choice with no extra compute — all three read off the same correlation.
- **Progress is 10 % then done.** The callback fires once at *"Reading image…"*
  and once at completion. On a large photon stream the read is most of the wait;
  report it per frame, or at least switch the message to *"Correlating…"*.
- **Duplicate dock titles.** Each result dock shows its name twice — once in the
  tab bar and once as a bold caption below it (*Half 1*, *Half 2*, *Rings*).
- **Warn about a salvaged scan geometry in the panel**, not on the console — a
  14 × 512 "image" should say so where the user is looking.

## Bugs filed

- RF-664 — the *Second channel* combo shows a channel that is not the one
  correlated, and the out-of-range error names a channel that exists.
- RF-665 — an empty detector channel is reported as *"no crossing"* with a
  diagnosis that cannot apply, and its undefined FRC is plotted as a flat zero.
- RF-666 — the two half images are rendered at ~2.2× different scale.
- RF-667 — the frequency axis never states its unit and loses its `×10⁻³`
  multiplier at the tool's own minimum window size.
- RF-668 — **Measure** stays enabled during a run; concurrent workers write the
  same view model.
- RF-669 — the GUI computes in-process while its docstring claims the plugin
  client / RPC path.
- RF-161 (already open) — re-observed here: a Leica PTU whose scan markers are
  not auto-detected is measured as a 14 × 512 image and returns 33.27 px.
