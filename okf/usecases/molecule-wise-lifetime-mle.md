---
type: Reference
title: Use case — molecule-wise MLE (a lifetime per segmented object)
description: Segment individual emitters from a confocal TTTR image and fit each one's fluorescence lifetime and anisotropy by Poisson MLE (Fit23), then browse the per-molecule decays and export the table.
tags: [usecase, imaging, clsm, lifetime, mle, fit23, segmentation, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: molecule-wise MLE — one lifetime per segmented object

**Goal:** the third way to get lifetimes out of a confocal image. A
[decay from a brushed region](/usecases/clsm-image-decay.md) gives one number for
a hand-drawn area, and [pixel-wise MLE](/usecases/flim-pixel-maps-mle.md) gives a
number for every pixel — neither gives a number *per object*. This tool segments
the intensity image into discrete objects (single molecules, beads, vesicles,
nuclei), pools each object's photons into a polarisation-resolved VV/VH
micro-time histogram, and fits **one** `Fit23` single-lifetime Poisson MLE per
object: τ, the scatter fraction γ, the rotational correlation time ρ, plus the
usual `regionprops` shape columns. The output is a table with one row per
molecule — the input to a lifetime histogram over a population, not to a map.

**Data:** `test/data/clsm/PQ_Olympus_MFIS.ht3` — 68 MB PicoQuant HT3 (Olympus
MFD), 15 604 430 photons, 40 frames × 256 × 256, **31 250 micro-time channels**
at 1 ps (31.25 ns period). Routing channels `0` / `1` are the parallel /
perpendicular green detectors. **IRF:** `imaging/pq/ht3/crn_clv_mirror.ht3` from
the external `tttr-data` collection (a mirror scan at the same settings); the
repo ships no matched IRF for this image. **Copy both to a scratch folder
first** — the run writes `<stem>_analysis/molecule_data.tsv`,
`<stem>_analysis/intensity.npy` and `joint_output.tsv` next to the input without
asking.

**Tool:** *Imaging:Lifetime:Molecule-wise MLE*
(`chisurf/plugins/microscopy/sm_image_mle`, `SmImageMleTool`) — an AutoForm over
`molecule_mle.view.json` with three docks (**Analysis**, **Molecules**,
**Decay**). It is `menu_hidden`: the way in is the **Image Tools** window, below
the separator under the numbered pipeline. Headless equivalent:
`sm-image-mle analyze <file> -i <irf> …`, and the RPC method
`sm_image_mle.analyze.run`.

## Steps

1. Open **Spectroscopy → Image Tools** and pick **Molecule-wise MLE** (or
   construct `SmImageMleTool` directly). The window opens on the **Analysis**
   dock; **Molecules** and **Decay** are tabs behind it, both empty.
2. Drag the `.ht3` onto **CLSM imaging files**, and the mirror scan onto
   **IRF file**. Both lists accept a drop or take a `+ Files` dialog.
3. Set **Detector channels** = `0 1` (even entries are ∥, odd are ⊥ — a single
   channel is used for both).
4. Set the fit window over the *binned* micro-time axis. This is the step the
   tool gives no help with: the shipped default is **Fit start 0 / Fit stop 256
   / Micro-time binning 1**, which on this file covers 256 of 31 250 channels
   (0.8 % of the period) and returns nonsense (RF-577). Use
   **binning 128**, **start 0**, **stop 244** (= 31 250 / 128).
5. Open the **Segmentation** box and set the object filter. Defaults are
   σ = 1.0, threshold = −1 (Otsu), peak footprint 6, **min area 1 px**,
   **min photons 1**. For this cell image use **min area 20**, **min photons
   200**; leave the threshold on Otsu.
6. Press **👁️ Preview**. It segments the first file only — no fitting — and
   reports in the info line: `Preview: 11 molecule(s) segmented, background
   84.27 photons/pixel — press Run to fit.` (~1 s). Click the **Molecules** tab
   to actually see it: pressing Preview does not raise the dock its result lives
   in.
7. Tune σ / threshold / peak footprint / min area against that count, previewing
   again. Optionally draw an **Analysis region** (rectangle, ellipse, polygon,
   or a loaded mask/label image) to confine the search — the automatic threshold
   is then computed from those pixels alone.
8. Press **▶ Run**. Every selected file is segmented and every molecule fitted
   (~3 s for one file here, ~4.5 s for two). The info line ends at
   `9 molecule(s) in 1 file(s); median τ = 2.68 ns.`
9. Click **Molecules**. Left: one entry per molecule with a `τ = … ns` badge and
   a filter box; centre: the frame-summed intensity image (`inferno`, levels /
   histogram bar, colormap combo) with a green marker on the selected molecule's
   centroid; bottom-left: an HTML summary (τ, γ, r0, ρ, photons, 2I*).
10. Click **Decay** to see the selected molecule's VV/VH histogram (∥ then ⊥,
    stacked on one axis) with the fitted Fit23 model overlaid, semilog.
11. Press **💾 Export** and give a `.tsv`/`.csv` path for the combined table over
    all files. The per-file TSV and the joint TSV are already on disk from
    step 8.
12. Later, point **Open results** at a saved `molecule_data.tsv` (or a
    `joint_output.tsv`) to browse a previous analysis. The molecule list, the
    intensity image and the markers come back; the decays do not (they are not
    persisted), and neither do the settings that produced them.

## Expected

- Preview and Run segment identically for the same settings (verified: both
  found the same 11 labels).
- Every fitted molecule gets τ, γ, r0, ρ, `r_scatter`, `r_experimental`, `2I*`
  and the `regionprops` columns (`area`, `perimeter`, `circularity`,
  `eccentricity`, `solidity`, weighted and unweighted centroids, photon counts
  split ∥ / ⊥).
- Objects in the same sample share a lifetime: here 2.60–3.00 ns over nine
  objects spanning 395 to 90 353 photons, median 2.68 ns.
- Each molecule's measured second-moment ellipse is outlined on the image, so a
  segmentation can be checked against the picture it came from.
- The GUI, the CLI and the RPC service agree. Verified:
  `sm-image-mle analyze … --detector-chs 0,1 --micro-time-binning 128
  --micro-time-range 0,244 --min-area 20 --min-photons 200 --json` returned the
  same **9 molecules** and the same TSVs as the GUI run.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through
`SmImageMleTool`: files dropped on the two path lists, settings typed into the
AutoForm bindings, `👁️ Preview` / `▶ Run` / `💾 Export` clicked as
`QToolButton`s, docks switched through the dock tab bar, screenshots read at
every step.

**What works.** The analysis itself is sound and quick. Preview → tune → Run is
a real loop, and it is fast enough to be one (0.9 s preview, 2.9 s run over
15.6 M photons). With a correct fit window the nine objects come back at
2.60–3.00 ns with no outlier, which is the right answer for one dye in one cell,
and the small 26 px objects agree with the 3 251 px nucleus to within 0.1 ns.
The **Decay** dock is the best part of the tool: the VV/VH pair is drawn as one
stacked axis with the Fit23 model over it, and the fit visibly tracks both
branches for three decades (shot `08_decay_dock.png`) — a user can tell a good
fit from a bad one at a glance. The molecule list, its τ badges, the filter box
and the centroid marker make browsing 9 (or 900) results straightforward, and
the table columns are the ones a population histogram needs. Reopening a saved
`molecule_data.tsv` restored all 9 molecules and the intensity image. The CLI
reproduced the GUI numbers exactly.

**What is broken.** The measured molecule outlines never appear. The tool
documents them ("the second-moment ellipse of each measured object, drawn
read-only") and builds them correctly — `molecule_regions()` returned 9 ellipses
with the right centroids, axes and tilts — but the shared AutoForm image widget's
`add_roi` raises `AttributeError: '_PgImageView' object has no attribute
'_added'` on *every* call, after the shape is already on the scene. So exactly
one ellipse — the first molecule's, always — is drawn, is never tracked, can
never be cleared or recoloured, and one more identical copy is stacked on it at
every refresh (ROI count on the canvas went 2 → 3 → 4 → 5 … 9 across successive
refreshes, all at the same position). The exception is swallowed by the
observer's `except Exception: logger.debug(…)`, so nothing appears in the UI at
all: the user just sees one ellipse round the wrong-looking object and no reason
why. The same widget backs the analysis-region overlay in this tool and the
region overlay in the CLSM tool. **RF-576.**

**What is dangerous.** The shipped defaults produce a confident wrong answer.
Fit window `(0, 256)` at binning 1, `min_photons = 1`, `min_area = 1` — on this
file that is 0.8 % of the period, so of the 11 segmented objects 7 silently
disappear (too few photons in the window, no message) and the surviving 4 are
fitted on 2, 4, 8 and 26 photons and reported as τ = 0.026 ns, 5.22 ns,
23.49 ns and 1.45 ns, with the info line summarising `4 molecule(s) …; median
τ = 3.34 ns`. Nothing on screen distinguishes that from the correct run.
**RF-577.**

**What is invisible.** The G factor is not in the GUI at all — no field, no
readout. `fit_molecules_from_files` estimates it from the IRF tail on a *copy*
of the settings (0.601 for this IRF), so the number the fit used is never shown
and the view-model's own `g_factor` stays at 1.0 for the whole session. Every
molecule came back with `r_experimental ≈ −0.119` and ρ pinned at its 1 × 10⁻⁴
bound, and there is nothing in the window to explain or correct that. The CLI
exposes four more knobs the view does not (`--normalize-counts`, `--threshold`,
`--shift-sp` / `--shift-ss`, `--irf-threshold-fraction`). **RF-578.**

**What the threading does.** `handle_event` is dispatched before the base
class's own UI-thread guard, so every `done` / `progress` / `preview` the
worker emits reaches `SmImageMleTool.handle_event` on the worker thread and
mutates the Qt scene there — `QObject::startTimer: Timers cannot be started from
another thread` on stderr for every preview and every run. The same misordering
throws away the legitimate refresh: the view-model sets
`Analysing PQ_Olympus_MFIS.ht3 (1/2)…` per file, and the info panel never shows
it — sampled 18 times across a two-file run, it went straight from the
"Add CLSM imaging file(s)…" instructions to the final result. **RF-579.**

Screenshots: `01_open.png` (empty window), `03_preview_default.png` (preview
status), `04_run_default_window.png` (the nonsense run),
`05_run_full_window_analysis.png`, `06_molecules_dock.png` (image + list + one
stray ellipse), `08_decay_dock.png` (VV/VH + fit), `09_reopened.png` (reloaded
analysis).

## UX / UI suggestions

- **Derive the fit window from the data.** The one setting a user cannot guess
  is the only one with a meaningless default. On the first file drop, read
  `get_number_of_micro_time_channels()` and offer `binning` / `stop` that cover
  the period (e.g. 31 250 → binning 128, stop 244), or state the window in **ns**
  beside the channel numbers so `0…256` reads as `0…0.26 ns` and looks wrong.
- **Say how many molecules the filters dropped.** `Run` reported 4 where
  `Preview` reported 11 with identical segmentation settings; the difference was
  entirely `min_photons`. `9 fitted, 2 below min photons, 0 below min area`
  costs one line and removes the whole confusion.
- **Show the G factor.** At minimum a read-only field with the value actually
  used and where it came from ("estimated from the IRF tail" / "from the
  detector setup"); better, an editable field with an *auto* toggle, since
  `auto_g_factor` already exists in the settings and only the shared-setup hook
  can currently turn it off. A negative `r_experimental` deserves a warning next
  to it.
- **Raise the dock a button fills.** `Preview` and `Run` produce a picture and a
  table that live behind tabs the user must know to click. Raise **Molecules**
  when a run finishes; nothing is gained by leaving the user on the form.
- **Show progress.** A 2-file run is 5 s, a folder is minutes, and the panel says
  nothing throughout. The per-file message already exists in the view-model —
  it just never reaches the screen (RF-579). While a job runs, `Preview` / `Run`
  should also read as busy instead of silently swallowing a second click.
- **Round-trip the settings with the results.** Reopening a `molecule_data.tsv`
  restores the molecules but leaves the file lists empty and the fit window at
  `0 / 256 / 1`, so the reopened analysis cannot be re-run or continued. The
  table already carries `source_ptu`; write the settings beside it and restore
  both.
- **Ask before writing next to the data.** `Run` creates `<stem>_analysis/` and
  overwrites `joint_output.tsv` in the input folder with no dialog and no
  mention in the UI — only the button's tooltip says so. A read-only data folder
  would fail silently.
- **Give the molecule info panel room.** In the Molecules dock the HTML summary
  is a ~4-line box showing 3 of its 4 lines behind a scrollbar; the photon count
  and `2I*` — the two numbers that say whether the fit is trustworthy — are the
  ones cut off.
- **Label the fit window's units.** "Fit start / Fit stop" are in *binned*
  channels while "Micro-time binning" changes what a channel is, so the two
  fields silently reinterpret each other. Show the resulting ns range under
  them.

## Bugs filed

- **RF-576** — `ImageMapWidget.add_roi` builds `_PgImageView` via `__new__`, so
  `self._added` is missing and every region drawn on an AutoForm image raises
  after the shape is on the scene: one untracked, unclearable shape per refresh,
  error swallowed.
- **RF-577** — the shipped fit window `(0, 256)` / binning 1 / `min_photons 1`
  fits molecules on a handful of photons and reports τ = 23.5 ns and a median as
  if it were a result, dropping the rest of the molecules silently.
- **RF-578** — the G factor is absent from the GUI and the auto-estimated value
  actually used is never reported (the view-model keeps 1.0 while the fit used
  0.601).
- **RF-579** — `AutoFormMleTool._on_model_event` dispatches `handle_event`
  before its UI-thread guard: worker-thread Qt scene mutation, and the per-file
  progress message never reaches the panel.
