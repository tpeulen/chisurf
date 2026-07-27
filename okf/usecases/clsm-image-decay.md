---
type: Reference
title: Use case — CLSM image and pixel-selected decay (Imaging)
description: Load a CLSM TTTR file into CLSM-Draw, auto-detect the scan markers, build a CLSM image and an intensity representation, brush a pixel selection, read its fluorescence decay, save it as an ROI and export the decay to ChiSurf.
tags: [usecase, imaging, clsm, tttr, lifetime, gui]
timestamp: '2026-07-25T00:00:00Z'
---

# Use case: CLSM image → pixel selection → decay

**Goal:** the standard FLIM/CLSM task — a user has a confocal scan recorded as
raw TTTR photons and wants (a) an image to look at, (b) a region of that image
they choose by eye, and (c) the fluorescence decay of exactly those pixels, as a
ChiSurf dataset they can then fit with a lifetime model.

**Data:** `test/data/clsm/Leica_SP5.ptu` — 32 MB Leica SP5 PTU, 6 714 549
photons, 230 frames × 256 lines × 256 pixels, micro-time resolution 0.025 ns
(1999 micro-time channels ≈ 50 ns window). The scene is a single bright cell on a
dark background. (`Leica_SP8.ptu` and `PQ_Olympus_MFIS.ht3` sit next to it for
the other two presets.)

**Tool:** CLSM-Draw (`chisurf/plugins/microscopy/clsm`, display name
*Imaging:CLSM-Draw*, `CLSMPixelSelect`), also reachable through the Imaging-Tools
aggregator, as `clsm.*` RPC methods, and as a `clsm` CLI.

## Steps

1. Open **Imaging → CLSM-Draw**. The tool is one dock area with seven panels —
   *File*, *Acquisition*, *Brush & Decay*, *Image*, *ROIs*, *Decay*, *FRC*.
2. On the **File** panel choose **Setup** = `Leica SP5`. The preset fills the
   *Acquisition* panel (TTTR type `PTU`, routine `SP5`, frame markers `4,6`,
   line start `1`, line stop `2`, event marker `1`).
3. Type or browse the file into **File** (`Leica_SP5.ptu`). The header is read
   immediately and the markers are re-detected from it — frame marker becomes
   `4` and **Pixel/line** becomes `256` (it was `0`).
4. Set **Channels** to `0,1` (comma separated routing channels; `0` alone is the
   shipped default and gives a dimmer image).
5. Click **+** next to **CLSM**. This builds the `CLSMImage` and the combo fills
   with `Leica_SP5_ch(0,1)`.
6. Leave **Image type** = `Intensity` on the *Brush & Decay* panel and click
   **+** next to **Image**. The combo fills with
   `Leica_SP5_ch(0,1)_Intensity` and the *Image* panel shows the frame-summed
   image with a `magma` colormap and a level/histogram bar.
7. Switch to the **Image** panel and brush over the cell. The brush is a square
   Gaussian kernel (*Brush size* 7, *Brush width* 3.0); the **select** /
   **deselect** radio pair chooses paint or erase, and **Live update**
   recomputes the decay on every stroke.
8. Switch to the **Decay** panel and read the decay of the painted pixels —
   log-y counts against `time (ns)`.
9. On the **ROIs** panel type a name (e.g. `bright`) and click **+** to keep the
   selection. The row shows `bright — 6579 px, 398.2 ph/px`. **Remove** /
   **Save** / **Load** sit at the bottom of the panel (`.json` keeps the region,
   `.tif`/`.npy` rasterise it).
10. Back on **File**, click **Add decay → ChiSurf**. The decay is added to the
    dataset list as a TCSPC curve and can be fitted with a `Lifetime` model (see
    [TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md)).
11. Optional: measure the resolution of the same image in the Image-Tools
    **Resolution** panel (`img_frc`) — it no longer lives here.
12. Optional headless equivalent:
    `clsm decay <file> --setup 'Leica SP5' --channels 0,1 --threshold 0.5`,
    plus `clsm info|representation|setups|contract`.

## Expected

- Step 3 loads in ~0.2 s and fills Pixel/line automatically; step 5 builds the
  CLSM image in ~0.15 s; step 6 computes the representation in ~0.4 s.
- The intensity image is 256×256, max 750 counts/pixel, 3 486 614 counts total,
  and shows a recognisable cell.
- A selection of the brightest 10 % of pixels (6579 px, ≥ 62 counts) yields a
  decay of 2 619 451 photons over 2000 channels, 0 … 49.975 ns, recomputed in
  ~0.04 s — a clean single-exponential-looking decay rising at ~2.7 ns over a
  flat ~45-count background, with the next-pulse rise visible at ~48.5 ns.
- The **Frames** mode (`sum` / `mean` / `frame`) and **Frame** index should
  control *both* the displayed image and the decay; **Coarsen** should re-bin
  the plotted decay; **Min #Ph** should blank out pixels with too few photons in
  the *Mean micro time* representation.
- `Mean micro time` should be an image of mean arrival times, i.e. numbers of
  order the fluorescence lifetime (here ≈ 7–8 ns).

## Observed (last run: 2026-07-25)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) against the real
`CLSMPixelSelect` widget: the Setup combo, the File line edit, the Channels
field, the **+**/**−** tool buttons of the CLSM and Image selectors, the
image-type / frames / coarsen combos, the *Min #Ph* and *Frame* spin boxes, the
ROI name field and its **+**, and the **Add decay → ChiSurf** / **Clear
selection** buttons — all clicked with `QTest`, with a screenshot taken and
inspected at every step and on every one of the seven panels. The CLI was
exercised in the same run.

**The core path works and the output is right.** Marker auto-detection, the
CLSM build, the intensity image, the pixel selection, the decay extraction, ROI
save/re-apply, and the export to a ChiSurf dataset all did what they promise, in
well under a second each. The intensity image is a clean, recognisable cell; the
decay is properly labelled (`time (ns)` / `counts`), plotted log-y, and
physically sensible; the ROI row's `6579 px, 398.2 ph/px` is exactly the pair of
numbers a user needs. The whole workflow never raised a dialog or a traceback,
and the CLI reproduced it (`decay: 2000 bins, 2158228 photons`).

**But the `Mean micro time` representation is quantitatively wrong.** The
displayed image runs 0 … 57 648 with a mean of 9413 and no unit, where the
correct answer is ≈ 8 ns. Two independent causes:

- `imaging.representation` calls
  `clsm_image.get_mean_micro_time(tttr, n_ph_min, False)`, but the installed
  tttrlib (0.27.0) signature is
  `get_mean_micro_time(tttr_data, microtime_resolution=-1.0,
  minimum_number_of_photons=2, stack_frames=False, correct_irf_offset=False)`.
  So **`n_ph_min` is passed as the micro-time resolution** — it multiplies every
  pixel value (Min #Ph 1 → max 57 648, 5 → 288 240, 50 → 2 882 406, the image
  itself unchanged) — and `minimum_number_of_photons` receives `False` = 0, so
  the low-photon discrimination the control exists for never happens and the
  background is pure noise. Every other call site in the tree
  (`core/fluorescence/imaging/pixel_maps.py:327`,
  `plugins/microscopy/img_pixel_micro_time/core.py:49`) already uses the correct
  4-argument form (RF-030).
- The per-frame means are then reduced with `reduce_frames`, whose default mode
  is `sum` — so the panel displays the **sum over 230 frames of per-frame mean
  micro times**. `mean` is no better (0 -photon pixels dilute it to 1.02 ns);
  tttrlib's photon-weighted `stack_frames=True` gives 8.076 ns against a true
  global mean of 7.037 ns (RF-031).

**Three controls do nothing.** `refresh_current_image` — whose docstring says
"after a frame-mode change" — has **zero callers** in the tree. Switching
**Frames** from `sum` to `frame` and setting **Frame** = 150 leaves the
displayed image byte-identical (mean 53.202 before and after), while
`recompute_decay` *does* honour them: the decay drops from 2 619 451 to 11 900
photons. The image and the decay then describe different data with nothing on
screen saying so. **Coarsen** behaves the same way — picking `8` leaves the
plotted decay at its 2000 channels until some later recompute re-bins it to 250
(RF-032).

**The Frame spin box is unbounded** (0 … 2 147 483 647 for a 230-frame image);
out of range it raises a bare `IndexError` from `reduce_frames`, reachable today
through the documented CLI: `clsm representation … --frame-mode frame
--frame-idx 5000` exits 1 with `index 5000 is out of bounds for axis 0 with size
230` and no message naming the real frame count (RF-033).

**Removing a CLSM image leaves its debris on screen.** Clicking **−** next to
CLSM empties that combo but the *Image* combo still lists
`Leica_SP5_ch(0,1)_Intensity`, the image is still displayed, and
`recompute_decay` silently returns `None` — brushing from then on updates
nothing, with no message (RF-034).

**The exported curve is named after the wrong thing.** After saving an ROI
called `bright`, **Add decay → ChiSurf** exports
`Leica_SP5_ch(0,1)_ROI(Leica_SP5_ch(0,1)_Intensity)` — the text inside `ROI(…)`
is the *representation* name, not the ROI name the user typed, and the same
string becomes the decay-plot legend entry (RF-035).

Also seen: `PDA TRACE: core_data.add_dataset …` info lines are logged on the
export, and pyqtgraph prints `RuntimeError: wrapped C/C++ object of type
QComboBox has been deleted` from a `ViewBox` destructor whenever the plot panels
are rebuilt (harmless, but it lands in the console on ordinary clicks).

## UX / UI suggestions

- **All seven panels open stacked as tabs in one dock, so the image and the
  decay can never be seen together** — which defeats the tool's whole premise
  ("brush over pixels; the decay updates live"). Whatever the *Live update*
  checkbox does, the user is on the *Image* tab and cannot see it. Ship a default
  layout that puts *Image* and *Decay* side by side with the settings panels
  docked left, rather than one tab bar of seven.
- **The panels waste the window.** *File* is 6 rows and *Acquisition* is 7 rows,
  each stretched over ~900 px of empty grey at 1500×950; the ROI panel's
  *Remove / Save / Load* buttons are pinned to the bottom edge, ~850 px away
  from the list they act on.
- **The `Brush & Decay` tab renders as "Brush &#95;Decay"** — the `&` in the
  panel title is consumed as a Qt mnemonic. Escape it (`&&`) or rename the panel.
- **Nothing on the image says what is being shown.** No title, no unit, no frame
  count, no pixel size or scale bar — `Intensity` (counts) and `Mean micro time`
  (should be ns) are drawn with the same bare colour bar, and the bar's right
  edge is clipped by the panel border. The image name only exists in the *File*
  panel's combo, one tab away.
- **The selection is painted opaque white**, hiding the very structure the user
  is trying to trace. A semi-transparent tint or an outline would let them see
  what they are including.
- ~~**The FRC panel gives no resolution.**~~ **Fixed** by moving it out: the
  panel drew the correlation against a bare ring index with no threshold line,
  no crossing readout and no length unit, so the one number FRC exists to
  produce could not be read off it. Resolution estimation is now the Image-Tools
  **Resolution** panel (`img_frc`), which reports the crossing in nm against a
  named criterion; the CLSM panel, its `clsm.frc.compute` method and the
  `clsm frc` command are gone.
- **Every decay series is drawn in the same yellow.** The saved curves and
  *Current selection* differ only by line width, and the legend swatches are
  identical — with several ROI decays the plot is unreadable. Cycle colours per
  series.
- **`Min #Ph`, `Coarsen`, `Frames`, `Frame` are on the *Brush & Decay* panel but
  act on the *Image*** — and `Image type` only takes effect on the next **+**,
  which is not discoverable. Group the representation settings with the **+**
  that consumes them, or make them live.
- **Changing `Channels` after a CLSM is built is silently ignored** (by design —
  you press **+** again), but nothing says so; the only clue is the channel list
  baked into the CLSM name.
- **`Setup` lists `PTU` as its first preset**, which is a file format, not an
  instrument, and it is the default — so a user who does not change it gets the
  generic marker set. Name it e.g. `Generic PTU`.
- **The CLI mislabels its output**: `clsm representation --image-type 'Mean micro
  time'` prints `total_intensity=616871573` for a stack of micro-time means.
- **No progress indication anywhere.** Everything here is fast on this 32 MB
  file, but the same clicks on a multi-GB acquisition (`+` on CLSM, `+` on
  Image, a brush stroke with *Live update* on) block the UI with no cursor
  change, no busy indicator and no cancel.
- **`Pixel/line = 0` means "same as the number of lines"** — that is in the
  tooltip, but the field shows a bare `0` which reads as "unset/broken" until
  the file is loaded and it is filled in.

## Bugs filed

- RF-030 — `imaging.representation` passes `n_ph_min` into tttrlib's
  `microtime_resolution` parameter: *Min #Ph* silently scales the mean-micro-time
  image instead of discriminating low-photon pixels.
- RF-031 — the mean-micro-time representation is reduced across frames with
  `sum`/`mean` instead of tttrlib's photon-weighted stacking, so the displayed
  image is ~230× the mean and carries no unit.
- RF-032 — `refresh_current_image` has no callers: the *Frames*, *Frame* and
  *Coarsen* controls leave the image (and the plotted decay) stale while
  `recompute_decay` already honours them.
- RF-033 — the *Frame* spin box is unbounded and an out-of-range frame index
  raises a bare `IndexError` from `reduce_frames` (reachable from the CLI).
- RF-034 — removing a CLSM image leaves its representations selectable and its
  image displayed, and `recompute_decay` then silently returns `None`.
- RF-035 — the exported/saved decay is named `…_ROI(<representation name>)`
  instead of using the ROI name the user gave.
