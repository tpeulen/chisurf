---
type: Reference
title: Use case — planning a raster scan (which dwell time measures D best?)
description: Predict, from the intended settings alone, how precisely a RICS acquisition would measure a diffusion coefficient, and sweep the pixel dwell time for the one that measures it best.
tags: [usecase, rics, ics, imaging, calculators, planning, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: planning a raster scan — which dwell time measures D best?

**Goal:** the one workflow that happens *before* the microscope time is spent.
A raster-image-correlation (RICS) measurement has a scan speed, and the choice
is not free: scan too fast and the molecule has barely moved between
neighbouring pixels, so the correlation carries almost no information about `D`;
scan too slowly and it has decorrelated before the next pixel is read. The user
wants to know, from the settings they *intend* to use and the `D` they *expect*,
whether the planned acquisition can resolve that `D` at all — and which pixel
dwell time would measure it best.

**Data:** none. Like the [FRET calculators](/usecases/fret-calculators.md), this
is a planner: it answers from the intended settings alone. The estimator is a
port of the MIA `RICSPE` reference (`chisurf/core/experiments/ics/precision.py`,
Sanguigno et al.'s treatment of RICS estimator noise), pinned against it by
`test/experiments/test_ics_precision_vs_pam.py`.

## Steps

1. Open **Tools ▸ Calculators** on the ribbon and pick **📐 RICS precision**
   from the left-hand list. (It also opens standalone as
   *Main ▸ Tools ▸ RICS-Precision*.) The panel comes up with a typical confocal
   acquisition already filled in: `D = 10 µm²/s`, 50 molecules, 100 kHz/molecule,
   `w_r = 0.25 µm`, `w_z = 1.25 µm`, 50 nm pixels, 8 µs dwell, 64 × 64, 100 frames.
2. Press **?** at the right of the toolbar for the theory — why the trade-off has
   a minimum, and the error → verdict table (below 5 % good, 5–20 % usable,
   20–50 % poor, above 50 % unusable).
3. Fill in the **Sample** panel: the `D` you expect (literature value or a
   guess), the number of molecules in the illuminated region, and the molecular
   brightness in kHz.
4. Fill in **Optics**: measured `w_r` / `w_z`, the pixel size, and tick
   **Membrane (2-D)** for a surface measurement.
5. Fill in **Scan**: the dwell time you plan to use, the line overhead (1.2 =
   20 % flyback), the image size and the number of frames.
6. Optionally expand the collapsed **Estimator** panel and raise *Repeats* from
   40 (the prediction carries ~1/√(2N) of its own uncertainty) or *Lags fitted*
   from 4 (cost grows as the fourth power).
7. Click **▶ Predict**. The status bar counts through the swept dwell times
   (`15.8 µs (44 %)` …) and ends on a one-line verdict.
8. Read the **Error vs dwell** plot: the predicted relative error on `D` against
   pixel dwell, log–log, with your own setting marked as an orange diamond.
9. Switch to the **Numbers** tab for the dwell / line / frame times and the
   error behind each point.
10. Click **💾 Export CSV** to save the swept prediction.

The same prediction is available headlessly:
`rics-precision 10 --pixel-time 8 --nx 64 --ny 64 --frames 100 --seed 1`.

## Expected

- At the shipped defaults the curve has a clear trough: 107 % at 0.5 µs, falling
  to **2.4 % at 15.8 µs**, rising again to 8.5 % at 211 µs.
- The status line reads *"At 8 µs: 3.3 % error (good) — about 1.4x worse than the
  best dwell (15.8 µs)."*
- A slower sample moves the optimum later (2-D, `D = 0.5 µm²/s` → best at
  211 µs, 1.3 %); a faster one moves it earlier (`D = 300 µm²/s` → best at
  37.5 µs, 5.7 %).
- The frame time column is what makes the trade-off concrete: a slower scan is
  also a longer acquisition.
- The numbers must agree with the CLI for the same settings and seed.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`) through the Calculators hub and
then standalone; screenshots inspected at every step.

**The estimator itself is right, fast and well presented.** A default prediction
takes **0.9 s** (9 dwell times × 40 Monte-Carlo realisations), 4.2 s at 400
repeats, 2.2 s at `n_lags = 8`. The sweep runs on a worker thread with a real
progress readout in the status bar (`0.5 µs (0 %)` → `done (100 %)`), so the
panel never freezes. Closing the window mid-prediction was survived cleanly. The
error values reproduce the CLI **exactly** at the same seed
(107.3 / 35.0 / 8.0 / 3.9 / **2.4** / 3.0 / 4.5 / 8.4 / 5.6 %), and the physics
behaves: the optimum moves later for slow samples and earlier for fast ones, and
a 1 kHz label is correctly called unusable. The layout is clean, every input
carries a tooltip, the collapsed *Estimator* panel expands on click, and the **?**
opens a properly rendered, scrollable help modal.

What a user gets wrong anyway:

- **The frame time is reported in seconds under a millisecond header** — in the
  *Numbers* table and in the exported CSV, both 1000× too small (RF-793). The
  CLI, from the same view model's settings, prints the same rows correctly:
  where the CLI says `frame/ms = 77.7`, the GUI table says `0.08`. The four
  fastest rows collapse to `0.00` / `0.01`, so a planner reading the panel
  concludes a 100-frame acquisition costs 8 ms when it costs 7.8 s. The frame
  time is the *only* number in the panel that prices the trade-off the tool
  exists to expose.
- **A failed prediction says "Prediction failed" and nothing else** (RF-794).
  Setting the image to 8 × 8 at the default 4 lags is a plausible thing to try;
  the model computes the complete diagnosis — *"n_lags=4 is too large for a 8x8
  image: the covariance needs 2 \* n_lags < min(nx, ny), so at most n_lags=3"* —
  and the window throws it away, leaving the two useless words in the status bar
  and an empty table (screenshot `07_small_image.png`). Lowering *Lags fitted* to
  3 fixes it immediately, but nothing on screen says so.
- **The "best dwell" is silently the edge of a hard-coded range** (RF-795). The
  sweep is fixed at 0.5 µs – 0.5 ms with no way to change it from the GUI. For a
  dim label (1 kHz) and for a slow membrane protein (`D = 0.02 µm²/s`) the curve
  falls **monotonically across the whole range** — there is no trough at all
  (screenshot `31_edge_pinned_slow.png`) — and the tool still reports *"about
  30.7x worse than the best dwell (500 µs)"*. 500 µs is not the optimum; it is
  the last point that was tried.
- **The log y-axis carries a linear `×1e+09` scale factor** when the errors span
  many decades (RF-796). In the dim-label case the axis reads
  `predicted error / % (x1e+09)` with ticks running `10¹ … 10⁻⁸`, so the user's
  own marked setting reads as ≈ 0.06 when the value is 5.7 × 10⁷ %
  (screenshot `30_edge_pinned_dim.png`). The reader has to multiply a
  logarithmic tick by a linear prefix.
- **The curve's slow end reproducibly turns back down**, contradicting the
  tool's own help (RF-797). At the shipped defaults 211 µs → 8.4 % but 500 µs →
  5.6 %, and it survives ten times the Monte-Carlo sampling (400 repeats:
  8.2 % → 6.7 %, a ~5σ move against the estimator's own ~3.5 % uncertainty),
  while the help modal and the plot description both state that the curve
  "rises at both ends" and that the useful region is the trough.

Screenshots: `01_hub_opened`, `03_predicted_defaults` (the good case),
`04_numbers_tab` (the frame-time bug), `07_small_image` (the lost diagnosis),
`30_edge_pinned_dim`, `31_edge_pinned_slow`, `41_help_0`.

## UX / UI suggestions

- **Show the total acquisition time, not just the frame time.** Frame × *Frames*
  is the number a user is actually trading against precision; at the defaults it
  is 7.8 s, and today the panel makes the reader multiply two numbers, one of
  which is in the wrong unit.
- **Mark the best dwell on the plot.** Only the status sentence names it; a
  second marker (or a vertical line) next to the "your setting" diamond would
  make "how far am I from the optimum" a glance rather than a subtraction.
- **Cap the displayed precision of absurd errors.** `57086768.4 % error` and
  `about 3926163.3x worse` are eight significant figures of a number that only
  means "hopeless"; `> 1000 %` and `≫ 100x` would read better and are equally
  informative.
- **Let the dwell range be set.** Two of the sample types tried here (a dim
  label, a slow membrane protein) want dwell times beyond 0.5 ms, and the panel
  can neither explore them nor say that it cannot. Low/high/points fields beside
  the *Estimator* group would cost three rows.
- **The Error [%] column takes all the leftover width.** Its declared width is
  110 px like the others, but as the last column it stretches to ~450 px while
  the three informative ones stay cramped at the left (screenshot
  `04_numbers_tab.png`). Add a trailing stretch column or stop stretching the
  last one.
- **The empty plot before the first Predict shows decade axes labelled 2…9**,
  which reads like a result rather than "nothing computed yet". A placeholder
  line ("press ▶ Predict") inside the axes would be clearer than relying on the
  status bar.
- **`D` is the input a planner is least sure of.** The help says so
  ("the best settings depend on the answer you do not have yet"); the panel could
  act on it by sweeping two or three `D` values at once, or by reporting how far
  the optimum moves for a factor-of-two error in `D`.

## Bugs filed

- RF-793 — the *Numbers* table and the exported CSV report the frame time in
  seconds under a `[ms]` header (1000× low); the CLI is correct.
- RF-794 — a failed prediction discards the model's diagnosis and shows only
  "Prediction failed".
- RF-795 — an optimum at the edge of the hard-coded 0.5 µs–0.5 ms sweep is
  reported as "the best dwell" with no indication that the range was not
  bracketed, and the range cannot be changed.
- RF-796 — the log-scaled error axis applies a linear `×1e+09` unit prefix, so a
  marked value reads three orders of magnitude away from its number.
- RF-797 — the predicted error reproducibly falls again at the slow end of the
  sweep, contradicting the shipped help text and plot description.
