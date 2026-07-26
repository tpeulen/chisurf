---
type: Reference
title: Use case — FLIM pixel maps and pixel-wise MLE (Image Tools pipeline)
description: Walk the numbered Image Tools pipeline on a confocal FLIM measurement — detector setup, browse, intensity, number & brightness, mean micro-time, IRF & background, phasor, pixel-wise MLE — and read the fitted lifetime map.
tags: [usecase, imaging, flim, clsm, phasor, mle, lifetime, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: FLIM pixel maps → phasor → pixel-wise MLE

**Goal:** the FLIM analysis task that follows
[CLSM image → pixel selection → decay](/usecases/clsm-image-decay.md). Instead of
one decay from a hand-brushed region, the user wants **per-pixel maps** of the
whole scan: intensity and count rate, number & brightness, mean micro-time,
phasor `(g, s)`, and finally a **fitted lifetime image** — every pixel fitted by
Poisson MLE against a measured IRF — all from one detector definition and one
photon file, with the results collected in one imaging HDF5 that ndxplorer and
CLSM-Draw can re-open.

**Data:** `test/data/clsm/PQ_Olympus_MFIS.ht3` — 68 MB PicoQuant HydraHarp HT3
from an Olympus MFD microscope (Seidel lab), 15 604 430 photons,
**40 frames × 256 lines × 256 pixels**, 32 768 micro-time channels at 1 ps
(31.25 ns period, 32 MHz). Routing channels 0 (3 881 967) and 1 (9 419 944) are
the parallel/perpendicular *green* detectors; 4 (759 340) and 5 (1 532 933) the
*red* pair. The scene is one bright cell nucleus with a dim cytoplasmic halo.
**IRF:** `imaging/pq/ht3/crn_clv_mirror.ht3` from the external `tttr-data`
collection — a mirror (scatter) scan recorded with the same settings (1 ps,
31.25 ns period, same channels). No matched IRF for this image ships inside the
repo. *Copy both files to a scratch folder before driving this workflow* — every
step writes its output next to the input data without asking.

**Tool:** Image Tools (`chisurf/plugins/microscopy/imaging_tools`, display name
*Spectroscopy:Image Tools*, `ImagingToolsTool`) — a `NavigationPanelTool` that
embeds eleven imaging plugins as steps: **Setup**, **Plan**, **Browser**,
**Drift**, then the numbered pipeline **1. Intensity**, **2. Number &
Brightness**, **3. Mean Micro-Time**, **4. IRF & BG**, **5. Phasor-FLIM**,
**6. Pixel-wise MLE**, and below a separator **CLSM Draw**, **Molecule-wise
MLE**, **PSF Determination**. The sub-tools (`img_pixel_*`, `img_calibration`,
`sm_image_mle`) are all `menu_hidden` — this window is the way in. The window
opens on **Browser**, not on **Setup**.

## Steps

1. Open **Spectroscopy → Image Tools**. Each numbered step auto-runs when it is
   navigated to and has a source but no result yet, so the walk below is mostly
   "click the next step and look".
2. Click **Setup** (the shared detector definition; every step pulls it over
   RPC). The only shipped setup is **BS** — a Becker & Hickl SPC-130 definition
   with detectors `green` (channels 8,0,3), `red` (9,1,2) and `yellow` (9,1,2).
   For this file:
   - set **File Type** = `HT3` in *TTTR Reading routine* — this also decides
     which files the Browser will list (see RF-160);
   - delete the `yellow` row (🗑️);
   - set `green` **Channels** = `0, 1` and **Micro Time Ranges** = `0:31250`;
   - set `red` **Channels** = `4, 5`, same range.
   *Leave the micro-time range at the full period* — it is transferred verbatim
   to the fit steps, in raw channels (see RF-157).
3. Click **Browser** and **📂 Open** the scratch folder (or drop the folder on
   the file list). The list shows the two `.ht3` files with their sizes; click
   `PQ_Olympus_MFIS.ht3`. A per-detector intensity mosaic appears within a
   second — two tiles labelled `green | mt: 0-31250 | ch: 0,1` and
   `red | mt: 0-31250 | ch: 4` (the second label is clipped at the tile edge),
   the cell clearly visible in both.
4. Click **Next ▶ Intensity** in the toolbar. The selected file becomes the
   pipeline *source* and the tool jumps to step 1.
5. **1. Intensity** computes in ~2 s and opens on its *Controls* tab, which
   shows only the file path and `PQ_Olympus_MFIS.ht3: 256x256 px. Windows:
   green, red.` The maps live behind the *Intensity*, *Count rate (kHz)* and
   *Frames (movie)* tabs — click **Intensity** to see the frame-summed image
   (a `magma` map with a level/histogram bar and a `channel` combo switching
   green/red). Columns produced: `Ng-p-all`, `Ng-s-all`, `Ng-all`,
   `green Count Rate (KHz)`, `S prompt green (kHz)`, the same five for red, and
   `Number of Photons`.
6. Click **💾 Create imaging HDF5** to start the standard imaging HDF5 the later
   steps enrich. It asks for a path with a modal save dialog (no default
   offered, although `<stem>.imaging.h5` is what the auto-persist-on-close uses).
7. **2. Number & Brightness** (~2 s) adds `N`, `B` and `epsilon` per detector;
   tabs *Brightness (B)*, *Number (N)*, *Brightness ε*. **➕ Add NB to HDF5**
   merges them into the file from step 6.
8. **3. Mean Micro-Time** (~2 s) adds `mean_micro_time (green|red)`. The map
   auto-scales to the full 0–31 ns period, so the cell (2–4 ns) reads as a dark
   silhouette against a bright background of near-empty pixels.
9. **4. IRF & BG** — pick **Detector** = `green`, then drop
   `crn_clv_mirror.ht3` on **IRF files (this detector)**. Building the decay and
   IRF histograms takes ~9 s with the status bar still reading *Ready*. The
   *Decay & IRF* tab then shows the semilog data decay (cyan) with IRF VV/VH
   (magenta/orange) over a `micro-time channel` axis, a draggable blue
   convolution region, a green IRF region and a grey background region. Adjust
   the ranges and background if wanted and click **Apply →** — the per-detector
   IRF, background, shift and convolution range are transferred to Phasor and
   MLE. (Set the IRF for *every* detector you intend to fit; `red` stays empty
   here and gets `conv 0:0`.)
10. **5. Phasor-FLIM** (~3 s) adds `g`, `s` and `n_photons` per detector and
    offers *Phasor g*, *Phasor s*, their movies and a **Phasor plot** — a 2-D
    histogram of the pixel cloud with the universal semicircle drawn over it.
    For this image the cloud sits around `g ≈ 0.85`, hugging the semicircle.
11. **6. Pixel-wise MLE** — the fit itself. The *Analysis* tab holds the CLSM
    file list, the IRF file list (both pre-filled from the pipeline), the
    parallel/perpendicular channel fields, the fit window, **Micro-time
    binning**, **Min photons**, an optional **Region** (a CLSM-Draw `.json`, a
    Cellpose `_seg.npy`, a label image or a mask), the **Fit model** combo
    (fit23 single lifetime + anisotropy, fit24 bi-exponential, fit25 lifetime
    selection) with its per-parameter value/fix rows, and folded *IRF
    preparation*, *Fit flags*, *Background* and *Performance* boxes. Before
    pressing **▶ Run**, three settings must be corrected by hand:
    - **Micro-time binning** — the default `1` makes the fit allocate
      `n_frames × n_lines × n_pixel × n_micro_channels` bytes (86 GB here) and
      the process is killed (RF-155). `128` (0.7 GB) is workable for a 1 ps,
      32 768-channel HydraHarp file.
    - **Fit start / Fit stop** — these are on the *binned* axis, while the
      values inherited from Setup / step 4 are raw channels (RF-157). With
      binning 128 the window is `0 … 244`.
    - **Parallel / Perpendicular channels** — the pipeline fills them by channel
      parity across *all* detectors (`∥ = 0,4`, `⊥ = 1,5`), which fits green and
      red photons together (RF-159). For the green pair type `0` and `1`.
12. Press **▶ Run**. The fit takes ~20 s (2 621 440 pixel rows, 40 frames) and
    then ~6 s more to write `<stem>_pixel_mle.csv` (75 MB) next to the data.
    The *Lifetime map* tab then shows the τ map with a `channel` combo naming
    the analysed file and a frame slider.

## Expected

- Every numbered step produces a 256 × 256 map per detector window, in seconds,
  and merges its columns into one imaging HDF5.
- The phasor cloud lies on/near the universal semicircle.
- The lifetime map is a **picture of the cell**: most pixels inside the cell
  fitted, τ ≈ 2–3 ns, background pixels unfitted.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) end to end;
screenshots inspected at every step and every tab.

- **Steps 1–3, 5 are fast and correct.** Intensity 2.1 s, N&B 2.4 s, mean
  micro-time 2.2 s, phasor 2.8 s on 15.6 M photons; the intensity map is a clean
  picture of the cell, the phasor plot shows the expected cloud on the
  semicircle. The Browser mosaic renders in <1 s and is cached.
- **The lifetime map is empty.** The MLE fits every *frame* separately — there
  is no frame-stacking control anywhere in the GUI although the Qt-free core
  has one — so with 40 frames each pixel holds ~1 photon per frame and only
  **277 of 2 621 440 rows** pass `Min photons = 50`. The map shows a handful of
  scattered dots (`43_mle_after_select.png`). Calling the same core with
  `stack_frames=True` fits **46 150 of 65 536 pixels in 1.6 s**, median
  τ = 2.42 ns — the picture the user expects. → RF-156.
- **The first Run kills ChiSurf.** With the defaults the pipeline hands the MLE
  (binning `1`, window `0:31250` from the detector setup) the fast extraction
  allocates a `(40, 256, 256, 32768)` uint8 array *per polarisation* = 85.9 GB
  on a 17 GB machine; the process was SIGKILLed (exit 137) on both attempts,
  losing the whole session. → RF-155.
- **A failed fit says nothing at all.** With a fit window that is invalid on the
  binned axis (start 1500 with binning 128 — exactly what step 4's convolution
  range transfers), Run returns in 0.8 s, no results appear and the info panel
  reverts to its "Add confocal (CLSM) TTTR image file(s)…" instruction. The
  underlying `ValueError: empty micro-time window: start=1500, stop=256` is
  written to `status_text` and then wiped by the same method. → RF-158, RF-157.
- **The Browser can look empty.** With the shipped `BS` setup (File Type
  `SPC-130`) the scratch folder full of `.ht3` files lists *nothing* —
  "0 image(s) in data" — because the setup's file type filters the list.
  → RF-160.
- **Leica PTU scans are mangled here.** Image Tools has no reading-routine or
  marker control and relies on tttrlib's header auto-detection. For the two
  Leica files that ship in `test/data/clsm` that detection fails:
  `Leica_SP8.ptu` → 1 frame × 14 lines × 512 px (correct with the SP8 routine:
  93 × 512 × 512) and `Leica_SP5.ptu` → 1 × 7921 × 256 (CLSM-Draw's preset:
  230 × 256 × 256). The Browser mosaic is a 14-line stripe
  (`11_browser_image.png`) and every downstream map inherits the wrong geometry;
  the only signal is a console warning. → RF-161.
- Constructing `tttrlib.CLSMImage` on `Leica_SP8.ptu` in a bare interpreter
  **segfaults** (exit 139) at the same "no complete frames" point; the identical
  call after `import chisurf` only warns. → RF-162 (belongs to the TTTR library).
- Headless limitation: **💾 Create imaging HDF5** opens a modal save dialog, so
  the HDF5-writing half of steps 6–10 could not be driven offscreen; the maps,
  the CSV export and every fit were exercised.

## UX / UI suggestions

- **Show the result, not the Controls tab.** Every numbered step opens on
  *Controls* — a small info box in an otherwise empty window — with the maps
  behind tabs. After a Run nothing visibly changes. Open on (or switch to) the
  primary map tab once a result exists.
- **Say something while working.** The 9 s IRF/decay build, the 20 s fit and the
  6 s CSV write all happen with the status bar reading *Ready*; the model's
  `status_text` reaches the panel's info box only for the MLE. Route step
  progress into the shared status bar, and end with a summary ("46 150 pixels
  fitted, median τ 2.42 ns, written to …_pixel_mle.csv").
- **Guard the binning/memory choice.** The MLE could estimate
  `n_frames × n_lines × n_pixel × n_channels/binning` before allocating and
  either propose a binning or refuse with a readable message.
- **Scale FLIM maps robustly.** The mean-micro-time map auto-scales to the full
  laser period, so the informative 2–4 ns contrast is invisible. Default to a
  percentile (1–99 %) scale, or mask pixels below the min-photon threshold.
- **Phasor axes in one unit.** The phasor plot's y axis is labelled
  `s (x0.001)` running 0–600 while x is `g` 0–1; plot `s` in the same units.
- **Offer a default HDF5 path.** `Create imaging HDF5` asks for a path although
  `_default_hdf5_path()` (`<stem>.imaging.h5`) already exists for the
  auto-persist path; default to it and keep "Save as…" for the exception.
- **Say where results went.** `<stem>_pixel_mle.csv` (75 MB) is written next to
  the source data without a prompt and the path is never shown in the UI.
- **The navigation rail clips its labels.** At the default 210 px width
  "2. Number & Brightn…" and "Molecule-wise MLE" are cut and a horizontal
  scrollbar appears under the list instead of eliding or wrapping. The selected
  row's label is invisible on this palette (already RF-075 / RF-109).
- **Label the second mosaic tile fully.** The Browser draws each tile's label at
  the tile origin, so the `red` tile's `ch: 4,5` is clipped to `ch: 4` at the
  panel edge.

## Bugs filed

- RF-155 — pixel-wise MLE at the default micro-time binning allocates ~86 GB and
  the process is killed.
- RF-156 — no frame stacking in the GUI, so multi-frame FLIM stacks fit almost
  no pixels.
- RF-157 — fit window is on the binned axis while Setup / IRF & BG transfer raw
  micro-time channels (and the IRF is then built empty).
- RF-158 — a per-file fit error is written to the status line and immediately
  wiped, so a failed run is silent.
- RF-159 — the ∥/⊥ split by channel parity merges all detectors, fitting green
  and red photons as one polarisation pair.
- RF-160 — the Browser's file list is silently filtered by the setup's file
  type; the shipped default hides every PTU/HT3.
- RF-161 — Image Tools has no CLSM reading-routine control, so Leica PTU scans
  are analysed with a wrong (auto-detected) image geometry.
- RF-162 — `tttrlib.CLSMImage` segfaults on `Leica_SP8.ptu` in a bare
  interpreter (library-side; needs triage in the TTTR library).
