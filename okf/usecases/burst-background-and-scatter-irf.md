---
type: Reference
title: Use case — background rate and scatter IRF from the non-burst photons
description: The two Burst Analysis utility panels that calibrate every burst-level number — estimate the per-detector background rate from the inter-photon-time tail, and recover a scatter IRF plus a background pattern from the photons the burst search rejected, then feed both to the burst-MLE lifetime fit.
tags: [usecase, burst, single-molecule, background, irf, tttr, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: background rate + scatter IRF from the non-burst photons

**Goal:** every corrected smFRET number (γ, E, S, a burst lifetime) needs two
instrument quantities the measurement itself contains but nobody acquires
separately: the **per-detector background count rate** and the **instrument
response**. In a free-diffusion measurement most of the acquisition has no
molecule in the focus, so the photons the burst search *rejects* are exactly a
built-in background + scatter measurement. The user wants (a) a background rate
per detector in kHz, and (b) a scatter-derived IRF and background pattern handed
to the burst-MLE lifetime fit — with no buffer-only or scatter acquisition.

**Data:** `chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/`
— `m000.spc`, `m001.spc`, `m002.spc` (Becker & Hickl SPC-132, freely diffusing
doubly-labelled dsDNA; 174 438 photons / 69.24 s in `m000`; macro-time
resolution 13.5 ns, micro-time resolution 3.2959 ps). Detector setup **BS**:
`green` = channels 8, 0, 3 over micro-time 0:4095; `red` = 9, 1, 2 over 0:2048
(PIE prompt); `yellow` = 9, 1, 2 over 2048:4095 (PIE delayed).

**Tools:** the two utility panels of the Burst Analysis window
(`chisurf/plugins/burst/burst_analysis`), below the numbered pipeline:

- **Background** — `burst_background`, `BurstBackgroundEstimator`; per-file,
  per-detector rate from the **inter-photon-time tail** (background photons are
  a homogeneous Poisson process, so the long-gap tail is a single exponential).
- **IRF & Background** — `burst_irf_bg`, `BurstIrfBackgroundTool`; runs its own
  burst search, keeps the **non-burst** photons, and returns per detector a
  normalised scatter IRF, a rate, a prompt position, and the vv_vh-stacked
  `{irf, bg}` patterns the burst MLE consumes (**🎯 Send to MLE**).

Both are also standalone plugins (`menu_hidden`), but the channel definition and
the raw files only carry over inside the workflow.

## Steps

1. Open **Spectroscopy → Burst Analysis** (≈ 4 s to first paint). The window
   opens on **1. Data Selection**.
2. Drop `m000.spc`, `m001.spc`, `m002.spc` into the list — status becomes
   *"3 TTTR file(s) selected; N imported to MMFDB."*
3. Click **2. Burst Selection** and pick the **Detector setup** `BS`. This is
   the *only* place the workflow's channel definition is set; the two background
   panels read it from there through the shared `detector_setups.*` RPC store.
4. Click **Background** (below the separator). The panel opens on its **Files**
   dock — the three raw files were pushed in from step 1 and the Channel
   Definition dock is hidden here (the workflow supplies the detectors).
5. Press **▶️ Estimate background**. ≈ 1.6–2.7 s for three files; the status line
   reads *"3 file(s), 3 detector(s) estimated."*
6. Read the result on the three other docks: **Inter-photon time** (log–log
   histogram per file × detector with the fitted background tail),
   **Background rate** (mean kHz per detector as coloured bars) and **Results**
   (one row per file × detector).
7. Click **IRF & Background**. It opens on its own **Channel Definition** dock,
   which here *does* show setup `BS` and the three detectors.
8. On **Files & Parameters**, check the burst-search parameters that define
   "non-burst": **Min photons/burst** 60, **Photon window** 10, **Time window**
   1.000 ms, **Dark-count floor (quantile)** 0.20, **Micro-time binning** 1.
   Set **Micro-time binning** to the value the **5. Burst MLE** step uses
   (32 for this setup) — otherwise the hand-over in step 11 silently does
   nothing (RF-753).
9. Press **🌙 Compute** (≈ 2.2–2.7 s for three files, pooled per detector).
10. Read **IRF (non-burst scatter)** — the normalised per-detector IRF on a log
    y axis — and **Results** — background (kHz), prompt (ns), non-burst and
    burst photon counts per detector.
11. Press **🎯 Send to MLE**. Inside the workflow this writes the `{irf, bg}`
    patterns into *both* MLE panels (burst-level and segment-level) and their
    per-detector state cache; the status line reports the detector count.
12. Go to **5. Burst MLE** and fit — the IRF and background it uses are now the
    ones measured from this very file's non-burst photons.

## Expected

- A background rate per detector, of order 0.1–2 kHz for a clean confocal setup,
  reproducible across repeat files of the same measurement.
- An IRF with a sharp scatter prompt at a few ns, one per detector, and a prompt
  position consistent between detectors sharing a synchronisation.
- The Results tables of *both* panels populated, and the file list showing the
  files the estimate actually ran on.
- The MLE fit afterwards using the sent IRF/background rather than reporting a
  missing IRF.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, isolated
`CHISURF_SETTINGS_DIR` seeded with a copy of the user's MMFDB so the `BS` setup
exists), screenshots read at every dock.

**The numbers are plausible and fast.** Background estimate 1.6–2.7 s for three
files; IRF/background compute 2.2–2.7 s. Rates per file:

| file | green | red | yellow |
|---|---|---|---|
| m000.spc | 1.327 kHz | 0.398 kHz | 0.184 kHz |
| m001.spc | 1.381 kHz | 0.580 kHz | 1.060 kHz |
| m002.spc | 1.334 kHz | 0.337 kHz | 0.181 kHz |

Green is stable to 2 % across the three repeats; the `m001` red/yellow values
are 1.5–6× the other two files, which is the kind of outlier this panel exists
to show. The IRF panel's own (non-burst counting) rates are lower —
green 0.693, red 0.338, yellow 0.177 kHz — because the two panels measure
different things (interphoton-time tail vs non-burst photons per acquisition
time); nothing in either panel says so.

**The IRF itself looks right.** The scatter prompt rises at 2.50 ns (green) /
2.29 ns (red, yellow) and the log-y plot shows a clean prompt followed by the
fluorescence tail the non-burst periods still carry.

**What is wrong:**

- **The Background panel shows almost nothing it computed.** After a successful
  estimate its **Results** dock is an empty table with headers and one blank
  row, although `results_rows()` holds all nine rows, and its **Files** dock is
  an empty list although the estimate ran on the three files the workflow pushed
  in. Only the status line, the bar chart and the inter-photon-time plot update
  (those register their own observers). RF-752.
- **The IRF panel's file list is empty too** when the files arrive from the
  workflow: 3 files in the model, 0 rows on screen. Different root cause —
  `AutoForm.refresh_plots()` only calls `refresh()`, and `PathListWidget`
  implements `sync()`. RF-754.
- **"Send to MLE" reports success while handing over something unusable.** At
  the shipped default **Micro-time binning = 1** the patterns are 8192 long; the
  MLE wizard's binning is 32, so its decay is 256 long and the fit skips with an
  INFO log — *"MLE fit skipped: decay length 256 != IRF length 8192 for 'green'
  (rebuild IRF at the current binning)"* — while the panel says *"Sent IRF +
  background to MLE for 3 detector(s)."* Setting binning to 32 first produces
  256-long patterns that land cleanly. RF-753.
- **Two detectors, one result.** `red` and `yellow` are the PIE prompt/delayed
  windows on the same routing channels. Their IRF-panel rows are identical in
  prompt (2.291 ns), non-burst (146 405) and burst (23 776) photons, their
  MLE `irf` and `bg` arrays are **byte-identical**, and in the IRF plot the red
  trace is drawn under the yellow one so the legend lists a colour with no
  visible curve. Only the background rate differs (0.338 vs 0.177 kHz), because
  that one path does honour the micro-time window. RF-755.
- **The inter-photon-time plot is unreadable.** The fitted tail model is drawn
  over the whole axis and reaches ~1e-20, so the y range spans 25 decades and
  every data point is squeezed into the top decade; the log x tick labels
  collide into a smear ("0.05 0.06 0.07 0.08 0.9 1") and the nine-entry legend
  sits on top of the data. RF-756.
- **A different burst search defines "non-burst".** The `BS` setup gives step 2
  `min_ph` 60 and `ph_window` 5; the IRF panel keeps its own defaults 60 / 10 /
  1.0 ms and nothing carries the step-2 values over, so the background is the
  complement of a burst search the user never ran. RF-757.
- **Two controls with no visible response.** Pressing **🌙 Compute** with no
  files, or **🎯 Send to MLE** before computing, leaves the panel's status label
  unchanged (*"Load files, define detectors, then compute."*); the reason only
  reaches a log record, which the workflow's shared status bar happens to show
  but the standalone tool does not. The sibling Background panel does write the
  reason into its own status line. RF-758.
- **`Files & Parameters` renders as `Files Parameters`** (with the *P*
  underlined) — the dock tab title goes through a `QLabel`, which eats the `&`
  as a mnemonic. RF-759.

Not judged this run: MMFDB registration of the raw files failed with
*"Authentication required"* and the data-selection status read *"3 TTTR file(s)
selected; 0 imported to MMFDB."*, because the driver constructs the tool without
the application login flow that owns the MMFDB session — an artefact of the
harness, not of the panel. The silent *0* is still poor feedback (see below).

## UX / UI suggestions

- **Say which detectors were used.** In the workflow the Background panel's
  Channel Definition dock is hidden, its file list is empty (RF-752) and its
  results table is empty — so after a successful estimate the only evidence of
  what ran is three coloured bars. Show the setup name and detector list in the
  panel header, the way the IRF panel's Channel Definition dock does.
- **The two panels report the same physical quantity with two estimators and
  two different answers** (green 1.347 vs 0.693 kHz). Name the method in each
  panel ("from the inter-photon-time tail" / "non-burst photons per acquisition
  time"), or show both in one table so the comparison is deliberate.
- **Carry the burst-search parameters from step 2** into the IRF panel (RF-757),
  or at least show the step-2 values beside the panel's own so the difference is
  visible; a "use the burst-search settings" button would make the intent
  explicit.
- **Default `Micro-time binning` to the MLE's binning** instead of 1, and label
  it with the target ("Micro-time binning (MLE uses 32)").
- **Aggregate the background table.** Nine rows of file × detector with no mean,
  spread or outlier marking makes `m001`'s 6× red/yellow excursion something the
  user has to spot by eye; a per-detector mean ± sd row (the bar chart already
  computes the mean) would carry the judgement.
- **Add units to the IRF results table** — *Non-burst* and *Burst* are photon
  counts; *Background* is per detector and pooled over all loaded files, which
  the header does not say.
- **Show why an import produced nothing.** *"0 imported to MMFDB"* with the
  reason only in the log reads as success with a zero in it.
- **Give the IRF panel an export.** The measured IRF is the one quantity every
  other TCSPC workflow needs, and it can only leave this panel through *Send to
  MLE* — there is no "save IRF" / "push to ChiSurf" action.
- Long absolute paths fill the file list; show the basename with the folder as
  tooltip (both panels).

## Bugs filed

- RF-752 — Burst Background tool never refreshes its declarative AutoForm
  widgets: the results table and the file list stay empty after a run.
- RF-753 — *Send to MLE* reports success while the default micro-time binning
  makes the patterns length-incompatible with the MLE decay.
- RF-754 — `AutoForm.refresh_plots()` skips `AUTOFORM_REFRESH` widgets that
  expose `sync()` (every `path_list`), so programmatically added files stay
  invisible.
- RF-755 — detectors sharing routing channels with disjoint micro-time windows
  get byte-identical IRF/background patterns and duplicate result rows.
- RF-756 — the inter-photon-time plot autoscales to the extrapolated fit model
  (25 decades), compressing all data into the top decade.
- RF-757 — the IRF & Background step does not inherit the burst-search
  parameters that produced the bursts.
- RF-758 — *Compute* / *Send to MLE* give no in-panel feedback when their
  preconditions are not met.
- RF-759 — dock tab titles eat `&` (mnemonic), so *Files & Parameters* renders
  as *Files Parameters*.
