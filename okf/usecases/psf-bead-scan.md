---
type: Reference
title: Use case — PSF determination from a bead scan
description: Measure the confocal point-spread function from a z-stack of fluorescent beads — detect beads, fit a 3-D Gaussian, read the lateral and axial FWHM and the axial ratio, and export the per-bead table.
tags: [usecase, imaging, psf, calibration, microscopy]
timestamp: '2026-07-27T00:00:00Z'
---

# Use case: PSF determination from a bead scan

**Goal:** measure the instrument's point-spread function — the lateral and axial
FWHM and the axial ratio — from a z-stack of sub-diffraction beads. This is the
resolution/alignment check a microscope user runs before an imaging session, and
the number that feeds the confocal detection volume behind an FCS measurement
(σ_xy, σ_z → V_eff) and the deconvolution of a FLIM image.

**Data:** a multi-page TIFF bead scan. The repo carries no bead scan, so this run
used a synthetic one written for the purpose (7 Gaussian beads + Poisson noise +
one hot camera pixel, 31 × 160 × 160, ground truth σ_xy = 2.6 px, σ_z = 3.4 px at
50 nm pixel / 100 nm z step → **FWHM_xy = 306.2 nm, FWHM_z = 800.7 nm, axial
ratio 2.62**). A real 100 nm TetraSpeck scan is the user's own file; the second
half of step 10 uses the repo's real `test/data/rics/RICS_EGFPGFP.tif`.

## Steps

1. Open **Imaging Tools** (`Imaging` → the numbered imaging hub) and pick
   **🔭 PSF Determination** at the bottom of the navigation list, below the
   separator (it is not one of the numbered pipeline steps — it needs no detector
   setup and no TTTR file). Standalone: `PsfDeterminationTool`, or headless
   `csc psf-determination fit-stack STACK.tif --csv out.csv`.
2. The panel opens on its **Controls** tab: *Load Stack / Detect*, *Fit Selected
   / Fit All / Export CSV*, a **Bead #** navigator, and two foldable parameter
   boxes (*PSF parameters*, *Detection*).
3. Click **Load Stack** and pick the bead-scan TIFF. The status line beside the
   bead navigator shows the file name; the results box reports
   `Loaded bead_scan.tif: 160×160×31 (x×y×z)`.
4. Set the microscope's geometry in *PSF parameters*: **Pixel (nm)** = 50,
   **Z step (nm)** = 100. These only scale the fitted σ into nm — they do not
   affect the fit. Leave **ROI xy (px)** / **ROI z (sl)** at 15 (the cut-out
   fitted around each bead).
5. In *Detection*, set **Px/frame** to roughly the number of bright pixels a
   frame contains (60 here — it sets the quantile threshold). **Min dist (px)**
   rejects clustered candidates, **Min area (px)** = 2 rejects single hot pixels.
6. Click **Detect**. The bead navigator enables and reports the count; the
   results box says `Detected N bead(s)`.
7. Open the **Stack** tab, drag the slider under the image to the slice where the
   beads are brightest, and look: green squares mark the detected beads on that
   slice, and clicking a bead selects **and immediately fits** it.
8. Click **Fit Selected** (or use the **Bead #** spinner, which fits on change).
   Read the report in the **Fit Results** tab: fitted centre and σ in pixels,
   then `FWHMx / FWHMy / FWHMz` and the `Axial ratio (σz/σxy)` in nm.
9. Check the fit visually in the **x-profile**, **y-profile** and **z-profile**
   tabs — the white points are the data through the fitted centre, the red line
   the Gaussian.
10. Click **Fit All** for the per-bead table, then **Export CSV** to write it
    (index, x/y/z, σ in px, FWHM in nm, axial ratio, success, cost).

## Expected

- The fitted lateral and axial FWHM reproduce the true PSF width, and the axial
  ratio lands at 2–3 for a confocal instrument.
- One row per **bead**, not per bead per slice, so the mean/σ over the exported
  table is the PSF averaged over the field.
- A single hot camera pixel is not reported as a bead.
- The image panel shows the bead that is selected, with its fitted FWHM circle.

## Observed (last run: 2026-07-27)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`) both standalone and through the
Imaging Tools hub; screenshots inspected at every step.

**The physics is right.** The 3-D Gaussian fit recovered the ground truth to
better than a nanometre: σx = 2.60, σy = 2.60, σz = 3.40 px (truth 2.6 / 2.6 /
3.4), **FWHM_xy = 306.1 nm** (truth 306.2), **FWHM_z = 801.5 nm** (truth 800.7),
axial ratio 2.62 (truth 2.62), `Success: True`. Over all 21 fits the spread was
±0.4 nm laterally and ±3 nm axially. The hot pixel column (6000 counts, brighter
than every bead) was correctly rejected by `Min area = 2`, and adding it back
with `Min area = 1` is the documented escape hatch. Everything is fast — load
0.08 s, detect 0.05 s, single fit 0.07 s, *Fit All* 0.25 s for 21 beads, panel
opens in 0.5 s — so no progress indication is needed anywhere.

**The empty-state guidance is good.** Clicking *Detect*, *Fit Selected*, *Fit
All* or *Export CSV* with nothing loaded each raises a specific dialog ("Load a
stack first.", "Click a bead in the image or detect beads first.", "Detect beads
first."), and the results box opens with `Load a stack, then detect or click a
bead.` No dead controls anywhere in the panel.

**What a user actually hits:**

- **The bead count is wrong.** 7 beads in the stack, `Detected 21 bead(s)`.
  Detection scans every 4th slice and appends a candidate on *each* plane where
  the bead is above threshold, so each bead is reported 2–4 times (unevenly: the
  brightest beads cross the most planes). The navigator, the *Fit All* table and
  the exported CSV all carry the duplicates — and averaging the CSV, which is
  the entire point of a bead scan, then weights each bead by its own brightness.
  RF-451.
- **The Stack tab looks empty.** It always opens on slice 0 and never follows the
  selection, so after *Detect* + *Fit Selected* the user sees a black frame with
  a single white dot (the hot pixel) and no markers at all — the green bead
  squares, the red pick marker and the yellow FWHM circle are each drawn only on
  their own slice. Moving the slider to z = 9 by hand makes all of them appear at
  once (screenshot `hub_03_stack_on_bead.png`). Step 7 above is only writable
  because we found that out; a first-time user reasonably concludes detection
  failed. RF-452.
- **The primary output is below the fold.** The *Fit Results* box is clamped to
  ~7 lines inside a ~900 px-tall dock that is otherwise empty grey, so the report
  cuts off after `Amplitude / Offset` — the `--- Physical (nm) ---` block with the
  FWHM values, i.e. the answer, needs scrolling. A 21-row *Fit All* summary shows
  6 rows. RF-454.
- **`--roi-xy` means the opposite of what its help says.** `csc psf-determination
  fit-stack --help` calls it "ROI half-size in x/y (pixels)"; the code halves it
  (`roi_xy // 2`), so `--roi-xy 7` gives a 7×7×… cut-out, not 15×15. The GUI
  tooltip ("Lateral ROI size") and the report line (`ROI size: 15×15×15`) are the
  correct reading; the CLI help and the `api/psf.py` docstrings are not. RF-453.
- **The fit ROI is off-centre in z.** A detected bead's `z` is the *scan plane*,
  not the bead's axial maximum, and the auto-selected bead #0 always comes from
  the lowest plane — here z = 9 for a bead centred at z = 14. The z-profile the
  user judges the fit by is therefore visibly truncated (peak at the 13th of 15
  points, screenshot `tab_4_z_profile.png`), and the yellow FWHM circle is
  anchored to a slice where the bead is dim. The fit still converged in every
  case tried, including a deliberately tight `ROI z = 9`, so this is robustness
  and appearance rather than a wrong number today. RF-455.
- **Contrast is set by the worst pixel.** The image auto-levels to the full data
  range on every refresh, so one 6000-count hot pixel pushes real beads (≈3000)
  into the dark half of the colormap; the histogram handles sit crushed against
  the top of the bar. Any level window the user drags is also discarded on the
  next refresh.
- **A time-series movie loads as a "z-stack" without a murmur.** Loading the real
  `test/data/rics/RICS_EGFPGFP.tif` (a 50-frame RICS *time* series) reports
  `Loaded RICS_EGFPGFP.tif: 300×300×50 (x×y×z)` and *Detect* finds "10 beads",
  ready to report an `FWHMz` in nm computed from a time axis.
- **The README's headless command does not exist.** `psf-determination fit-stack
  STACK.tif` is advertised in the plugin README and in the CLI module docstring;
  no such console script is installed (`[project.scripts]` has only `csc` and
  `chimol-cli`). The working command is `csc psf-determination fit-stack …`, which
  ran correctly. RF-456.
- **No documentation.** Unlike its neighbours in the hub (FRC → guide 51,
  colocalization → guide 38 + concept page, tracking → guide 50), PSF
  determination has no `docs/concepts/` page and no numbered `docs/guides/` entry
  — nothing tells a user what FWHM_z they should expect, or how σ_xy/σ_z feed an
  FCS detection volume.

## UX / UI suggestions

- **Report one row per bead.** Merge candidates that repeat across scan planes
  (they already sit within `Min dist` of each other laterally) and keep the plane
  where the bead is brightest as its `z`. That fixes the count, the navigator,
  the batch table and the CSV in one place — and lets *Fit All* end with the line
  the user actually came for: **mean ± SD of FWHM_xy, FWHM_z and the axial ratio
  over the accepted beads**, with the outliers flagged.
- **Follow the selection in the image.** Selecting a bead (click, `Bead #`
  spinner, or the auto-selection after *Detect*) should move the displayed slice
  to that bead's plane, so the markers and the FWHM circle are on screen where
  they were computed. A "z = 9 / 31" readout beside the slider, and an axis label
  saying *z (slice)* rather than an unlabelled 0…30 timeline, would remove the
  remaining doubt about what the slider does.
- **Do not tile everything into tabs.** Controls, Stack, x/y/z-profile and Fit
  Results are six tabs in one dock stack, so the image, the profiles and the
  numbers can never be seen together — the user clicks *Fit Selected* on the
  Controls tab and nothing visibly happens. Default the layout to image left,
  the three profiles stacked right, results below, and let the results box grow
  with its dock (it is the panel's output, not a caption).
- **Level the display for beads, not for defects.** Auto-level on a high
  percentile (e.g. 99.9 %) instead of the maximum, and keep a user-dragged level
  window across refreshes.
- **Say which axis is which on the profiles.** They are plotted in ROI-local
  indices (`x (pixels)` running 0…14) while the report gives the bead at
  `x = 60`; either label them "ROI x" or plot them in stack coordinates.
- **Sanity-check the stack.** A one-line hint when a loaded stack looks like a
  time series (no axial structure in the detected spots, or TIFF metadata without
  a z-spacing) would stop the RICS-movie case above from producing confident
  nonsense.
- **Close the loop with the rest of ChiSurf.** The fitted σ_xy/σ_z is what an FCS
  detection volume needs; offering "send to FCS" (or simply printing
  V_eff = π^{3/2} w_xy² w_z) would make the panel part of a workflow instead of a
  dead end. The fitted FWHM circle is already available as a `RegionOfInterest`
  (`fit_region()`) but no button exposes it.
- **Document it** — a `docs/concepts/psf.md` (what the PSF is, the Gaussian
  approximation and where it breaks, expected FWHM vs NA/λ, the axial ratio as an
  alignment diagnostic) and a numbered `docs/guides/` walkthrough with the CLI and
  a screenshot, both registered in their indexes.

## Bugs filed

- RF-451 — the same bead is reported once per scan plane (7 beads → 21 rows).
- RF-452 — the image panel never follows the selection, so every overlay is
  invisible after *Detect* / *Fit*.
- RF-453 — `--roi-xy` / `--roi-z` documented as half-size, used as full size.
- RF-454 — the Fit Results box is clamped to ~7 lines, hiding the FWHM output.
- RF-455 — a detected bead's `z` is the scan plane, not its axial centre.
- RF-456 — the advertised `psf-determination` console command does not exist.
