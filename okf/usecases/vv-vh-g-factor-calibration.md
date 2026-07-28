---
type: Reference
title: Use case — VV/VH G-factor and l1/l2 detection calibration
description: Determine the detector G-factor by tail-matching a fast-rotating reference dye, subtract the background, estimate the channel-mixing l1/l2 from a slow-rotating sample, read r(t), and batch a folder of VV/VH files.
tags: [usecase, anisotropy, tcspc, calibration, g-factor, vv-vh, gui]
timestamp: '2026-07-29T00:00:00Z'
---

# Use case: VV/VH G-factor and l1/l2 detection calibration

**Goal:** measure the two numbers that every polarisation-resolved measurement in
ChiSurf silently assumes — the detection **G-factor** (the relative sensitivity of
the VH channel to the VV channel) and the **channel-mixing factors l1/l2** — from
reference measurements, and see the anisotropy `r(t)` they produce. Every
anisotropy fit, every `r∞`, and the *Corrections* page of the
[anisotropy wizard](/usecases/anisotropy-wizard-global-fit.md) takes `G`, `l1` and
`l2` as *given*; this is the window that produces them.

The method is tail matching. Long after excitation a **fast-rotating** dye has
fully depolarised, so the true `VV` and `VH` photon rates are equal and any
residual ratio in that tail is the detector's, not the sample's:
`G = ⟨VV⟩ / ⟨VH⟩` over a tail region. `l1`/`l2` describe the polarisation
scrambling of the objective and are estimated from a **slow-rotating** sample
whose steady-state anisotropy is predicted by the Perrin equation
`r_s = r₀ / (1 + τ/ρ)`.

**Where it lives:** *Spectroscopy → Fluorescence decay → VV/VH G-Factor
Calculator* (`vv_vh_g_factor`), also embedded as panel **5. VV/VH G-Factor** in
the *Decay Analysis* hub (`lifetime_analysis`). Headless: `csc vv-vh-g-factor
calculate`. Distinct from the neighbouring `vv_vh_anisotropy` plugin, which is
marked deprecated.

**Data (repo paths):**

- fast-rotating reference — `test/data/tcspc/Jordi/02_18-577+7.5uM(577)UP_8ps.dat`
  (2048 channels per polarisation, ~8 ps/channel, rise at ch 246, peak at ch 380)
- alternative reference — `test/data/tcspc/Jordi/H2O_8-0 ps_2048 ch.dat` (water scatter)
- slow-rotating "FP" sample — `test/data/tcspc/Jordi_PIE/Green_Donly_ps.dat`
  (1024 channels, ~32 ps/channel)
- synthetic smoke file — `chisurf/plugins/vv_vh_g_factor/test_vv_vh_data.dat`

## Steps

1. Open the calculator (standalone, or *Decay Analysis* → **5. VV/VH G-Factor**).
2. **Load VV/VH File** → the fast-rotating reference. The stacked file is split
   into its VV and VH halves and both are drawn on a log-intensity plot against
   the raw channel index. Two draggable regions appear: a **blue tail-matching
   region** (default 70–90 % of the record) and a **red background region**
   (default 5–15 %).
3. Drag the **blue** region into the clean exponential tail, past any residual
   anisotropy and short of the zero-padded end. Read **G-Factor** and **StdDev**;
   the plot overlays `VH × G` on `VV`, so a correct `G` makes the two tails lie on
   top of each other.
4. Tick **Background Correction**. Drag the **red** region into the pre-pulse
   baseline — the flat stretch *before* the decay rises. Read **BG Parallel** /
   **BG Perpendicular** and the **Corrected G-Factor**, which is the value the
   window then uses everywhere.
5. If the two detectors are not time-aligned, set **Shift Perpendicular Decay
   (channels)** and watch `G` and `r(t)` respond.
6. Use **Flip VV<->VH** if the file stores the perpendicular half first.
7. Read the right-hand panel: `r(t)` computed from the current `G`, `l1`, `l2`.
   A fast rotor should decay from `r₀` towards a flat plateau.
8. **Load FP VV/VH File** → the slow-rotating sample, to get `l1`/`l2`.
9. Set **dt [ns/ch]** to the file's real channel width, and **rho [ns]** / **r0**
   for the sample. The panel estimates **tau [ns]** (first moment of the total
   intensity), predicts **Target rS** from Perrin, and solves the linked
   `l1 = l2` that reproduces it from the measured VV/VH integrals.
10. Override **tau**, **Target rS** or **l1/l2** by typing into them if you know
    better; typed values win over the estimates.
11. **Batch...** → add a folder of VV/VH files, **Run Batch** to apply the current
    `G`, `l1/l2`, background and region settings to all of them, and **Save
    CSV...** to export `filename, r_inf, region_min, region_max, bg_vv, bg_vh,
    g_factor`.
12. Carry `G`, `l1`, `l2` to the *Corrections* page of the anisotropy wizard, or
    to a VV/VH fit's nuisance parameters.

Headless equivalent of steps 2–4:

```bash
csc vv-vh-g-factor calculate <file.dat> --region-min 1200 --region-max 1800 \
    --use-bg --bg-min 5 --bg-max 230
```

## Expected

- Step 3 returns `G` near 1 for a well-matched detection path, with the `VH × G`
  overlay lying on `VV` through the whole matching region.
- Step 4 reports a background equal to the **pre-pulse baseline** of each channel
  and leaves `G` essentially unchanged when that baseline is near zero.
- Step 7's `r(t)` decays monotonically from below `r₀ ≈ 0.4` and never goes
  systematically negative.
- Step 9 returns a physically possible `tau` (single-digit ns) and an `l1 = l2`
  in `[0, 0.5]`.
- Step 11 produces one row per input file, and says so when a file could not be
  processed.

## Observed (last run: 2026-07-29)

Driven offscreen (`QT_QPA_PLATFORM=offscreen`, arm64 env) against the real
`VvVhGFactorCalculator` and `VvVhDecayBatchWindow` widgets, with screenshots read
at every step. **The G-factor half works and is fast** — 2048 channels load and
recalculate in 0.08 s, each region drag is debounced into one 150 ms RPC round
trip, and the two-plot layout (decay overlay with both shaded regions, plus
`r(t)`) is genuinely clear. **The l1/l2 half does not run at all**, and the
background default is actively harmful.

- **Loading the FP file crashes, and the crash poisons the window.**
  `VvVhGFactorClient.solve_linked_l` computes its result into a local and then
  **falls off the end of the function without a `return`** — the next line is
  `def archive_g_factor`. It hands back `None`, the caller's fallback never fires
  (no exception was raised), and `np.isfinite(None)` raises
  `TypeError: ufunc 'isfinite' not supported for the input types`. Every press of
  **Load FP VV/VH File** dies there. Worse, the same call sits in
  `_apply_manual_g_from_text`, so once an FP file is on record **every later
  interaction** — typing in the G box, dragging a region, ticking a checkbox —
  raises the identical `TypeError`. Verified three times in one session
  (`06_fp_loaded.png`). The file path is written into the label, so the panel
  *looks* loaded while `tau`, `Target rS` and `l1/l2` all stay `0.000000` and the
  warning reverts to *"Load FP VV/VH data to estimate l1/l2."* See RF-918.
- **The default background region sits on the decay, not before it.** It is
  hard-coded to channels `[5 %, 15 %]` of the record, and every real VV/VH file in
  the repo has its rise before 15 %. On
  `02_18-577+7.5uM(577)UP_8ps.dat` the default window `[102, 307]` ends **61
  channels after** the rise at 246: the panel reports `BG Parallel 94.0098`,
  `BG Perpendicular 16.4732` where the true pre-rise baseline is `0.000 / 0.000`,
  and the *Corrected G-Factor* it then uses everywhere is **1.0048 instead of
  1.2866** (−22 %). On `H2O_8-0 ps_2048 ch.dat` the same default turns
  `G = 1.7418` into `G = 0.2173` — a factor of **8**. On the two 1024-channel PIE
  files the window `[51, 153]` straddles the peak at channel 54, so the reported
  background is `11948` and `27554` counts/channel against true baselines of `34`
  and `76`, ~350× too large. Nothing warns. The damage is visible in the
  screenshot without reading a number: with the shipped default the corrected
  `r(t)` plateau is **negative** across the whole tail (`04_bg_on.png`), while
  dragging the region back to `[5, 230]` restores `BG 0.0000 / 0.0000`,
  `G_corr = 1.2866` and a clean plateau at `r ≈ 0.15` (`11_bg_correct_region.png`).
  See RF-919.
- **The l1/l2 it determines never reaches the plot it is for.** Patching the
  missing `return` in the harness, the panel does compute a sensible
  `l1 = l2 = 0.1392` from `Green_Donly_ps.dat` at `dt = 0.032 ns/ch` and shows it
  in the form — while the `r(t)` legend beside it still reads
  `l1=0.0000, l2=0.0000` and the curve is the uncorrected one (`13_fp_dt.png`).
  Loading the FP file does not draw its decay either, although *Show slow dye* is
  ticked. Toggling **any** unrelated checkbox makes both appear at once — the same
  state then renders `l1=0.1392, l2=0.1392` with the slow curves present
  (`16_after_toggle.png`). `_set_fp_outputs` updates the model and never calls
  `update_plot`/`update_rt_plot`; only the *manual* l1 path does. See RF-920.
- **Batch turns two different failures into the same silent `nan`.** Running the
  batch over the 2048-channel reference, an unreadable text file and the
  1024-channel PIE file with a tail region of `1200–1800` gives three rows and the
  message *"Processed 3 file(s)."*: the good file returns `r_inf = 0.2544`; the
  unreadable file returns `nan` while still carrying the **previous** file's
  `bg_vv = 94.0098`; and the short file has its region clamped to
  `region_min = region_max = 1023.0` and returns `nan`. A region that does not
  exist in a file is not a result — it is a configuration error, and it is
  reported as neither (`15_batch_run.png`, `17_batch_bad.png`). See RF-921.
- **The batch table cannot display its own numbers.** All seven columns are set to
  `QHeaderView.Stretch` and filled with full-precision `str(float)`, so in the
  shipped 1000 px dialog `r_inf` renders as `0....` and `g_factor` as `1....` —
  the two columns the window exists to produce. Only *Save CSV...* recovers them.
  See RF-922.
- **The CLI's error paths are broken.** `cli/__init__.py` calls `sys.exit(1)`
  twice but never imports `sys`: `--use-bg` without `--bg-min/--bg-max` raises
  `NameError: name 'sys' is not defined` instead of the message directly above it.
  An unreadable file never even reaches that handler — `read_vv_vh` returns two
  **empty arrays** without raising, so the guarded `try` passes and the run dies
  in numpy with `ValueError: attempt to get argmin of an empty sequence`. The
  happy path is correct and matches the GUI digit for digit
  (`g_factor = 1.2865870347614639`). See RF-923.
- **`dt [ns/ch]` defaults to 1.0 and nothing sanity-checks what follows.** At the
  shipped default the panel reports `tau = 170.5105 ns` for a real donor decay and
  carries it into Perrin and the `l1` solve without comment; the resulting
  `l1 = −2.29` *is* caught by the range guard, but the impossible lifetime that
  produced it is not. Setting the file's real `0.032 ns/ch` gives
  `tau = 5.4563 ns`, `rS = 0.2834`, `l1 = 0.1392`. See RF-924.
- **Nothing leaves the window except the batch CSV.** The window has exactly two
  buttons and four checkboxes; there is no *Save*, no *Apply to fit*, no
  *Archive*. `vv_vh_g_factor.archive_g_factor` exists as an RPC, is implemented,
  is tested (`test/test_calib_provenance.py`) and is wired into the client — and
  the **only** caller in the tree is the channel-definition wizard. A user who
  calibrated `G` here re-types it into the anisotropy wizard by hand. See RF-925.
- **Already on record, reconfirmed and extended.** `G` is the *mean of per-channel
  ratios* and *StdDev* is the spread of that population (RF-173). Two further
  symptoms this run: on 600 channels of the reference, `StdDev = 0.159876` while
  the standard error of the mean is `0.006527` — the displayed uncertainty is
  **24× too large** — and the estimator is not self-consistent under the panel's
  own **Flip** control: `G = 1.2866` unflipped but `0.7875` flipped, where
  `1/1.2866 = 0.7773`. Which half of the file you call "parallel" moves the
  calibration by 1.3 %. Ratio-of-sums over the same region is `1.2684`.

## UX / UI suggestions

- **Place the default background region from the data, not from the record
  length.** The rise channel is one `np.argmax`/threshold away; anchoring the red
  region to `[0, rise − margin]` would make the shipped default correct on all
  four repo files instead of wrong on all four. Failing that, refuse to apply a
  background sampled from a window whose mean exceeds the record's minimum by
  orders of magnitude, and say so.
- **Say what *StdDev* is.** Label it *"SD of per-channel ratios"* and show the
  standard error and the channel count beside it, so `1.2866 ± 0.0065 (n = 600)`
  is what the user copies rather than `1.2866 ± 0.1599`.
- **The r(t) panel wastes three quarters of its height.** It is fixed to
  `−0.5 … 1.5` while physical anisotropy is bounded by `r₀ ≈ 0.4`; the prompt
  spike that needs the headroom is an artefact. Auto-range on the matching region,
  or default to `−0.1 … 0.45` with an expand control.
- **The legend covers the data.** With a slow dye loaded the decay plot draws
  eight legend entries directly over the peak (`08_slow_on.png`). Move it outside
  the axes or make it collapsible.
- **The fast and slow files share one channel axis and one pair of region
  selectors, and they should not.** A 2048-channel 8 ps file and a 1024-channel
  32 ps file are overlaid on the raw channel index, so the tail region set for one
  is off the end of the other and the background region set for one lands on the
  other's peak. Convert both to nanoseconds via their own `dt` and give the FP
  file its own background region.
- **`dt [ns/ch] = 1.000000`, `tau = 0.000000`, `Target rS = 0.000000` and
  `l1/l2 = 0.000000` are placeholders that look like values.** Blank them or grey
  them until a file is loaded, and flag a `tau` that is not physically possible.
- **Explain "FP".** *Load FP VV/VH File* is the only place the abbreviation
  appears; it means the slow-rotating reference (fluorescence-polarisation
  standard). Rename to *Load slow-rotating reference* and put the abbreviation in
  a tooltip.
- **No control in the window carries a tooltip** (`grep -c toolTip wizard.ui` →
  `0`), including `rho`, `r0`, `Target rS` and `l1/l2`, which are the four a user
  is least likely to know. Long help behind a `?` section would fit the pattern
  the rest of ChiSurf uses.
- **The G-Factor box re-selects its own text after every recalculation**
  (`selectAll()` in `calculate_g_factor`), so it renders highlighted and the next
  keystroke replaces the calibration rather than editing it.
- **Give the calibration somewhere to go.** A *Send to fit* / *Archive to MMFDB*
  button would close the loop into the anisotropy wizard and the channel
  definition, which already consume exactly these numbers.

## Bugs filed

- RF-918 — `VvVhGFactorClient.solve_linked_l` has no `return`; loading an FP file
  raises `TypeError` and every later interaction with the window raises it too.
- RF-919 — the default background region is sampled from the decay, not the
  baseline; the corrected G-factor is wrong by 22 % to 8× on every repo file.
- RF-920 — the determined `l1/l2` and the loaded FP decay do not reach the plots
  until an unrelated checkbox is toggled.
- RF-921 — batch writes indistinguishable silent `nan` rows for an unreadable file
  and for a region outside a file, and reports success.
- RF-922 — the batch table's columns are too narrow to show any of its numbers.
- RF-923 — the CLI uses `sys.exit` without importing `sys`, and an unreadable file
  bypasses its error handling entirely.
- RF-924 — `dt [ns/ch]` defaults to 1.0 and a 170 ns "lifetime" is accepted
  without a plausibility check.
- RF-925 — the calibrated G-factor cannot leave the window; the archive RPC that
  exists for it has no caller here.
- RF-173 (existing, reconfirmed) — `G` is a biased mean of per-channel ratios and
  *StdDev* is the population spread; new evidence: the SEM is 24× smaller, and
  `Flip` does not return `1/G`.
