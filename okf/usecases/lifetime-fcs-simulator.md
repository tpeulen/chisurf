---
type: Reference
title: Use case — Lifetime-FCS (FLCS) simulator
description: Simulate two diffusing species with distinct fluorescence lifetimes (and optional interconversion) and recover them by lifetime-filtered correlation — the ground-truth loop behind every filtered-FCS measurement.
tags: [usecase, fcs, flcs, filtered-fcs, simulation, lifetime, gui]
timestamp: '2026-07-29T00:00:00Z'
---

# Use case: Lifetime-FCS simulator — does FLCS really separate the species?

**Goal:** filtered FCS (FLCS) claims that two species which are *spectrally
identical* but differ in fluorescence lifetime can be separated into their own
correlation curves — and that their interconversion shows up as a rising
species **cross**-correlation. Both claims are hard to check on real data,
because no real sample has a known answer. The Lifetime-FCS simulator supplies
that answer: it generates a photon stream of diffusing species with lifetimes,
diffusion coefficients and an exchange rate **you** set, builds the lifetime
filters from the ground-truth species decays, and shows the filtered
auto-/cross-correlations. If the recovered τ_D matches the `D` you typed and the
cross-correlation amplitude tracks the `k` you typed, the method works — and you
have learned to read the plot before you meet a real sample.

It is the validation companion to the two measured halves of the same window:
the [filter calculator](/usecases/ffcs-filter-calculator.md) (which derives the
filters from measured pure-species decays) and the
[FCS correlator](/usecases/fcs-correlate-tttr.md).

**Data:** none — the tool is self-contained. The photon stream comes from
`tttrlib`'s `SimEngine` through
`chisurf/core/fluorescence/fcs/simulate.py::simulate_lifetime_fcs`; the worked
non-GUI equivalent is `examples/lifetime_fcs.py`.

## Steps

1. Open the **FCS** window (*Spectroscopy ▸ Fluorescence Correlation
   Spectroscopy*). The left rail shows the five correlator steps, then a
   **Tools** separator, then the optional tools.
2. Click **🧬 Lifetime-FCS Sim** under *Tools*. A red experimental banner
   appears across the top: *"Lifetime-FCS simulator: a synthetic-data
   teaching/validation tool. The recovered curves depend on the simulated
   statistics."*
3. **Species (lifetime + diffusion)** — set the two species. Defaults are
   τ₁ = 1.000 ns / D₁ = 8.0000 µm²/ms and τ₂ = 4.000 ns / D₂ = 0.5000 µm²/ms:
   a short-lifetime fast diffuser and a long-lifetime slow one, i.e. the easy
   case where lifetime *and* diffusion separate the species. Each `D` tooltip
   states the relation you will check against: `τ_D = w₀²/(4·D)`.
4. **Kinetics / statistics** — leave **k (1/ms)** at 0.000 for the first run
   (static, independent species), keep **Photons** at 400000 and **Seed** at 1.
5. Press the green **Simulate + Correlate**. The window freezes for ~5 s at the
   default budget (RF-943) and then draws three curves.
6. Read the plot: two auto-correlations (blue = species 1, red = species 2) and
   one cross-correlation (green), legend-named by the input lifetimes
   (`τ=1 ns × τ=1 ns`, `τ=4 ns × τ=4 ns`, `τ=1 ns × τ=4 ns`). Check that each
   auto-correlation decays at the τ_D its `D` predicts, and that the
   cross-correlation is **flat at the baseline** — static species must not
   cross-correlate.
7. Read the status line under the button: `N species correlation(s); filter
   condition number C.C`. `C` is the conditioning of the lifetime-filter
   inversion — small (≈ 1–5) means the two decays are well separated, large
   means the decomposition is noise. **The second line of this label is clipped
   and the condition number is the part you cannot read** (RF-941).
8. **Now switch the exchange on.** Set **D₂ = 2.0000** and **D₁ = 2.0000** so the
   two species diffuse identically (the `k` tooltip advises exactly this — it
   isolates the kinetics in the cross-correlation), then set **k (1/ms)** to
   5.000 and press **Simulate + Correlate** again.
9. The two auto-correlations now lie on top of each other (same `D`), and the
   green cross-correlation lifts off the baseline at short lag and relaxes back
   into it — that rise *is* the interconversion. Sweep `k` and watch the
   amplitude grow.
10. There is nothing else to press: the panel has no save, no export and no
    "push to ChiSurf" (RF-946).

## Expected

- Each species auto-correlation decays at `τ_D = w₀²/(4·D)` with the hard-coded
  beam waist `w₀ = 0.3 µm`, so D = 8 µm²/ms → 2.8 µs, D = 0.5 → 45 µs,
  D = 2 → 11.2 µs.
- With `k = 0` the species cross-correlation is flat at G = 1.
- With `k > 0` and equal `D`, the cross-correlation amplitude grows
  monotonically with `k`.
- The filter condition number is small (a few) when the two lifetimes differ,
  and large when they do not.
- A change of **Seed** produces a *different* realisation of the same physics.

## Observed (last run: 2026-07-29)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`) through the real `FcsTool`
window: nav click → `LifetimeFcsSimWidget` → form spin boxes → the
`Simulate + Correlate` button, screenshots at each step.

**The physics is right, and it is the best part of the tool.**

| what | measured | expected |
| --- | --- | --- |
| τ_D, species 1 (D = 8 µm²/ms) | 4.4 µs half-decay | 2.8 µs |
| τ_D, species 2 (D = 0.5 µm²/ms) | 47.2 µs | 45.0 µs |
| τ_D, both species at D = 2 µm²/ms | 11.2 / 13.6 µs | 11.2 µs |
| cross-correlation, k = 0 | amplitude −0.027 (flat) | 0 |
| filter condition number, τ = 1 vs 4 ns | 3.3 | small |
| filter condition number, τ₁ = τ₂ = 4 ns | 92.0 | large |

The exchange sweep (D₁ = D₂ = 2 µm²/ms, 600 000 photons) is textbook — the
species cross-correlation excess over its own baseline rises monotonically with
the rate, while the k = 0 control stays flat:

| k (1/ms) | 0 | 1 | 2 | 5 | 20 | 50 |
| --- | --- | --- | --- | --- | --- | --- |
| cross-correlation excess (5–50 µs) | −0.027 | 0.107 | 0.196 | 0.516 | 1.539 | 2.572 |

Everything around that is weaker.

- **The Seed control does nothing.** Seeds 1, 2, 7 and 12345 produce a
  **byte-identical** photon stream — same photon count, same macro-times, same
  micro-times, same per-species counts. The simulator writes `"seed"` into the
  `SimEngine` settings, but the engine's config schema names its two RNG streams
  `seed_diffusion` and `seed_emission`; the unknown key is ignored and both
  engines stay on their defaults forever. Both sibling simulators in the same
  tree already pass the right keys. So a tool whose own banner warns that "the
  recovered curves depend on the simulated statistics" can never show a user a
  second realisation. **RF-940.**
- **The one line of feedback is cut in half.** The status label needs two
  wrapped lines (40 px) and is given 25 px, so every run reads
  `3 species correlation(s); filter condition` / `number 3.3` with the second
  line sliced by the bottom of the *Run* box. The clipped half is the condition
  number — the only quality metric the tool produces. **RF-941.**
- **Set τ₁ = τ₂ and the tool decomposes one species into three curves without a
  word.** At τ₁ = τ₂ = 4 ns the filter matrix is singular: condition number 92,
  two "auto"-correlations of one physical species at G(0) = 10.9 and 9.3, a
  spurious "cross"-correlation at 8.4, and ±50 noise across the plot — and all
  three legend entries read the same string, `τ=4 ns × τ=4 ns`, so the curves
  cannot even be told apart. The status line reports "3 species
  correlation(s)" exactly as it does for a good run, and the number that would
  have warned you is the clipped one. **RF-945.**
- **The lag axis runs past the end of the measurement.** The correlator settings
  are hard-coded (`n_bins = 8, n_casc = 25`), giving 200 channels out to
  26 840 ms whatever the photon budget. At the form's *minimum* budget
  (50 000 photons = a 10.7 s measurement) the last 12 channels sit at lags up to
  **2.5× the measurement duration** and come back as G = 0 and G = −3.99; the
  plot autoscales y to include them, so the far right of the picture is a spike
  to −4.5 (`06_tau_extremes.png`). Meanwhile everything informative lives below
  1 ms and occupies the left ~45 % of a 9-decade axis. **RF-942.**
- **The τ range and the excitation period contradict each other.** The spin box
  accepts τ up to 50 ns; the simulator's laser period is a hard-coded
  2048 × 0.016 ns = **32.77 ns**, and neither the period nor the TAC axis is
  exposed anywhere in the form. At τ₂ = 50 ns the decay wraps into a near-flat
  pattern: mean micro-time 14.63 ns and a first/last-decile ratio of 1.77
  against 29 879 for the 1 ns species. The tool reports condition number 1.1
  and "3 species correlation(s)" and draws a confident plot. **RF-944.**
- **The run blocks the window and never says so.** `simulate()` runs on the UI
  thread: 0.61 s at 50 000 photons, 4.75 s at 400 000, 17.6 s at 1.5 M — and the
  form permits **20 M**, extrapolating to ~4 minutes of a frozen window with no
  progress, no cancel and no busy cursor. The busy cursor that was meant to be
  there is a no-op: `window.setCursor(window.cursor())` sets the cursor to its
  own current value (verified: shape stays 0/Arrow, never 3/Wait). The CLSM
  Generator, one shelf over, runs the same kind of job on a worker thread.
  **RF-943.**
- **Nothing can leave the panel.** No save, no export, no push. When `run()`
  returns, the model keeps only `datasets`, `reference_decays` and
  `condition_number`; the simulated photon stream itself is discarded — even
  though the *Filter Calc*, *Correlator* and *FCS Merger* panels a few rows up
  the same rail are exactly the tools that would consume it as ground truth.
  **RF-946.**

Screenshots (scratch, not committed): `02_lfcs_panel_defaults.png` (clean
two-column form, empty plot), `03_after_simulate.png` (the two separated
species + flat cross-correlation, clipped status), `05_degenerate.png`
(τ₁ = τ₂: three identically-named noise curves), `06_tau_extremes.png` (the
negative spike past the end of the measurement), `08_final_exchange.png` (the
exchange cross-correlation).

## UX / UI suggestions

- **Show the parameters the answer actually depends on.** `w₀ = 0.3 µm`, box
  1.5 × 1.5 × 3 µm, population 1.5 molecules per species, brightness 120 cps,
  background 2 cps, 2048 TAC channels at 0.016 ns — all hard-coded and invisible,
  yet they are what set G(0) ≈ 17 and every τ_D the user is asked to check. At
  minimum print them in a read-only *Assumptions* info line; better, expose w₀
  and the TAC axis, since the τ_D formula in the tooltip is unusable without w₀.
- **Say what the condition number means.** A bare "3.3" teaches nothing. Colour
  it (green < 10, amber < 50, red beyond) and add one clause — *"well
  conditioned: the two decays are separable"* / *"ill-conditioned: the species
  separation is noise"*. This is the tool's only quality readout.
- **Warn when the two species are not separable** before spending the
  simulation: if |τ₁ − τ₂| is below roughly the TAC resolution times a few
  channels, say so next to the button rather than returning three identical
  curves.
- **Make the legend unique.** Name the curves by species index as well as
  lifetime (`species 1 (τ=4 ns) × species 1`), so the degenerate case is still
  readable.
- **Default the x range to the informative decades** (say 10 µs → 10× the
  slowest τ_D) instead of autoranging over 9 decades of empty correlator
  channels, and drop channels whose lag exceeds the measurement duration rather
  than plotting G = 0 and G = −4 beside a curve whose baseline is 1.
- **Add an overlay of the expected curve.** The whole point is validation: draw
  the analytic 3-D-Gauss `G(τ)` for the `D` (and the exchange relaxation for the
  `k`) the user typed as a dashed line under each simulated curve. Then the tool
  answers its own question on screen instead of asking the user to do arithmetic
  from a tooltip.
- **Move the legend off the data** — it currently overlaps the top of both
  auto-correlations at their most interesting point.
- **The empty plot before the first run** shows a log axis ticked 2…9 with no
  decade, which reads as broken. Show a placeholder line of text instead.
- **The shell's `Next ▶` tooltip is wrong here** — it promises "Process all
  loaded files in this step, then go to the next step" on a panel that has no
  files; it does navigate correctly (to *Burst-wise FCS*). Tools below the
  *Tools* separator are not pipeline steps and should not offer pipeline verbs.

## Bugs filed

- RF-940 — the **Seed** control has no effect; every run returns the same
  realisation (wrong `SimEngine` config key).
- RF-941 — the status line is clipped, hiding the filter condition number.
- RF-942 — hard-coded 25 cascades put 200 lag channels out to 26.8 s regardless
  of the measurement length; channels past the end of the data are plotted as
  G = 0 / G = −4 and drag the y range.
- RF-943 — the simulation blocks the UI thread (up to ~4 min at the permitted
  photon budget) with no progress, no cancel, and a no-op busy cursor.
- RF-944 — the τ spin boxes accept lifetimes up to 50 ns against a hard-coded
  32.77 ns excitation period; a wrapped decay is simulated and reported as
  normal.
- RF-945 — τ₁ = τ₂ yields three identically-named curves from one physical
  species with no warning.
- RF-946 — the simulated stream and the recovered curves cannot leave the panel.
