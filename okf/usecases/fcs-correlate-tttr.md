---
type: Reference
title: Use case — FCS correlation from raw TTTR (correlate, merge, hand to the fit)
description: Drive the unified FCS tool end to end — define correlation channels, drop TTTR files, multi-tau correlate in chunks, merge the chunks into one curve, save it as .cor and push it into ChiSurf for a diffusion fit.
tags: [usecase, fcs, correlation, tttr, multi-tau, merger, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: FCS correlation from raw TTTR

**Goal:** the step *before* [the FCS diffusion fit](/usecases/fcs-diffusion-fit.md).
The user has a raw photon stream from the confocal instrument and needs a
**correlation curve** out of it: pick which detectors form correlation channel A
and channel B, multi-tau correlate the stream in chunks, look at the chunks to
spot drift or a bad segment, average the good ones into one curve with per-lag
errors, write it as a `.cor` file and hand it to the fitting side. This is the
"Correlation / TTTR tools" coverage entry for the **correlator**.

**Data:** `test/data/tttr/BH/132/BH_SPC132.spc` — a Becker & Hickl SPC-130
stream, 183 657 photons over 62.3 s (≈3.0 kHz) on routing channels 0 (56 499),
1 (23 038), 8 (79 468) and 9 (24 652); macro-time resolution 13.5 ns. The shipped
detector setup **BS** names three detectors over those channels (`green`, `red`,
`yellow`). *Copy the file to a scratch folder before driving this workflow* —
**Save Merged** writes its output next to the input data without asking (RF-111).

**Tool:** `chisurf.plugins.fcs.fcs_toolbox` (`FcsTool`), display name
*Spectroscopy:FCS*. It is a `NavigationPanelTool`: a left rail with the five
correlator steps under a **Correlator** header, then a **Tools** group holding
2D-FLCS, Lifetime-FCS Sim, Burst-wise FCS, Diffusion Calc and Filter Calc. The
standalone `fcs_correlator` plugin is `menu_hidden` — this merged window is the
only entry point.

## Steps

1. Open the tool. It opens on step **2. Files & Steps**, not step 1 — the
   channel step is assumed to be preconfigured from the last session. Two
   checkboxes under *Steps:* decide the shape of the workflow: **Count
   rate/burst filter** (off by default) and **FCS merger** (on). Unticking one
   greys its row out in the rail.
2. Go to **1. Channel Definitions**. Pick the detector setup in *Detector setup*
   (`BS` ships), then build the correlation pairs: choose a detector in *A:* and
   in *B:*, give the pair a label, press **+ Add**. A pair whose A and B are the
   same detector is an autocorrelation; different detectors give a
   cross-correlation. **Save** persists the pairs for that setup to
   `~/.chisurf/fcs_channel_setups.json`.
3. Back on **2. Files & Steps**, drag the TTTR file(s) onto the file list (or use
   **+ Files** / **Folder**). Entries are checkable — only ticked files are read.
   Burst-ID `.bst` files may be dropped here too; doing so force-disables the
   count-rate filter step.
4. Go to **4. Correlator**. Pick the pair you defined in *FCS Preset*, or the
   detectors directly in the *A:* / *B:* combos. `Ch A` / `Ch B` take raw routing
   channel numbers (`0, 8`) and `µt A` / `µt B` optional micro-time gates
   (`0-100;200-300`) for PIE/ALEX-style windows.
5. Set *Bins* (linear bins per cascade, 9), *Cascades* (20 — together these fix
   the longest lag: 9·2²⁰·13.5 ns ≈ 127 ms), *Splits* (how many chunks the stream
   is cut into, so the chunks can be compared and averaged) and, for lags below
   the macro-time clock, **Fine** + *µt bin* (micro-time-resolved correlation;
   the first lag then becomes one micro-time channel, 3.3 ps).
6. Press **Correlate**. A modal progress dialog counts the chunks; the status
   line next to the button reads `N chunk(s) correlated.` and the *FCS
   Correlation* plot draws one curve per chunk on a log lag axis.
7. Go to **5. FCS Merger**. The chunks arrive automatically from step 4 (the
   *Folder* box is only needed to re-open chunks written in an earlier session).
   The table lists each chunk with its count rate in both channels and its
   duration, each with a **Use** tick — untick a chunk that drifted. The upper
   plot overlays the individual curves, the lower one the weighted mean; the
   status line reads `n curve(s), dur=…s, CR=… kHz`.
8. Press **Save Merged** to write the mean curve as a Kristine-format `.cor`
   (lag [ms], G, duration/count-rate metadata, per-lag error), and **Add to
   ChiSurf** to load it as an `FCS` dataset with the *Seidel Kristine* reader —
   ready for [the diffusion fit](/usecases/fcs-diffusion-fit.md).

## Expected

- Step 2: selecting `BS` makes its three detectors selectable by **name** in
  step 4's *A:* / *B:* combos and its saved pairs selectable in *FCS Preset* —
  the user should never have to remember that `green` means routing channels
  `8, 0, 3`.
- Step 6: with `Ch A = 0, 8` and `Ch B = 1, 9`, 181 lag points from the
  macro-time resolution (1.35e-5 ms) to 127 ms, `G` decaying to the uncorrelated
  baseline 1.0 at the longest lags, and the per-chunk photon counts recorded
  (here 32 617 in A, 13 297 in B for chunk 0 of 4).
- Step 7: one row per chunk, count rates ≈3 kHz, durations summing to the 62.3 s
  acquisition.
- Step 8: a `.cor` whose every row is a usable data point with a non-zero error,
  and a dataset in ChiSurf whose `y` is the correlation and whose `ey` is the
  error bar.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env,
`PYTHONPATH=modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:.`) against a
scratch copy of `BH_SPC132.spc`, with `QMessageBox` intercepted so nothing
blocks. Screenshots at every step.

**The core path works.** Correlate → merge → save → add-to-ChiSurf ran end to end
without a crash. `Correlate` on an empty tool correctly refuses with *"No Photons
Selected — No photons selected for correlation. Please load data."*. With the
file loaded and `Ch A = 0, 8` / `Ch B = 1, 9`, four chunks were correlated in
about a second, the per-chunk curves and the merged curve drew correctly, and
`Add to ChiSurf` produced one 180-point `FCS` dataset via the *Seidel Kristine*
reader. The **Fine** path also works: 181 points from 3.3 ps to 0.031 ms, all
finite. The Photon/Burst filter panel (step 3) is the best-looking panel in the
window — it computed `96 774 / 183 657 photons kept (52.7 %)` and drew a
delta-macro-time scatter and a count-rate trace without prompting.

**Step 1 is disconnected from step 4 — the headline problem.** With setup `BS`
selected and its view-model reporting channels `['green', 'red', 'yellow']`,
`FcsCorrelatorTool._channel_def_context()` returns `('', {}, {})`: it still reads
`widget.setup_combo`, `widget._detector_setups` and `widget._channels_for_setup`,
none of which exist on the AutoForm-ported `FCSChannelWidget` (the data moved to
`widget.model`). Everything downstream is starved — *FCS Preset* is empty, the
*A:* and *B:* detector combos are empty, and `model._channel_defs` stays `{}`.
The **only** way to correlate is to type raw routing-channel numbers into
`Ch A`/`Ch B`, which is exactly what naming detectors was supposed to avoid; and
if the user leaves them blank, `correlate_data` silently falls back to *all*
routing channels for both sides and correlates the whole detector against itself
with no indication in the UI. Filed as **RF-107**.

**The exported curve ends in a zero.** Every chunk comes back with `G = 0` at the
first lag (`x = 0`, which cannot be drawn on the log axis anyway) *and* `G = 0`
at the last multi-tau lag. The `x = 0` point is dropped on the way out, but the
last one survives merging (merged `y[-1] = 0.0`, `ey[-1] = 0.0`) and is written
into the `.cor`. Re-reading that file — which is what **Add to ChiSurf** does —
trips `RuntimeWarning: divide by zero encountered in divide` in
`kristine.py:112` (`w = 1./data[:, 3][i]`), and the loaded dataset ends with
`y[-3:] = [1.0914, 1.0825, 0.0]`. Visible in the screenshots as a vertical dive
to zero at the right edge of both the per-chunk and the merged plot. **RF-108**.

**You cannot read which step you are on.** In the left rail the *selected* row
renders its label in `HighlightedText` (#ffffff) while the stylesheet suppresses
the `Highlight` background, so the text is white on white — a pixel histogram of
the selected row contains no dark pixels at all, against ~150 for every other
row. The row shows its emoji and nothing else. This is in
`chisurf/gui/widgets/navigation.py`, so it hits every window built on that
shell — reproduced identically in the TTTR Toolbox. **RF-109**.

**Next/Back walk into steps the tool disabled.** With *Count rate/burst filter*
unticked, the rail greys out **3. Photon / Burst Filter**, but pressing
**Next ▶** on step 2 lands on it anyway (`enabled=False`), and **◀ Back** from
step 4 returns to it. It is not just visited — it is fully live: it read the
file, enabled a burst filter and reported `96 774 / 183 657 photons kept`, none
of which reaches the correlator, because `use_photon_filter` is `False`.

**Save Merged is silent and picks a strange name.** No file dialog, no
confirmation, no status text, nothing in the log — the button writes
`<data folder>/cr5.cor` and returns. `cr5` is the correlator's internal output
subdirectory constant, so the file is named after an implementation detail rather
than after the measurement, and a second run overwrites it without a word.
**RF-111**.

**A side tool is broken.** Opening the **Filter Calc** step raises
`TypeError: addItem(...): argument 2 has unexpected type '_Region'` from
`fcs_filter_calculator/gui_parts/main_window.py:1430` (`_clear_recon_plot` adds a
chiplot `_Region` to a pyqtgraph `PlotItem`) — a chiplot migration gap, caught by
a broad `except` that logs it as *"Multi-detector computation error"* and leaves
the panel's plots empty. The panel then sat at 0 % CPU for over three minutes
without finishing, so the walk had to be killed there. **RF-112**.

Screenshots: `01_open.png` (rail + file step), `s1_channel_def.png`,
`b_correlator_cross.png` (4 chunks, cross-correlation),
`a_next_lands_on_disabled.png`, `c_merger.png`, `nav_tttr.png` (the same
selected-row defect in a second tool).

## UX / UI suggestions

- **The plot never grows.** At 1400×1000 the *FCS Correlation* dock is ~400 px
  tall and leaves ~560 px of empty grey below it; the same at 1280×820. The
  correlation curve is the whole point of the panel and should take the height.
- **Say which channels were actually correlated.** The legend reads
  `chunk 0 … chunk 3`. When `Ch A`/`Ch B` are blank the tool quietly correlates
  every routing channel against every routing channel; the status line
  (`4 chunk(s) correlated.`) should name the channels and the photon counts it
  used — both are already in the result dict.
- **Fix the log-axis tick labels.** The x axis mixes notations in one row:
  `0.0001, 0.001, 0.01, 0.1, 1, 10¹, 10²`. Pick decimals or exponents.
- **The merger legend is drawn on top of the data.** In *Individual FCS Curves*
  the `chunk N` entries sit in the middle-left of the plot, overlapping the
  curves in a colour with almost no contrast against them; the correlator panel
  puts the same legend outside the data, top-right, where it is readable.
- **Explain what *Bins*, *Cascades* and *Splits* buy.** Three bare spinboxes
  decide the longest lag and the number of averaged sub-measurements. The
  tooltips describe the mechanism ("Number of multi-tau cascades"), not the
  consequence — showing the resulting longest lag (`≈127 ms`) and chunk duration
  (`≈15.6 s`) live next to them would make the choice obvious.
- **`µt A` / `µt B` need units.** `e.g. 0-100;200-300` are micro-time *channel*
  indices, not ns, and nothing says so.
- **The channel-definition panel keeps its standalone chrome.** Embedded as step
  1 it still shows a **✕ Close** button (which closes the panel inside the
  workflow) and its *Channel pairs* header renders greyed-out as if disabled.
- **The Controls dock clips at narrower widths.** At 1280 px the `Ch A` / `Ch B`
  line edits run past the dock edge and a horizontal scrollbar appears; the
  splitter should give the controls their size hint.
- **Step 1 is where the workflow starts but the tool opens on step 2.** With
  RF-107 fixed that is defensible, but the rail should then show that step 1 is
  satisfied (a tick, or the active setup name in the row) rather than looking
  skipped.

## Bugs filed

- RF-107 — the channel-definition step feeds nothing to the correlator (reads
  attributes the AutoForm port removed).
- RF-108 — `G = 0` at the last multi-tau lag is exported and re-read as a
  divide-by-zero weight.
- RF-109 — the selected navigation row's label is invisible in every
  `NavigationPanelTool`.
- RF-110 — **Next**/**Back** step onto navigation rows the tool has disabled.
- RF-111 — **Save Merged** writes with no dialog, no feedback and an
  implementation-derived filename.
- RF-112 — the FCS Filter Calc panel's reconstruction plot raises on a chiplot
  `_Region`, swallowed as a "computation error".
