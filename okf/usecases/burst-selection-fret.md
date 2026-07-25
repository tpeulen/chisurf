---
type: Reference
title: Use case — single-molecule burst selection and FRET histogram (Burst Analysis)
description: Load raw single-molecule TTTR files into the integrated Burst Analysis workflow, pick a detector setup, find and filter bursts, read the proximity-ratio histogram, then hand the burst folder on to BVA, 2CDE, burst-MLE and the Burst Browser.
tags: [usecase, burst, smfret, single-molecule, tttr, gui]
timestamp: '2026-07-25T00:00:00Z'
---

# Use case: burst selection → FRET histogram → BVA / 2CDE / MLE

**Goal:** the canonical smFRET task — a user has free-diffusion single-molecule
data recorded as raw TTTR photons and wants (a) the bursts, (b) the
proximity-ratio (FRET) histogram of those bursts, and (c) the per-burst
follow-up analyses (BVA, 2CDE, burst-wise lifetime MLE) computed on exactly the
same burst set, without re-selecting files or re-defining detectors in each tool.

**Data:** `chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/`
— ten Becker & Hickl SPC-132 files (`m000.spc` … `m009.spc`, 1.2 MB each) of a
freely diffusing doubly-labelled dsDNA sample. `m000.spc` holds 174 438 photons
over 69.24 s; macro-time resolution 13.5 ns, micro-time resolution 3.296 ps.
This run used `m000`–`m002` (533 699 photons). Routing channels are 0/8 (green)
and 1/9 (red).

**Tool:** Burst Analysis (`chisurf/plugins/burst/burst_analysis`, display name
*Spectroscopy:Burst Analysis*, `BurstAnalysisTool`) — a navigation-panel window
that embeds nine other burst plugins as steps: **1. Data Selection**,
**2. Burst Selection**, **3. BVA**, **4. 2CDE**, **5. MLE-Lifetime**,
**6. H2MM**, then (below a separator) **Browser**, **Background**,
**IRF & Background**. Each embedded plugin is also reachable on its own; only
the aggregator is shown in the menu.

## Steps

1. Open **Spectroscopy → Burst Analysis**. The window opens on
   **1. Data Selection**: an empty drop list with **➕ Files / 📁 Folder /
   🗄️ Database / ➖ Remove / 🗑️ Clear** and the status line
   *"No TTTR files selected."*
2. Drop (or **➕ Files**) `m000.spc`, `m001.spc`, `m002.spc`. The status line
   becomes *"3 TTTR file(s) selected; N imported to MMFDB."* — each file is also
   pushed into the MMFDB object store as it is added.
3. Click **2. Burst Selection** in the left navigation. The files carry over
   automatically into the step's *Files* tab and the first one is selected; the
   panel immediately reads it and draws the delta-macro-time and MCS diagnostics.
4. On the **Filter Settings** tab pick a **Detector setup** — here `BS`
   (green = channels 8,0,3 over the whole TAC range; red = 9,1,2 over
   micro-time 0–2048; yellow = 9,1,2 over 2048–4095; PIE windows
   *prompt* 0–2048 / *delayed* 2048–4095; file type `SPC-130`). The setup also
   carries the burst-search parameters.
5. Check the filter settings the setup brought: **Filter mode** = *Sliding
   window* with **Min photons (L)** 20 and **Photons per window** 10 (time
   window 0.5 ms), plus a **Macro time interval** filter (*Use upper bound*,
   max dMT 0.15 ms, merge gap 3). The right-hand **Info** box previews burst
   statistics for the current file.
6. On the **Files** tab choose the **Output Format** — `CSV` (which writes the
   tab-separated `.bur` files), `MFD-HDF`, `MMFDB`, optional `Zip Output`.
7. Press **🚀** (*Process all loaded files*) in the toolbar. A progress dialog
   appears and closes; the run writes an analysis folder next to the raw data
   (`sliding_window_All 0.1500#60/` with `bi4_bur/*.bur` and `Info/`).
8. Read the result on the **Summary** tab (JSON: `n_files`, `n_bursts`,
   `n_photons`, `n_selected`, `output_folder`, and the full settings block) and
   on the **Bursts** tab (one row per burst: first/last photon, duration, mean
   macro time, photon counts per detector, count rate, proximity ratio).
9. Switch to the **Histogram** tab. **Feature** defaults to *Proximity Ratio*;
   set **# Bins** and **Range** (or press **⚡ Auto**), optionally set the GMM
   component count and press **🎯 Fit GMM** to overlay a mixture model.
   *The histogram and the burst table describe the files selected in the Files
   list — select all of them to see the whole measurement.*
10. Cross-check the **dT** and **Decay** tabs: delta-macro-time against photon
    index with the accepted band shaded, and the micro-time histogram of all
    photons against the burst-selected photons.
11. Click **3. BVA**. The burst folder and the detector setup carry over; the
    panel reads the `.bur` files and draws the burst-variance plot (std of the
    proximity ratio against its mean) with the shot-noise-limited static line.
12. Click **4. 2CDE**, then its **🚀** button, to add the FRET-2CDE dynamics
    feature (kernel *laplace*, τ = 100 µs) for the same bursts.
13. Click **5. MLE-Lifetime**. The first `.bur` of the run is loaded, the
    detector channels come from the setup, and a burst-wise maximum-likelihood
    lifetime/anisotropy fit is shown (model *Single lifetime + anisotropy
    (Fit23)*). Use **IRF & Background** (last panel) to extract a real IRF and
    background from the non-burst photons and **Send to MLE** instead of the
    synthetic Gaussian IRF the panel starts with.
14. Click **Browser** to inspect the whole result: the burst table, an
    E histogram, and E/S/size gating.
15. Optional headless equivalent: `burst-selection` CLI
    (`analyze`, `inspect`, `fit-gmm`), or the
    `burst_selection.jobs.analyze_files` / `.results.inspect_bur` /
    `.gmm.fit` / `.diagnostics.load` RPC methods.

## Expected

- Step 2 registers the files and reports how many reached MMFDB.
- Step 3 loads and diagnoses the first file in well under a second.
- Step 7 finishes in a few seconds for three 1.2 MB files, reports the number of
  bursts it found, and writes one `.bur` per input file.
- The **Info** preview in step 5 and the **Summary** in step 8 describe the same
  burst set, and no statistic there may contradict the search parameters shown
  beside it (a mean of 15 photons/burst is impossible when *Min photons (L)* is
  20).
- The proximity-ratio histogram shows the expected two-population dsDNA
  pattern: a donor-only spike near 0 and a FRET peak near 0.4.
- Every count-rate column is in the unit its header claims, and the burst's
  total count rate is at least as large as any of its per-detector rates.
- **File → Export → Export as .bur / as flrCIF** writes the current burst table.
- BVA, 2CDE, MLE and the Browser all operate on the burst folder produced in
  step 7 without the user pointing at it again.

## Observed (last run: 2026-07-25)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, the app's real
`dark_blue_flat` theme) against the real `BurstAnalysisTool`: navigation clicks,
the file drop, the toolbar **🚀**, every dock tab of the Burst Selection panel,
the histogram/GMM controls, the export menu actions, the 2CDE **🚀**, and each
downstream panel — with a screenshot taken and read at every step.

**The core path works and the physics comes out right.** Three files
(533 699 photons) filtered to 71 802 selected photons and **620 bursts**
(152 / 222 / 246) in 5.4 s; the `.bur` files and the `Info/` folder are written
next to the raw data; BVA found 555/620 bursts with std > 0; 2CDE reported
574/620 valid in 8.2 s; the MLE panel auto-loaded `m000.bur` and fitted
τ = 2.239 ns, r₀ = 0.380, ρ = 0.336; the Browser loaded 620/620 bursts with E/S
gating. The proximity-ratio histogram is exactly the expected dsDNA result — a
donor-only spike at ~0.02 and a FRET population centred at ~0.40 — and the
hand-off of folder + detector setup between the six panels needs no user action
at all, which is the whole point of the aggregator. Nothing raised a dialog.

**But the burst count rate is written in the wrong unit.** For the first burst
of `m000` (21 photons in 0.898 ms) the *Bursts* table, and the `.bur` file
behind it, report `Count Rate (KHz) = 0.023383`; the true rate is 23.383 kHz.
The same row's `Green Count Rate (KHz) = 20.817` *is* in kHz — so one row
carries two columns with the same unit label on scales 1000 apart, and the
burst's total rate reads *smaller* than its own green sub-rate. The cause is a
unit mismatch inside one expression (`crate = (npix/dur)/1e3` where `dur` is
already in ms), and the same file's `write_bur_file_old` computes it correctly
from seconds (RF-052). The bundled legacy reference `.bur` has the same 1000×
scaling, so this is long-standing and the fix has to decide between the value
and the label.

**Both export menu items crash whenever there is something to export.**
*File → Export → Export as .bur* and *→ Export as flrCIF* start with
`if not self._last_frame:` on a `pandas.DataFrame`, which raises
`ValueError: The truth value of a DataFrame is ambiguous`. Verified in both
directions: with 620 bursts loaded both raise; with no data both correctly print
*"No burst data to export."* The whole export surface is therefore dead
(RF-053).

**The Filter Settings *Info* box disagrees with the run it is supposed to
preview.** It reported *Bursts 7730, mean duration 4.103 ms, mean
photons/burst 15.0* for `m000` while pressing **🚀** on the same file and the
same settings produced 152 bursts of mean 113 photons — and 15.0 photons/burst
is below the *Min photons (L) = 20* displayed two rows underneath it. The box
counts contiguous runs of the photon-selection mask over the full photon array
instead of running the configured burst search on the filtered photons, and it
is not refreshed after the run, so both numbers stay on screen at once
(RF-054).

**The BVA plot throws on every repaint and never draws its error bars.** The
error-bar item is created with `height=np.array([])` and afterwards only ever
updated with `top`/`bottom`; pyqtgraph keeps the stale empty `height` and takes
that branch, so each paint raises
`ValueError: operands could not be broadcast together with shapes (31,) (0,)`
from `ErrorBarItem.drawPath` — a traceback per repaint on the console and a
binned-mean curve with no uncertainties (RF-055).

**🎯 Fit GMM does nothing out of the box.** The component spin box is created
with range 0–10 and never given a value, so it starts at 0 and the button
answers *"GMM fitting skipped: not enough data points or zero components."* —
blaming the data first — on a perfectly good 620-burst histogram (RF-056).

Also seen, not filed: the MMFDB import in step 2 failed for every file with
*"Authentication required"* in this unauthenticated harness and was reported
only as `0 imported to MMFDB` in the status line; the MLE panel logged *"MLE fit
skipped: no IRF for detector 'green'"* ~20 times in 300 ms to the root logger,
where the window's status bar (scoped to `chisurf.plugins.burst`) cannot show
it; and each run creates a new numbered output folder next to the raw data
(`… #60`, `… #60_0`) without ever asking where to write.

## UX / UI suggestions

- **Nothing tells the user the run finished.** The panel pops its own modal
  progress dialog and closes it, and the shared status bar still reads *Ready*
  afterwards — while the navigation shell exists precisely so embedded tools can
  report through `begin_task` instead. Report *"620 bursts from 3 files → …"*
  in the status bar and raise the **Summary** tab.
- **The burst table and the histogram silently show only the files selected in
  the *Files* tab** (the first one, auto-selected), while the *Summary* on the
  next tab reports all three. Neither view is labelled, so 152 and 620 sit two
  clicks apart with nothing explaining the difference. Put *"m000.spc — 152 of
  620 bursts"* in the tab or above the plot.
- **The *Bursts* table clips every header** (`Duration (ms`, `nber of Photo`,
  `ount Rate (KH`) and hides the *Proximity Ratio* column off the right edge —
  the one number the user came for. Size the columns to content and put the
  FRET observable first.
- **The same quantity has three names across the workflow**: *Proximity Ratio*
  in Burst Selection, *E* in the Browser, *FRET efficiency (proximity ratio)* in
  2CDE. Pick one (uncorrected proximity ratio is not E) and use it everywhere.
- **`Output Format: CSV` writes `.bur` files**, which are tab-separated. Label
  it `BUR (tab-separated)`. `Remove Folder` sits in the same row with no
  explanation of what it removes.
- **The output folder is created next to the raw data without asking**, named
  from the filter parameters (`sliding_window_All 0.1500#60`), and a repeat run
  silently adds `_0`. On read-only or shared acquisition storage this fails or
  scatters folders; offer the destination in the Files tab.
- **The *Info* box text is clipped** — *"…a burst is where m consecutive photons
  fall inside a time T."* is cut off at the panel edge — and the box has no
  refresh/staleness indication.
- **The pyqtgraph axis auto-prefix ruins two plots**: BVA's y axis reads
  *Std Proximity Ratio (x0.001)* with ticks 0…450 for a quantity that is
  naturally 0…0.45, and H2MM's *Transition rates (x0.001)* the same way. Fix the
  axis scale rather than asking the user to multiply.
- **The status bar keeps another panel's message.** Standing on *MLE-Lifetime*
  it still read *"FRET-2CDE: 574 / 620 bursts valid"*; on *Background* and
  *IRF & Background* it read H2MM's data folder. Clear it on panel change.
- **The Decay plot has no legend** — all-photons and burst-photons are two
  colours with the mapping only implied by the toolbar checkboxes, whose colour
  swatches are identical under the theme.
- **2CDE opens with an empty plot, a pre-filled folder and no prompt to run**;
  its only run affordance is an unlabelled 🚀 tool button, and the points it
  finally draws are dark blue on black with no density colouring and no
  threshold line.
- **The MLE panel fits with a synthetic Gaussian IRF by default** and reports
  τ to three decimals with no visible warning that the IRF is guessed — only a
  grey tip line. Its x axis is in channels while the fitted lifetime is in ns,
  its legend overlaps the y tick labels, and *Score 3.578* is an unlabelled
  goodness measure.
- **The setup combo offered exactly one entry** (`BS`, saved locally); no
  detector setup ships with the app, so a new user's first burst run has nothing
  to select and must detour through the Channel Definition wizard. Ship one
  generic two-colour PIE setup.
- **The *Summary* JSON dumps every filter block** (`bocpd_filter`,
  `kalman_filter`, `cusum_filter`) even though only the tttrlib sliding window
  ran, burying `n_bursts` under settings that had no effect.
- **No progress indication for the long steps.** 2CDE blocked for 8.2 s on 620
  bursts with a frozen panel; on a real measurement (tens of files, 10⁷–10⁸
  photons) both it and the burst search would block for minutes.

## Bugs filed

- RF-052 — `Count Rate (KHz)` in the burst dataframe and every `.bur` file is
  1000× too small (it is MHz), and disagrees with the per-detector
  `… Count Rate (KHz)` columns in the same row.
- RF-053 — *File → Export → Export as .bur* and *→ Export as flrCIF* raise
  `ValueError: The truth value of a DataFrame is ambiguous` whenever burst data
  is loaded.
- RF-054 — the Filter Settings *Info* box counts runs of the selection mask
  rather than the configured burst search, so it contradicts both the run
  (7730 vs 152 bursts) and its own *Min photons (L)* parameter.
- RF-055 — the BVA error-bar item keeps an empty `height` array, so every
  repaint raises from `ErrorBarItem.drawPath` and the binned means are drawn
  without uncertainties.
- RF-056 — the GMM component spin box defaults to 0, so **🎯 Fit GMM** always
  refuses, with a message that blames the data.
