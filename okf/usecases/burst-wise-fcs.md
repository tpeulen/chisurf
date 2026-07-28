---
type: Reference
title: Use case — burst-wise FCS (a diffusion time per burst)
description: Correlate the photons of every single-molecule burst separately, fit each correlation for a diffusion time, and browse the per-burst curves.
tags: [usecase, burst, fcs, correlation, diffusion, gui]
timestamp: '2026-07-27T00:00:00Z'
---

# Use case: burst-wise FCS — a diffusion time per burst

**Goal:** a burst search gives every burst a brightness, a duration and a FRET
efficiency. Burst-wise FCS adds one more per-burst observable: the *diffusion
time* τ_D obtained by correlating that burst's photons on their own. Plotted
against E or S it separates species that share a FRET efficiency but differ in
size or in aggregation state, and it is the standard way to spot the rare
multi-molecule event hiding inside a burst population.

**Data:** the burst analysis shipped with the burst-selection plugin —
`chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15/`
(10 `bi4_bur/*.bur` tables, 2 980 real bursts) over the raw
`bh_spc132_sm_dna/m00*.spc` streams (BH SPC-132, 174 438 photons per file,
13.5 ns macro-time resolution). Detector setup `BS` (green = channels 8,0,3;
red = 9,1,2; yellow). The same folder the
[burst selection](/usecases/burst-selection-fret.md) use case produces.

## Steps

1. **Define the FCS channel pairs first** — the burst-FCS window cannot create
   them and does not say so (RF-509). Open **Setup ▸ FCS Definitions**, pick
   detector setup `BS`, and for each pair choose **A** and **B** from the
   logical channel names (`green`, `red`, `yellow`), type a label and press
   **+ Add**: `green×green` = `GG_ACF`, `green×red` = `GxR_CCF`,
   `red×red` = `RR_ACF`. Press **💾 Save**.
2. Open **Spectroscopy ▸ Fluorescence Correlation Spectroscopy ▸ Burst-wise
   FCS**.
3. Pick the detector setup `BS` in the top combo. The **FCS channel pairs** list
   fills with the three pairs from step 1, all checked. Uncheck the ones you do
   not want.
4. Drag the burst-analysis folder (`burstwise_All 0.1000#15`) onto **Burst
   folders or BUR/BST files**, or use **📁 Folder**. It expands to the ten
   concrete `bi4_bur/m00*.bur` index files, all checked; each resolves to its
   raw `.spc` stream and its `(first photon, last photon)` burst ranges.
5. Set the correlator: **FCS bins (B)** = 3, **cascades** = 20, **Fine grid**
   off, **Padding ±[ms]** — this is the photon window added around each burst
   before correlating and the default of 100 ms is far larger than a burst
   (RF-512); 0 correlates burst photons only.
6. Choose the per-curve **Mode**: *None* (correlate only), *Simple* (one-
   component 3-D Gaussian diffusion, ~2 ms/curve) or *MaxEnt* (a τ_D
   distribution per burst, ~48 ms/curve — 14 min for this folder, RF-515).
7. Restrict the fit window with **t_min / t_max [ms]** — leaving both at 0 fits
   from the shortest lag, where detector afterpulsing dominates, and the
   reported τ_D is then not a diffusion time (RF-511).
8. Press **▶ Run**. A status-bar progress bar advances once per *file*.
9. Browse the result: the right-hand list holds one entry per (file × burst ×
   pair), `m000.spc · b0 · GG_ACF`. Type in the filter box (e.g. `GxR`) to keep
   one pair. Select a row to see its **Correlation** curve with the fit, and —
   in MaxEnt mode — its **Diffusion-time distribution**.
10. Carry the per-burst τ_D out to a burst-parameter file so it can be plotted
    against E/S in ndX or the Burst Browser. **There is no such step: the
    window has no export at all** (RF-509 … RF-510).

## Expected

- Step 4 resolves 10 files × ~298 bursts; step 8 produces one curve per burst
  and pair — 8 940 curves for the three pairs — in about 22 s.
- Each curve is a multi-tau correlation over 61 lag points from ~10⁻⁴ ms to
  ~10 ms, i.e. the burst-length-limited window.
- The *Simple* fit returns a τ_D of the order of the ensemble diffusion time
  (sub-millisecond to a few ms for this DNA sample), with obviously bad fits
  flagged rather than reported as numbers.
- The 8 940 τ_D values leave the window as a per-burst parameter file
  (the legacy wizard wrote Paris-style `.td4` tables next to `bi4_bur/`).

## Observed (last run: 2026-07-27)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through
`BurstFcsTool` and `FCSChannelWidget`, with screenshots read at each step.

**What works.** The mechanics are sound and fast. Dropping the burstwise folder
expands it to the ten `.bur` files correctly; each `.bur` resolves its raw
`m00*.spc` stream by name and yields exactly the non-empty burst rows (203 of
the 407 data rows in `m000.bur` — the all-zero rows are correctly skipped).
Correlation is
quick: 609 curves for one file in 1.4 s, 8 940 curves for the folder in 21.8 s.
Pair check-boxes work (checking only `GxR_CCF` gives 2 980 curves of that pair
alone), the filter box narrows 8 940 rows to 2 980 instantly, and re-running
replaces rather than appends. The micro-time gating that separates prompt from
delayed photons is applied correctly (a `(0, 2048)` range selects micro-times
480–1988, not their complement). The plots render legibly with the fit
overlaid.

**What does not.** The window cannot deliver its own product, and by default
the numbers it computes are not diffusion times:

- The pairs it needs cannot be made in it. On a fresh profile the pair store is
  empty, so the **FCS channel pairs** list is empty for *every* detector setup,
  and **Run** answers "Select a detector setup and at least one FCS pair." with
  a setup plainly selected. The editor that fills the list is a different,
  `menu_hidden` plugin (**Setup ▸ FCS Definitions**), which the window never
  names — no label, no tooltip, no link (RF-509).
- Nothing can leave the window. There is no export, no save-curves, no push to
  ChiSurf: the toolbar is `▶ Run` plus a settings menu (load/save *settings*,
  show the pairs JSON). The 8 940 τ_D values are visible one row at a time and
  then discarded on close. The legacy `wizard.py` this tool replaces wrote
  `.td4` per-burst tables — the file format the rest of the burst stack reads
  (RF-510).
- With the shipped defaults the fitted τ_D is wrong by two orders of magnitude.
  Over 1 488 curves (2 files): median τ_D = **0.0075 ms**, 31.7 % below 1 µs,
  4.6 % pinned exactly at the fit grid's lower rail. Re-running with the fit
  window set to 0.01–10 ms — i.e. excluding the afterpulsing spike — gives a
  median of **0.87 ms**, which is a plausible diffusion time for this sample
  (RF-511).
- 32.7 % of those fits are unphysical: the fitted G(t_c) *rises* with lag,
  because the amplitude comes from an unconstrained least-squares solve and is
  allowed to go negative. The screenshot of `m000.spc · b0 · GxR_CCF` shows the
  red "fit" climbing from below zero to a plateau across a noisy
  cross-correlation. Each such curve still reports a τ_D, unflagged — this is
  the user-visible face of RF-505, already filed from the code side; a sane fit
  window cuts it to 13 % (RF-511).
- The default padding decides the answer. At the default ±100 ms, a 16-photon,
  0.33 ms burst is correlated together with 472 surrounding photons — **3.3 %
  of the correlated photons belong to the burst**. Turning padding off changes
  the median τ_D of one file from 0.020 ms to 0.288 ms (14×) and drops 78 of
  609 curves for lack of photons, silently (RF-512).
- The per-pair **Bins / Cascades / Fine** columns that the FCS Definitions
  editor stores (here 9 bins) are ignored: the window correlates every pair with
  its own global settings (3 bins). The same named pair therefore gives a
  different correlation here than in the FCS correlator (RF-513).
- The progress bar never goes away. After the run the status bar still reads
  "Computing burst-wise FCS… 100 %" with a ✕ button, in every screenshot taken
  after step 8, until the user dismisses it by hand (RF-514).
- MaxEnt mode costs 48 ms/curve — ~14 min for this small folder — in a
  synchronous loop that repaints once per *file*, so a single-file dataset shows
  one progress tick for the whole run (RF-515).
- On a single burst the MaxEnt distribution is meaningless and says so nowhere:
  burst 0 of `m000.spc` returns τ_D peak 8.8 ms and mean 352 ms from a 0.33 ms
  burst, on an auto grid running to 10³ ms (RF-511 covers the missing quality
  flag).

Two things found beside the main flow: `save_fcs_channel_setups` reports success
while silently keeping a setup that was removed from the payload (RF-516) —
which is why this run's `BS` pair set could not be rolled back out of the local
profile and is still there; and in *Simple* mode the **Diffusion-time
distribution** tab is permanently blank, since only MaxEnt fills `td_grid`/`p`.

## UX / UI suggestions

- Put the per-burst τ_D distribution *in the window*: a histogram of the fitted
  τ_D over all bursts is the actual result of this analysis, and it is the one
  plot the window does not show. It would also have made the 0.0075 ms default
  answer obvious on sight.
- Show τ_D in the browser rows (`m000.spc · b0 · GG_ACF · τ_D 0.87 ms`) so a
  user can scan for failed fits without clicking through 8 940 entries.
- Name the pair editor in the window: "FCS channel pairs (edit in *Setup ▸ FCS
  Definitions*)" plus a small ✎ button that opens it and a reload afterwards.
- Default **Padding ±[ms]** to 0 (or to a small multiple of the burst duration)
  and state in the tooltip what the padded photons do to the answer.
- Default the fit window to start above the afterpulsing region rather than at
  the first lag point, and mark curves whose fit has a negative amplitude or
  sits on a grid rail as failed instead of listing a number.
- The file list shows full absolute paths left-aligned, so all ten rows read
  identically (`/Users/…/data/bh_spc1…`) and the file name — the only part that
  differs — is the part clipped. Show the basename with the folder as tooltip.
- Report the curves that were dropped for too few photons ("531 of 609 curves;
  78 bursts had too few photons in one channel") instead of silently returning
  fewer rows.
- On the *Diffusion-time distribution* tab in Simple mode, say "MaxEnt only"
  rather than showing an empty plot; the tab's x-axis labels also collide
  around 10⁻⁴–10⁻³ ms.
- The label pair "FCS bins (B)" / "cascades" is inconsistently capitalised, and
  "bins" here means bins *per cascade* — worth spelling out in the tooltip,
  since the same numbers exist per pair in the FCS Definitions editor.

## Bugs filed

- RF-509 — the FCS pairs the window requires cannot be created from it, and it
  never says where they live.
- RF-510 — no export: the per-burst τ_D values cannot leave the window (the
  replaced wizard wrote `.td4`).
- RF-511 — the default fit window starts inside the afterpulsing spike: median
  τ_D wrong by ~100× on real bursts (the fit-internal half — unconstrained
  amplitude, edge-pinned τ_D — is already RF-504 / RF-505).
- RF-512 — the default ±100 ms padding makes 97 % of the correlated photons
  non-burst photons and changes τ_D 14×.
- RF-513 — the per-pair Bins/Cascades/Fine stored with each preset are ignored.
- RF-514 — the status-bar progress stays at "Computing burst-wise FCS… 100 %"
  after the run.
- RF-515 — MaxEnt mode blocks the GUI for minutes with one progress tick per
  file.
- RF-516 — `save_fcs_channel_setups` returns success while keeping setups that
  were removed from the payload.
