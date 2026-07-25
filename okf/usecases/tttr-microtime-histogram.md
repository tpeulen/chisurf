---
type: Reference
title: Use case — TTTR micro-time histogram (raw photons to a fittable decay)
description: Load a raw TTTR file, pick a detector setup and detector, build the polarization-resolved micro-time histogram, read the width, save the stacked VV/VH decay and transfer it to ChiSurf for lifetime fitting.
tags: [usecase, tttr, tcspc, decay, microtime, detector-setup, polarization, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: TTTR micro-time histogram

**Goal:** the bridge workflow that feeds
[TCSPC lifetime fitting](/usecases/tcspc-lifetime-fit.md). The user has a raw
photon stream from the instrument (`.spc`, `.ptu`, `.ht3`) and needs a
**fluorescence decay curve** out of it — a micro-time histogram of the photons
belonging to one detector (colour), split into the parallel (VV) and
perpendicular (VH) polarization channels and stacked into the two-channel VV/VH
layout every `fit2x` estimator expects (see
[the VV/VH format](/references/vv-vh-decay-format.md)). The decay is then saved
to disk and pushed into ChiSurf as a TCSPC dataset to fit.

This is the "Correlation / TTTR tools" coverage entry for **channel definition +
micro-time histograms**.

**Data:** `test/data/tttr/BH/132/BH_SPC132.spc` — a Becker & Hickl SPC-130 stream,
183 657 photons on routing channels 0 (56 499), 1 (23 038), 8 (79 468) and
9 (24 652), 4096 micro-time channels at 3.2959 ps. The shipped detector setup
**BS** defines three detectors over those channels: `green` = `8, 0, 3`,
`red` = `9, 1, 2` (µT 0:2048) and `yellow` = `9, 1, 2` (µT 2048:4095).

**Tool:** `chisurf.plugins.tttr.microtime_histogram` (`MicrotimeHistogram`),
display name *Spectroscopy:Fluorescence decay:Histogram-Microtime*.

## Steps

1. Open the tool. It is `menu_hidden: true`, so there is **no menu entry** — it is
   reached from the `microtime-histogram` CLI, or launched automatically by
   NDXplorer after burst IDs are saved. Two tabs appear: **Histogram** (open
   first) and **Detector Setup**.
2. Go to **Detector Setup**. Pick the setup in the *Setup:* combo (`BS` ships).
   The *TTTR Reading routine* box shows the file type (`SPC-130`), the macro-time
   resolution (13.5 ns) and the micro-time resolution (3.2958984375 ps); the
   *Detectors* table lists the detectors with their channels, micro-time ranges
   and G-factors. **Polarization resolved** is ticked, which is what makes the
   channel list interleave as `[par, perp, par, perp, …]`.
3. Return to **Histogram**. Choose the colour in *Detector:* (`green`). The
   *Parallel* and *Perpendicular* boxes fill in from the detector definition
   (`8, 3` and `0`), *dt [ns]* and the file-type combo are set from the setup,
   and the *Output* path is proposed.
4. Drag the TTTR file(s) onto **Drop TTTR files below:** (or use **+ Files**).
   Entries are checkable — only ticked files are used. For single-molecule work,
   drop `.bur`/`.bst` burst-index files, or a whole burstwise folder, onto
   **Drop BID files below:** instead; the tool then finds the matching TTTR files
   itself and histograms only the burst photons.
5. Set *Binning* (1 = full 4096-channel resolution), the *VV/VH Timeshift*
   channels if the two polarization arms are not aligned, *G-Factor*, and
   *Polarization* (`vm` for the magic-angle combination).
6. Press **Compute**. The plot shows three log-scaled curves against micro time in
   ns — *Cumulative Parallel (VV)*, *Cumulative Perpendicular (VH)* and
   *Combined (VV + 2G·VH)* — and the *FWHM (VV + 2G*VH)* box fills in.
7. Press **Save** to write the stacked VV/VH decay to the *Output* path.
8. Press **Transfer to ChiSurf** to add the decay as a TCSPC dataset (setting
   `is_vv_vh`, `dt`, `g_factor` and `polarization` on the reader), ready to fit.

## Expected

- Step 3: selecting `green` yields parallel `[8, 3]`, perpendicular `[0]`,
  `dt = 0.003296` ns, G-factor 1.0.
- Step 6: 8192 stacked values (2 × 4096) totalling ~136 k counts for this file;
  three visibly separated curves with the combined trace highest.
- The reported width must be a property of the **data**, not of the display —
  changing *Binning* must leave it unchanged to within one coarse channel.
- Step 7: a text file a `vv_vh` reader can interpret without outside knowledge —
  the counts plus the `#`-footer (`format_version`, `channels`, `g_factor`) that
  `chisurf.core.fio.write_vv_vh` emits.
- Step 8: one new entry in ChiSurf's dataset list, with `dt` and the G-factor
  carried across, and a confirmation dialog.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env,
`PYTHONPATH=modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:.`) by
constructing `MicrotimeHistogram` directly and, in a second pass, with the real
`chisurf.gui.main.Main` window booted first so `cs.cs` was a live main window.
Files were put in through the real `PathListWidget`, buttons were `click()`ed in
the order above, and screenshots were taken and inspected at each step. Both a
repo sample and a private copy in a scratch "measurement folder" were used, to
see what the tool leaves behind on disk.

**The core computation is right and the plot, once you can see it, is good.**
The tool reads the SPC stream, splits it correctly into parallel `[8, 3]` and
perpendicular `[0]`, produces 2 × 4096 stacked values (135 967 counts), and draws
three properly-labelled log-scaled curves with a real legend against
*Micro Time (ns)* 0–12 ns. The Detector Setup tab is one of the cleaner panels in
the application — the detector table, the µT ranges, the reading routine and the
LUT box all read well and nothing is clipped. `_apply_setup_lut` and the
polarization gating already have unit tests.

**"Transfer to ChiSurf" — the whole point of the tool — does nothing, and says
nothing.** `add_to_chisurf` dispatches `setup.params.set`, whose handler reads
`cs.cs.current_setup`; no such attribute exists on the main window. With `Main`
constructed and assigned to `cs.cs`, clicking the button raises
`AttributeError: 'Main' object has no attribute 'current_setup'. Did you mean:
'current_fit'?`, Qt swallows it out of the slot, and the user gets **no dialog, no
dataset and no error** — `chisurf.imported_datasets` stays at 0. The action is
broken for every caller, so the IRF estimator's "send to ChiSurf" path
(`irf_estimator/gui/tool.py:1058`) fails the same way (RF-090).

**Pressing *Compute* writes a file into the user's measurement folder without
being asked.** `compute_microtime_histogram` ends with an "Auto-save the
histogram" block that calls `save_cumulative_histogram` on the *Output* path,
which defaults to the directory of the input data. Copying the sample into a
scratch folder and pressing **Compute** once — never **Save** — left
`sample_A_green_(8,3)-(0).dat` sitting next to `sample_A.spc`. During the first
run this dropped a stray `.dat` into `test/data/tttr/BH/132/` in the repo. A tool
with an explicit **Save** button should not also save on preview (RF-091).

**The FWHM readout changes by 34× when you change the binning, on identical
data.** `calculate_fwhm` takes the global `argmax` and walks out to the *first*
bin below half-max on each side; on shot-noise data that neighbour is a random
dip a few channels away, so the answer tracks the noise, not the width. Same
file, same detector, only *Binning* changed:

| Binning | dt (ns) | reported FWHM |
| --- | --- | --- |
| 1 | 0.003296 | **0.27 ns** (82 ch) |
| 2 | 0.006592 | **1.07 ns** (162 ch) |
| 4 | 0.013184 | **8.94 ns** (678 ch) |
| 8 | 0.026367 | **9.12 ns** (346 ch) |

The field is presented to two decimals with no caveat, so it reads as a measured
instrument-response width (RF-092).

**The *Parallel* and *Perpendicular* channel boxes are dead.** They are enabled
and editable, but `_get_interleaved_channels` consults the detector-wizard page
first and only falls back to the boxes if no setup provides channels — and a
setup always does. Typing `0` / `8` into them left the computation on `[8, 0, 3]`
and `parallel_channels` on `[8, 3]`. Their `textChanged` is wired only to
`update_output_filename`, so the *filename* dutifully changes to reflect channels
that are not used (RF-093).

**The documented CLI crashes on its main argument.** `__main__.py` feeds BID files
in with `widget.listWidget_BID.add_file(...)`, but the migration to the unified
`PathListWidget` left no `add_file` — the methods are `add_paths` / `set_paths`.
`microtime-histogram --bid-folder …` therefore raises `AttributeError:
'PathListWidget' object has no attribute 'add_file'` inside a `QTimer` slot, which
is also the NDXplorer hand-off path the README advertises (RF-094).

**The saved decay loses everything except the counts.** `save_cumulative_histogram`
hand-rolls `np.savetxt` instead of calling `chisurf.core.fio.write_vv_vh`, so the
file is a bare column of 8192 integers. Setting *G-Factor* to 1.25 and saving
produced a file with no `#` footer at all, while `write_vv_vh` on the same data
emits `#channels: VV, VH` and `#g_factor: 1.25`. Nothing in the file records the
G-factor the user typed in this very panel, the `dt`, or the fact that it is two
stacked 4096-bin channels rather than one 8192-bin decay (RF-095).

**The plot gets 93 pixels.** The `Histogram` tab is a `QSplitter` whose stretch
factors and initial sizes are never set, so Qt sizes it from size hints: the form
side wins and the plot — the tool's only output — is a black sliver.
`splitter.sizes()` is `[899, 93]` at 1000 px, `[1179, 93]` at 1280,
`[1499, 93]` at 1600 and `[2099, 93]` at 2200 — the plot is pinned at **exactly
93 px** and every pixel of extra width goes to the form, so making the window
bigger makes the plot relatively worse. The x axis collapses to a "5 10" tick
pair, the axis label clips to "Micro Time", and the legend is entirely outside
the visible area. Meanwhile two mostly-empty file-drop lists hold ~570 px
of height. A single `setSizes` call makes it the good plot described above —
compare `21_full.png` with `30_splitter_fixed.png` (RF-096).

**Compute with nothing selected is a silent no-op that leaves the old answer on
screen.** After clearing the file list, **Compute** logs "Computing microtime
histogram…", returns, and leaves the previous curves and the previous
`0.27 ns (82.0 channels)` in the FWHM box — no warning, nothing greyed out. A
user who swaps datasets and re-computes cannot tell a stale result from a fresh
one (RF-097).

**On this SPC-130 file the decay runs backwards** — counts rise monotonically with
micro-time index (deciles 2 291 → 11 649) because the module measures reverse
start–stop, and the last decile is empty. Nothing in chisurf inverts the TAC axis
(the only `invert_tac` in the tree is an unused argument in a reader deprecated in
2019), so this is the instrument's convention rather than a plugin defect — but
the panel offers no way to flip it and the FWHM box above assumes a peak, so it is
recorded here as the thing a first-time user will ask about.

**Timing was not a problem.** Constructing the widget takes ~1.5 s and **Compute**
on 183 k photons is ~0.03 s, so no progress indication is needed at this size.

Screenshots: `01_open.png`, `02_tab1_Detector_Setup.png`, `21_full.png`,
`20_plot.png`, `30_splitter_fixed.png`.

## UX / UI suggestions

- **Give the splitter initial sizes.** `setStretchFactor(0, 1)` /
  `setStretchFactor(1, 2)` in `__init__`, or a `setSizes` seeded from the window
  width, turns the tool from unusable to good (RF-096). The two file lists should
  also stop claiming vertical space they never use — a maximum height of a few
  rows, growing on demand, would free the plot even at small sizes.
- **Put the tool somewhere a user can find it.** It is `menu_hidden`, has no
  `docs/guides/` page, and its only advertised entry points are a broken CLI flag
  and an NDXplorer hand-off. It is the natural first step before
  [TCSPC lifetime fitting](/usecases/tcspc-lifetime-fit.md) and belongs in the
  TTTR toolbox hub beside *Count Rate Analysis* and *LUT Tools*.
- **Fix the command name in the README.** It documents
  `csc_microtime_histogram`; the manifest registers `microtime-histogram`.
- **Make the channel boxes read-only when a setup drives them**, or add an
  "override setup channels" tick that actually takes effect. Right now they look
  like the primary control and are the one thing on the panel that changes
  nothing (RF-093).
- **Label the outputs and give them units.** *Output*, *Binning*, *dt [ns]* and
  *FWHM* are outputs or derived values sitting in the same flat two-column grid as
  the inputs, in identical widgets. *Binning* has no unit hint (channels?
  factor?), *VV/VH Timeshift* says "(channels)" but the shift is more naturally
  thought of in ps, and *Polarization* offers a bare `vm` with no expansion of
  what the magic-angle option does to the stored curve.
- **Say what the three curves are before the user computes.** The colour coding
  (green = VV, red = VH, yellow = combined) is only discoverable from the legend,
  which is off-screen at the default size.
- **Report the counts.** The panel shows a width but never the total photons, the
  per-channel counts, or the peak count — the numbers a user checks first to know
  whether the acquisition was long enough.
- **Two "Save" buttons on the Detector Setup tab** (top-right beside *Setup:*, and
  bottom-right beside *Edit JSON*) with no indication that they save different
  things.
- **Drop the auto-save, or rename it.** If previewing really must persist, the
  path should default to a scratch/output directory rather than the folder the raw
  data came from, and the panel should say a file was written (RF-091).
- **The canonical `write_vv_vh` footer doubles its comment marker** — the lines
  come out as `# #g_factor: 1.25`, because a `#`-prefixed footer is handed to
  `numpy.savetxt`, which prefixes it again. Noticed while comparing against the
  plugin's output rather than through the GUI, so it is not filed as a bug, but it
  is worth a look when RF-095 is fixed.

## Bugs filed

- RF-090 — `setup.params.set` reads `cs.cs.current_setup`, which no main window
  has; "Transfer to ChiSurf" fails silently here and in the IRF estimator.
- RF-091 — **Compute** auto-saves a `.dat` into the user's raw-data folder
  without being asked, despite an explicit **Save** button.
- RF-092 — the FWHM readout is noise-driven and swings 0.27 → 9.12 ns with the
  *Binning* setting on identical data.
- RF-093 — the *Parallel* / *Perpendicular* channel boxes are enabled but ignored
  whenever a detector setup exists; they only rewrite the output filename.
- RF-094 — the documented `--bid-folder` CLI calls `PathListWidget.add_file`,
  which does not exist after the path-list migration.
- RF-095 — the saved decay is written with bare `np.savetxt` instead of
  `write_vv_vh`, dropping the G-factor, the channel layout and the format version.
- RF-096 — the `Histogram` splitter has no stretch factors, so the plot is fixed
  at exactly 93 px from 1000 to 2200 px of window width.
- RF-097 — **Compute** with no files selected is a silent no-op that leaves the
  previous curves and FWHM on screen.
