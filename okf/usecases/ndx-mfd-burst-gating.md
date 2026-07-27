---
type: Reference
title: Use case — ndXplorer, gating a multiparameter burst space
description: Load a Paris/Seidel burstwise MFD folder into ndXplorer, plot one burst parameter against another, gate a sub-population with a 1-D range or a painted 2-D bitmap, and carry the gate out as Burst IDs or into an FCS/TCSPC/PDA/PCH analysis.
tags: [usecase, burst, mfd, ndxplorer, gating, smfret]
timestamp: '2026-07-27T00:00:00Z'
---

# Use case: ndXplorer — gating a multiparameter burst space

**Goal:** answer *where the populations are*. A burst search produces one row per
molecule with ~40 parameters (photon numbers, count rates, per-colour lifetimes,
anisotropies, macro-times). ndXplorer is the tool that plots any two of them
against each other, shows the third as a marginal, lets the user **cut out a
sub-population** — a FRET state, a bright fraction, the bursts with a sensible
anisotropy — and then hands that population on: as Burst-ID `.bst` files, or
straight into an FCS / TCSPC / PDA / PCH analysis in ChiSurf.

This is the step between [burst selection](/usecases/burst-selection-fret.md) and
every burst-wise analysis ([PDA](/usecases/pda-distance-fit.md),
[H2MM](/usecases/h2mm-burst-dynamics.md),
[accurate FRET](/usecases/accurate-fret-calibration.md)).

**Data:** `modules/ndxplorer/test/mfd/burstwise_All 0.1500#30` — a real
four-channel (2 colour × 2 polarisation) Paris burstwise output: `bi4_bur/`
(45 `.bur` burst tables, 12 237 bursts), `bg4/` + `br4/` (per-colour lifetime
fits), `BID/` (burst-ID files) and `Info/` (the Paris setup log). The raw
`.spc` photon files it was produced from are **not** in the repo — see step 10.

## Steps

1. Open **Tools → 🔭 ndX** (`chisurf.plugins.ndxplorer.rpc_bridge:make_ndxplorer`,
   which injects the in-process ChiSurf RPC client so the phasor/FRET-line
   overlays and the "Send selection to …" menu are live). The window opens on the
   ndXplorer splash with every plot control blank — nothing is loaded yet.
2. **File → Import → Analysis-Folder** and pick the `burstwise_All …` folder (the
   folder that *contains* `bi4_bur/`, not `bi4_bur/` itself). The reader
   concatenates all 45 `.bur` tables, joins the `bg4`/`br4` companions by file
   stem, offsets the macro-times into one continuous `Mean Macro Time (s)` axis
   and runs the equation set (Parameters tab) to derive `Sg`, `Sr`, `Proximity
   ratio`, `FRET efficiency`, … . The path appears in the **Path** box and the
   two count fields at the top right read `12237 / 12237` (shown / total).
3. Pick the axes in the **Plot controls** tab: **x:** `Tau (green)`, **y:**
   `r Experimental (green)` — the classic MFD lifetime-vs-anisotropy (Perrin)
   plot. The two spin boxes right of each combo are the **1-D** and **2-D** bin
   counts (81 / 31 by default, tooltips only); the row below is that axis'
   **min/max**, which auto-fills from the data (here 0…6 ns and −0.2…0.6).
   The 2-D histogram redraws with its x-marginal on top and y-marginal at right.
4. To gate on a *third* parameter, tick the checkable **z** group in the middle of
   the panel. That enables the z combo, the `z range` boxes, the z histogram and
   the **`+ select`** button — all four are greyed out until it is ticked.
5. Choose **z:** `Number of Photons`. The magenta z-histogram appears with the
   axis auto-ranged to the data (31…3131 photons).
6. **Drag the shaded region in the z histogram** onto the part of the
   distribution you want to keep (e.g. 100 → 3131 photons: "only bright bursts"),
   then press **`+ select`**. A row appears in the **Selection** table
   (parameter, min, max, Invert, Enable), the shown-count drops (12 237 → 7 312)
   and every histogram redraws from the surviving bursts. Rows are editable in
   place; `Delete` removes one, the 🗑 button clears them all.
7. For a **2-D gate**, tick **Draw Mask**, set *Cat:* (the class id) and a brush
   size, and paint over the population in the 2-D histogram; **Erase** removes.
   Press **✅ Apply**: the painted bins become one `Bitmap N (x-param, y-param)`
   row in the same Selection table and combine with the range gates (a box over
   the main population here: 12 237 → 5 082 bursts).
8. Save the gate for reuse with **💾 save** (and **📂 load**) beside the table.
9. **💾 BID** writes one Burst-ID `.bst` file per source measurement for the
   surviving bursts — 45 files here — and then asks *"Choose what to do with the
   saved Burst IDs: ☑ Compute microtime histogram / ☐ Open FCS Correlator Wizard
   to correlate BST files"*.
10. Right-click the 2-D histogram → **Send selection to** → **FCS / TCSPC decay /
    PDA / PCH**. The submenu is built from what ChiSurf advertises
    (`bursts.consumers`), each entry carrying its own summary and caveat as a
    tooltip, and it names the missing prerequisite in its own title when a send
    is impossible. The gated bursts are resolved to per-file `(first, last)`
    photon intervals and handed to the analysis over RPC.
11. Cross-checks used while driving: `Settings → Performance Settings`, the
    **Parameters** tab (the MFD constants `gG/gR`, `Bg`, `Br`, `By`, `PhiA`,
    `PhiD`, `alpha`, `tauD0`, `forster_radius` that feed the equations), the
    **Overlays** tab (analytic curves over the 2-D plot) and
    `View → Axis Control / Fit Gaussians / UMAP`.

## Expected

- The burstwise folder loads into one table of 12 237 bursts and **all** the
  derived MFD columns — including `Proximity ratio` and `FRET efficiency` — are
  offered in the axis combos.
- Every gate is visible in the Selection table, the shown/total counts and the
  three histograms agree, and the first gate a user creates is a plausible one.
- Burst IDs and selections round-trip to disk.
- A send either performs the analysis or says why it could not.

## Observed (last run: 2026-07-27)

Driven headlessly (offscreen Qt, arm64 env) through the real widget with the real
folder; screenshots inspected at every step.

- **Loading works and is fast**: 12 237 bursts from 45 `.bur` + `bg4` + `br4`
  files in **0.5 s**, with a cancellable progress window. Window construction is
  ~8 s (import cost), during which the splash is shown.
- **The whole red half of the parameter set is missing.** The loaded table has 39
  columns and the axis combos offer no `Proximity ratio`, no `FRET efficiency`,
  no `Sr` — the central quantities of the tool. Cause: the reader unconditionally
  drops the last column of every `.bur`, which is `Red Count Rate (KHz)`; with it
  the equation chain produces 15 derived columns, without it 3
  (`Sg`, `Fg`, `Tg-Tr(ms)`). Nothing is reported to the user. **RF-470.**
  The Perrin plot (`Tau (green)` vs `r Experimental (green)`, screenshot
  `03_perrin`) is therefore what this dataset can still be gated on, and it looks
  correct: a single population at τ ≈ 3.5 ns, r ≈ 0.1.
- **The first gate a user makes selects nothing.** The z range selector is never
  rescaled when the z parameter changes — it sits at `(0.25, 0.5)` whatever is
  chosen (measured for `Number of Photons` 31…3131, `Duration (ms)` 0.2…55,
  `Tau (green)`, `Count Rate (KHz)` 3.8…215). Pressing `+ select` without first
  hunting for the invisible handle adds a `0.25…0.5` gate, the counter goes to
  `0 / 12237`, all three plots go blank, and the now-empty z histogram no longer
  shows where to drag back to (screenshot `06_naive_gate`). No message.
  **RF-473.**
- **Gating itself is correct.** With the range set by hand: `N ≥ 80` → 8 370
  shown, matching the 8 377 bursts with `N ≥ 80` in the table minus those above
  the upper bound; `N ≥ 100` → 7 312. The painted 2-D bitmap gate is also
  correct — probing the four edges of the mask grid against the data confirmed
  bin (0,0) is (x-min, y-min), no flip: rows 0–5 → r ∈ (−0.200, −0.040), rows
  24–29 → r ∈ (0.440, 0.594), cols 0–5 → τ ∈ (0.00, 1.20), cols 24–29 →
  τ ∈ (4.80, 5.99).
- **BID export works**: 45 `.bst` files written, then the follow-up dialog. The
  dialog does not say where they went.
- **A send that reads nothing reports success.** The bridge resolves the gate to
  `{'m000.spc': [(2755, 3006), …], …}` — the bare `First File` name, never joined
  to the measurement folder (the original absolute paths *are* in
  `Info/Paris_x64 info.bin`) — so `tttr_path='m000.spc'` is resolved against the
  process CWD. **RF-471.** For `TCSPC decay` and `PCH` this correctly surfaces as
  *"decay read failed: No such file or directory: 'm000.spc'"*; for **FCS** and
  **PDA** the services swallow the open failure and return `ok` with
  `curves: []`, so the status bar reads *"Sent 7312 bursts from 45 file(s) to fcs
  (not recorded: no database product attached)"* over 45 stack traces in the log
  and zero photons read (screenshot `08_after_send`). **RF-472.** Note the raw
  `.spc` files are absent from the repo, so this run cannot prove the send
  succeeds once the path is right — only that a total failure is reported as a
  success.
- **Log noise on the happy path**: `[DISPLAY] Invalid 2D histogram format` at
  startup and six × `X histogram computation failed or returned empty result` on
  every successful load, both at ERROR level; a `'tuple' object has no attribute
  'edges'` warning from the marginal fast-path after clearing a selection
  (**RF-474, RF-475**); and a PyArrow parse fallback for every `br4` file (same
  trailing-tab root cause as RF-470).

## UX / UI suggestions

- **Name the gating panel.** The checkable group whose title is just `z` is the
  entire 1-D gating UI, and `+ select` is dead until it is ticked with no hint
  why. Title it *"z axis / gate"* and give the disabled `+ select` a tooltip
  saying *"enable the z panel to add a range gate"*.
- **Say when a gate is empty.** `0 / 12237` in a small unlabelled box beside a
  blank plot is the only feedback that the current selection excluded everything.
  A status-bar line (*"gate excludes all 12 237 bursts"*) costs nothing.
- **Label the count boxes.** The two fields at the top right showing
  `7312 / 12237` have no caption; *"shown / total"* would remove the guesswork.
- **The plot-control panel is dense and cryptic**: the `u` and `r` buttons, the
  bare `81` / `31` bin spinners and the unlabelled spin box above the x combo
  carry tooltips only. Short inline captions ("1D/2D bins") would help; the
  project rule is short labels + detail in the tooltip.
- **Widen the Selection table columns.** The header renders as `aramete` and the
  parameter cell as `Nu…` / `Bit…` at the default width — the two things the row
  exists to state. Stretch the first column, or elide from the right.
- **Better default axes.** After a burstwise load the defaults were
  x = `Tau (green)`, y = `First Photon`. A raw photon index is not an MFD
  observable; prefer the first *derived* parameter (proximity ratio / FRET
  efficiency) or, failing that, a count rate.
- **The provenance suffix reads like an error.** *"(not recorded: no database
  product attached)"* appears on every send from a normally-opened ndX window.
  Either attach the product or drop the clause when no store is in play.
- **Confirm where the BIDs went.** The post-save dialog offers two follow-up
  actions but never states the folder or the number of files written.

## Bugs filed

- RF-470 — the `.bur` reader drops the last real column, so the entire red /
  FRET half of the MFD parameter set silently never computes.
- RF-471 — the burst bridge sends a bare file name as `tttr_path`; nothing joins
  it to the measurement folder.
- RF-472 — `burst_fcs.correlate_file` and `pda.from_bursts` report `ok` with an
  empty result when the TTTR could not be opened, so a failed send is announced
  as a success.
- RF-473 — the z range selector is never rescaled to the chosen z parameter, so
  the first gate a user adds excludes every burst.
- RF-474 — the marginal-plot fast path aborts on its first attribute access.
- RF-475 — ERROR-level log noise on the normal startup/load path.
