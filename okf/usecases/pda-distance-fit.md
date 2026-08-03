---
type: Reference
title: Use case — PDA distance fit from burst tables (S1S2 histogram)
description: Turn a burst-search result into a shot-noise-exact PDA fit — pick the PDA experiment, drop the BUR tables, let the reader build the S1S2 histograms per time window, add a PDA model and fit a donor–acceptor distance.
tags: [usecase, pda, smfret, burst, fitting, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: PDA distance fit (burst tables → S1S2 → distance)

**Goal:** the step *after* burst selection. The proximity-ratio histogram of
freely-diffusing single molecules is broadened by shot noise, so its width says
nothing about heterogeneity on its own. PDA models the photon-count distribution
exactly, so fitting it returns a donor–acceptor distance (and width, and a
donor-only fraction) rather than a histogram moment. The user starts from a burst
search they already ran and wants R, σ and χ²ᵣ.

**Data:** `chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/` —
Becker & Hickl SPC-132 files of a freely diffusing doubly-labelled dsDNA sample,
plus the burst tables a previous burst search wrote next to them in
`burstwise_All 0.1000#15/bi4_bur/*.bur`. This run dropped `m000.bur`, `m001.bur`,
`m002.bur`; the reader resolved them back to `m000.spc … m002.spc` and applied
**827 burst slices** (63 677 photons of the 533 699 in those files). Routing
channels 0/8 (green) and 1/9 (red), container `SPC-130`.

**Experiment:** `PDA` / setup `PTU/HT3/SPC`
(`chisurf.core.experiments.pda2c.Pda2cReader` +
`chisurf.gui.widgets.experiments.pda2c.controller.Pda2cTTTRWidget`), models
`chisurf/core/models/pda2c/`.

## Steps

1. Start ChiSurf. In the **Read data** dock set **Experiment** = `PDA`;
   **File type** is then `PTU/HT3/SPC` (the only setup).
2. The PDA reader panel appears with five sections: **Colours** (`2 — PDA (S1S2
   histogram)`), **Detector** (Setup / Routine / Ch0 / Ch1 with channel lists and
   micro-time windows), **Segmentation** (`Burst search (variable duration)`),
   **Acquisition** (`nPh min` / `nPh max`, the `TW [ms]` spin with a **+** button
   and the time-window list), and the drop list.
3. Pick a **Setup** — `BS` fills Ch0 = green `8, 0, 3` over micro-time `0-4095`
   and Ch1 = red `9, 1, 2` over `0-2048`. For this SPC-132 file set, edit
   Ch0 = `0,8`, Ch1 = `1,9`, both micro-time ranges `1-4095`, and set
   **Routine** = `SPC-130`.
4. Check the **Acquisition** settings: `nPh min` 15, `nPh max` 150 (the S1S2
   support is 151×151), and the time-window list, pre-filled with
   `10 ph @ 1 ms`, `20 ph @ 2 ms`, `30 ph @ 3 ms`. Each list entry produces its
   own histogram, so this asks for three. Use **+** to add
   `(nPh min, TW)` pairs, double-click an entry to edit it, right-click to remove.
5. Drag the three `.bur` burst tables onto *drop files or analysis folders below*
   (a whole `bi4_bur` folder works too — the list expands it). With **Auto load**
   ticked the read starts on drop; untick it and press **Load dropped files**.
6. The reader locates the referenced TTTR files next to the burst tables, turns
   each burst row into a photon-index interval, and computes one S1S2 histogram
   per time-window entry with `tttrlib.Pda`. It appears in **Datasets** as one
   group `m000_TW1ms` with members `m000_TW1ms` / `_TW2ms` / `_TW3ms`, data type
   `PDA`. Each member carries the flattened 151×151 S1S2 matrix as `y`
   (22 801 points) plus the `pda` dict the models read
   (`s1s2`, `ps`, `nPh_min/max`, `observation_time`, `tttr_indices`, …).
7. Select the **group row** in *Datasets* (not one of its members — see RF-263),
   pick a model in the **Model** combo — `PDA-discrete`,
   `PDA-Gaussian-distance`, `PDA-SAW-ν-distance`, `PDA-dynamic-2-state`,
   `PDA-anisotropy` — and press **+ Analysis**.
8. The **Analysis** dock shows the model editor: **FRET parameters** (τ₀, R₀,
   κ²), **Distance distribution** (an `add` / `del` list of Gaussian components
   R_P / s_P / x_P), **Corrections / nuisance** (BG, BR, QY, g, direct
   excitation, crosstalk, α), **Diagnostics** (*🔗 Apply light path*,
   *🎲 Consistency check*) and **Fit histogram / statistic** (histogram axis,
   statistic, binning).
9. Press **Fit**. Read χ²ᵣ, the fitted distance and its confidence interval on
   the fit window's **Info** tab; look at the proximity-ratio overlay on
   **Distribution**, the per-member weighted residuals on **Residuals**, and the
   S1S2 residual map on **Residuals 2D**.

## Expected

- Three PDA curves for a three-entry time-window list, each 22 801 points, built
  from the same 827 bursts.
- A PDA fit that converges to a physically sensible distance with χ²ᵣ falling
  substantially, and a **Distribution** plot whose model curve tracks the
  measured proximity-ratio histogram *after* the fit.
- Every panel of the fit window agreeing on the same χ²ᵣ.

## Observed (last run: 2026-07-26)

**The analysis itself is correct and the numbers are good.** Reading, burst
slicing, the S1S2 histograms and both PDA models worked on the first try:

| | before fit | after fit |
|---|---|---|
| `PDA-Gaussian-distance`, group of 3 TWs | χ²ᵣ = 16.16 | **χ²ᵣ = 3.46** |
| R(P,1) | 50 Å | **46.95 ± 0.46 Å** (1.0 %) |
| s(P,1) | 6 Å | **6.26 ± 0.33 Å** |
| xDOnly | 0 | **0.336 ± 0.025** |
| `PDA-discrete`, single TW | χ²ᵣ = 37.68 | **χ²ᵣ = 8.70** |

The **Info** tab is the best panel in the app: values, `±σ (%)`, the error
source (`cov`), links, an explicit *"bounds only (not in objective) … no
informative prior — the fit is plain least squares"* note, and per-parameter
likelihood intervals with the method named.

Everything that went wrong is in the shell around that analysis:

- **Selecting a member of the dataset group silently mis-targets the fit.**
  With the group `m000_TW1ms` expanded, clicking member row 0 / 1 / 2 and
  pressing **+ Analysis** gave: no fit at all (a `DataCurve object has no
  attribute 'pda'` error against the unrelated *Global Dataset*), a fit on the
  **whole group** rather than the selected 2 ms curve, and no fit at all
  (*"dataset indices out of bounds"*). Nothing is shown but a 10 s status-bar
  line. Filed as RF-263 and RF-267.
- **The Distribution plot does not refresh when the fit finishes.** After the
  single-curve fit took χ²ᵣ from 37.68 to 8.70, the visible **Distribution** tab
  still drew the starting model and the annotation `χ²ᵣ=37.6816`, while the
  **Info** tab in the same window already read `chi2r=8.7048`. Switching away and
  back — or calling `fit.update()` — fixes it. RF-265.
- **The GUI freezes for the whole fit with a 0 % progress bar.** The three-curve
  global fit took 22 s. A 1 s `QTimer` armed before the click fired *exactly
  once*, after the fit returned, so no Qt event was processed in between: the
  `EnhancedProgressDialog` that `_run_fit_impl` puts up cannot repaint, and the
  ETA / χ² text it is written to display never appears. RF-266.
- **This installation's experiment list is stale, silently.** The combo offered
  a `RICS` experiment whose reader and six models do not exist
  (`No module named 'chisurf.core.experiments.rics'`, logged as ERROR at every
  start), the PDA model list was missing `PDA-dynamic-N-state` and offered a
  removed `Pda2cDynamicThreeStateModel` instead, and the shipped `PDA3c (3-colour)`
  experiment was absent altogether. Cause: the shipped defaults are read from a
  path that never exists, so the user's copy of `experiment_configs.yaml` is the
  only source and the "configuration update available" prompt can never fire.
  RF-264.
- **The fit sub-window is titled after the wrong curve** —
  `PDA-Gaussian-distance - m000_TW3ms` for a fit named
  `PDA-Gaussian-distance - m000_TW1ms`. RF-268.

Screenshots inspected this run: the read-data dock with the PDA panel, the panel
with files dropped, the dataset tree, the analysis dock with every section
expanded, and all five fit tabs before and after the fit.

## UX / UI suggestions

- **Label the range boxes.** *Range selection* is a 2×2 grid of four bare number
  boxes (`0`, `0`, `auto` / `150`, `150`) with no captions and no units. Worse,
  three conventions are on screen at once for the same fit: the boxes say
  `0 … 150`, the **Info** tab says `range=0..22800` (the flat S1S2 index) and the
  plot annotation says `Fit-range 1, 78` (proximity-ratio bins). Say which is
  which, in the unit the user is looking at.
- **Fix the distance-distribution table header.** `R_P`, `s_P` and `x_P` are
  clipped and overlap the neighbouring `Fixed` column, so the three-component
  table reads as a row of half-letters. Give the header row its natural width or
  drop the subscripts.
- **Tone down `add` / `del`.** They are full-width saturated green and red bars
  that dominate the panel; a Gaussian component is not a destructive action. A
  pair of small ➕ / ➖ tool buttons next to the table caption would match the
  rest of the app.
- **Let the Diagnostics status text finish its sentence.** Both paragraphs are
  cut mid-phrase ("…from a simulated optical setup instead of", "…could
  plausibly have come from") with no ellipsis and no scroll, so the explanation
  ends in the middle of the point it is making.
- **Label the Residuals 2D axes and give it a diverging scale.** The 151×151 map
  has no axis titles (they are S1 and S2 photon counts), no colour bar, and a
  greyscale ramp — so the sign of a signed residual is unreadable. A diverging
  map centred on zero with a bar is the standard for this plot.
- **Say what the three offset curves on Residuals are.** They are one per group
  member, stacked at +0 / +5 / +10, but the y-axis is labelled `w.res.` and
  reads 0–15, which invites reading a residual of 12. Label the offsets or the
  member names.
- **Move the Distribution annotation off the axis.** The
  `Fit-range / χ²ᵣ / DW` box is drawn over the y-axis tick labels, so `χ²ᵣ` and
  the top tick overprint each other.
- **Give the Parameter scan tab a hint.** It is an empty black plot with a
  ±0.5 / ±0.5 axis and nothing to say what to select or which control runs the
  scan.
- **Tooltip the fitting controls.** `Fit`, `Sample`, `local first`, the `…`
  button and the unlabelled number box beside `Fit` have no tooltips; only
  `auto` does. `Stps` in the Sampling group is an abbreviation that does not need
  to be one.
- **Name the pooled dataset after the pool.** Three burst tables pooled into one
  histogram are named `m000_TW1ms` — the first file's name — which reads as "one
  file". Something like `m000..m002 (3 files) TW 1 ms` would not mislead.
- **Two drop targets, one panel.** The PDA panel has its own drop list *and* the
  main window's *Drop files here.* is right below it, with different behaviour.
  Make the outer one either forward to the reader or say it does not apply here.
- **Widen the micro-time / statistic combos.** `Burst search (variable durat…`,
  `Proximity ratio S1/(S0…` and `Poisson deviance (ML` are all elided at the
  dock's natural width.

## Bugs filed

- RF-263 — `onAddFit` maps a dataset-group *member* row to the wrong top-level
  dataset index, so the fit is created on unrelated data (or not at all).
- RF-264 — `_setup_experiments` reads the shipped `experiment_configs.yaml` from
  `get_path('cs')`, which is not a valid path type, so the shipped defaults are
  never merged and the update prompt is dead code.
- RF-265 — the fit window's plots are not refreshed when a fit finishes; the
  visible tab keeps the pre-fit model and χ²ᵣ.
- RF-266 — the progress callback built in `_run_fit_impl` is never handed to
  `run_fit`, so every fit freezes the GUI behind a 0 % dialog.
- RF-267 — an *Add fit* failure is reported only to the log and a transient
  status-bar message.
- RF-268 — the fit sub-window title uses a leaked loop variable, naming the last
  group member instead of the fit.

## Related

- [burst selection and FRET histogram](/usecases/burst-selection-fret.md) — the
  step that produces the `.bur` tables this workflow consumes.
- [PRD-65](/prds/prd-65.md) — time-correlated PDA.
- `docs/concepts/pda2c.md`, `docs/guides/11_pda2c.md`.
