---
type: Reference
title: Use case — simulate a TCSPC decay and recover its lifetimes
description: Generate a synthetic decay with known lifetimes from the TCSPC Simulator setup, then fit it back and check that the fit returns the numbers that went in.
tags: [usecase, tcspc, simulation, fitting, lifetime, validation, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: simulate a TCSPC decay and recover its lifetimes

**Goal:** the validation loop every fitting program needs. Before trusting a
lifetime fit on real data, the user makes data whose answer they already know —
a bi-exponential decay with typed-in amplitudes and lifetimes, convolved with a
real instrument response and given Poisson shot noise — feeds it back through
the same *Lifetime* model they use on measurements, and checks that the fit
returns the numbers they typed. The same panel is how one produces teaching
data, a test case for a new model, or a decay to try a fit range on.

**Data:** none required for the simulation itself — the decay is typed in. To
convolve with a real instrument response and to fit the result properly, one
measured prompt is used: `test/data/tcspc/ibh_sample/Prompt.txt` (IBH text,
4094 channels, `dt = 0.0141` ns/ch, 10 MHz).

**Entry point:** *Read data* dock → **Experiment** `TCSPC` → **File type**
`Simulator` (reader `chisurf.core.experiments.tcspc.TCSPCSimulatorSetup`,
controller `TCSPCSimulatorSetupWidget`). There is no ribbon button and no
plugin — the simulator is a *file type*, which is where a user has to think to
find it.

## Steps

1. Start ChiSurf. In **Read data**, set **Experiment** = `TCSPC`,
   **File type** = `TXT/CSV`, *File parameters* `Skiprows = 11`,
   `dt = 0.0141` ns/ch, `rep. = 10` MHz, and load
   `test/data/tcspc/ibh_sample/Prompt.txt`. This is the instrument response;
   the simulator can only use an IRF that is already a dataset.
2. Set **File type** = `Simulator`. The *Decay-Parameter* panel appears with
   `Name`, `lifetime spectrum`, `n TAC`, `Peak count`, `dt [ns]`, an
   *Instrument response function* box and a *Simulation preview*.
3. Click **Select IRF** and pick `Prompt.txt` from the list. The label changes
   from *"IRF: Gaussian (no dataset selected)"* to the file's path. (Leaving it
   unset uses the Gaussian IRF defined by the **mean** / **sigma** boxes below.)
4. Type the ground truth into **lifetime spectrum** as interleaved
   `amplitude, lifetime` pairs — `0.75, 4.0, 0.25, 1.0` — and set `Name` =
   `Truth-x0.75t4.0-x0.25t1.0`, `n TAC` = 4096, `Peak count` = 20000,
   `dt [ns]` = 0.0141 (the same `dt` as the IRF, or the two axes do not line up).
5. Click **Simulate**. The preview draws the noisy decay (yellow) and the IRF
   (red) on a log axis.
6. Click **Add**. The decay is appended to the dataset list under `Name`.
7. Switch to the **Data** tab, select the simulated row, pick `Lifetime ` in the
   model combo and click **+ Analysis** (*Add fit*).
8. In the analysis dock, **Convolve** section, click **…** next to *IRF* and
   choose `Prompt.txt` — the same prompt the simulation used.
9. Click **Fit**. Read χ²ᵣ and `tL1`.
10. Click the green **add** button in the *Lifetimes* section to add the second
    component and click **Fit** again. Compare `xL1/tL1` and `xL2/tL2` against
    what was typed in step 4.

## Expected

- Step 5 produces integer photon counts peaking at `Peak count` at the IRF's
  own arrival time, with the prompt's features (here the reflection bump at
  ≈30 ns) visible in the decay.
- Step 9 with one component underfits by construction: χ²ᵣ ≈ 5, an average
  lifetime between the two true ones.
- Step 10 recovers the input: **τ = 4.0 / 1.0 ns and x = 0.75 / 0.25 with
  χ²ᵣ ≈ 1.0**. A round trip that does not return the input is a bug in the
  model, not in the data.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, isolated
`CHISURF_SETTINGS_DIR`) through the real main window — the experiment/setup
combo boxes, the simulator controller's own buttons, the dataset selector, the
model combo, **+ Analysis**, the `ConvolveWidget` IRF selector and
`FittingControllerWidget` — with screenshots read at each step.

**The round trip is exact.** Ground truth `x = 0.75 / 0.25`, `τ = 4.0 / 1.0 ns`
came back as **`xL2 = 0.7566`, `tL2 = 3.9948` ns, `xL1 = 0.2434`,
`tL1 = 1.0022` ns at χ²ᵣ = 0.9999, DW = 1.9801**, with flat weighted residuals
across the whole 525…2978 fit range. The one-component fit first gave χ²ᵣ = 5.36
at τ = 3.78 ns, so the second component is worth exactly what it should be.
Simulating 4096 channels took 0.75 s; the two-component fit 6.2 s. Using the
measured prompt rather than the Gaussian fallback carries the prompt's ≈30 ns
reflection into the simulated decay, which is what makes this a real test case.

**But only one of the panel's two "load" buttons produces that data.** The
panel sits under the standard *Read data* header, whose **+ Data** button is how
every other file type is loaded. Pressing **+ Data** with the Simulator selected
runs `TCSPCSimulatorSetup.read()`, which is a different generator: it ignores
**Peak count**, ignores the *Instrument response function* box entirely, and
applies no shot noise. The result is an amplitude-normalised curve with
`y.max = 1.0`, `Σy = 231`, and — because `counting_noise` floors zeros at 1 —
an error bar of 1.0 on the peak, i.e. errors larger than the data. The **Add**
button two rows below, with identical settings, produced `y.max = 20 150`
integer counts, `Σy = 5.1e6`, `ey = 142`. Both land in the dataset list under
the same name and the same *TCSPC* type, indistinguishable (RF-636).

**That curve cannot be fitted, and nothing says so.** `read()` sets `setup=`
but never `data_reader=`, so the curve reaches `imported_datasets` with
`data_reader = None` and the fit's auto-range never runs. The new fit window
opens showing *"Range 0, 0 · chi2r=-0.0000 · DW=0.0000"*, both range spin boxes
at 0, empty residual panels and **no data curve drawn at all** — only the model
line. **Fit** returns immediately, the status bar says *"Fitting finished!"*,
and every parameter is untouched (RF-637). Typing a range in by hand does not
rescue it: at range 10…3000 the same curve fits to **τ = 268 ns** and reports
**χ²ᵣ = 0.0002** while the weighted residuals run to 100 — a nonsense answer
wearing a perfect goodness-of-fit. The control in the same process (same RPC
transport, same model) fits the **Add** curve correctly, so this is the data,
not the harness.

**Two silent all-zero paths in the input handling.** `_parse_lifetime_spectrum`
drops non-numeric tokens without complaint: `abc, 4.0` becomes `[4.0]`, an
odd-length spectrum, which the generator turns into an all-zero decay — peak 0,
`Simulate` redraws nothing, `Add` still stores it (RF-638). Separately, an IRF
dataset whose x axis does not overlap the simulator's time axis is interpolated
to zeros with no warning: loading `Prompt.txt` at the reader's default
`dt = 1 ns/ch` gives x = 1…4094 while the simulator axis is 0…57.7 ns, so
`_build_irf` returns zeros and the "simulation" is an empty array that **Add**
happily adds as a dataset (RF-639). Both cases look exactly like "the button
did nothing".

**Dead buttons on empty input.** With the spectrum field cleared, **Simulate**
and **Add** each do nothing at all — no dialog, no status-bar text, no disabled
state; the dataset count stays where it was and the status bar still reads
*"Background startup complete."*

**Layout.** At the dock's natural width (≈520 px, screenshot
`01b_mainwindow_readdata`) the panel is cramped and then mostly empty: the
`lifetime spectrum` label butts against a ~110 px field that shows only the tail
of a four-number spectrum (`.1, 0.6, 4.1`), *"IRF: Gaussian (no dataset
select"* is cut off by the **Select IRF** button, the *"Gaussian IRF mean
[ns]:"* label is truncated to *"Gaussian IRF"* so its number has no name and no
unit, there is a blank band inside the *Instrument response function* group, and
the *Simulation preview* plot is squeezed into a ~90 px strip — y tick labels
overlapping into an unreadable smear, the axis title clipped to *"ts"* — above
~350 px of empty grey and a *"Drop files here."* prompt that means nothing for a
generator. Widened to ~720 px the same panel is legible and the preview is good.

## UX / UI suggestions

- **One generator, one button.** The panel should not contain two ways to make a
  decay that disagree. Either **+ Data** produces exactly what **Simulate** /
  **Add** produce, or the header's **+ Data** and *"Drop files here."* are hidden
  for the Simulator file type — there is no file to add.
- **Give the preview the space.** Drop the `preview_group` maximum height and let
  the plot take the empty area below it; at the dock's real width the plot is
  currently unreadable.
- **Label the Gaussian IRF fully** — *mean [ns]* and *sigma [ns]* — and elide the
  IRF dataset label from the left (`…/ibh_sample/Prompt.txt`) instead of letting
  the button cut it, so the file name stays visible.
- **The lifetime-spectrum field needs room and a format hint.** Interleaved
  `a₁, τ₁, a₂, τ₂ …` is not guessable from the label `lifetime spectrum`; put the
  convention and the unit (ns) in the placeholder and the tooltip, and give the
  field the width of the row.
- **Validate the spectrum as it is typed.** Colour the field on a non-numeric
  token or an odd number of values, and say *"needs amplitude/lifetime pairs"* —
  rather than silently simulating zeros.
- **Say something when a click does nothing.** Empty spectrum, non-overlapping
  IRF and an all-zero result should each produce one line in the status bar;
  today all three are indistinguishable from a frozen button.
- **Name the dataset for what it is.** Two entries called `SimA` with different
  content is the norm here, not an edge case. Append the spectrum (or an
  incrementing suffix) so the list distinguishes them.
- **Offer the Gaussian IRF as a dataset.** A user who simulates with the built-in
  Gaussian has nothing to assign in the fit's *Convolve* box, so the
  self-contained simulate-then-fit loop — the obvious first thing to try — cannot
  be closed without loading a measured prompt from disk. An "add IRF as dataset"
  checkbox next to **Add** would close it.
- **No way to save the simulated decay.** The panel can only push into the
  session; exporting the synthetic data (to hand to a colleague, or to a test
  suite) means going through a fit window.
- **`bg = -0.53508 ± 0.221 (41.3%)`** is reported in the *Info* tab of the
  otherwise perfect fit. A negative photon background is not a physical result;
  either bound it at zero or mark it as a free offset rather than a background.
- **The fit's IRF picker is a 256×192 frameless list** that truncates names to
  `Truth-…` and `Global …`, so the datasets it offers cannot be told apart — the
  same picker already crashes on the *Global Dataset* row (RF-015).

## Bugs filed

- RF-636 — `+ Data` and `Add` in the Simulator panel produce different data;
  `read()` ignores **Peak count**, the IRF and shot noise.
- RF-637 — the `+ Data` curve carries `data_reader = None`, so the fit opens at
  range (0, 0) with χ²ᵣ = -0.0 and **Fit** is a silent no-op.
- RF-638 — the lifetime-spectrum field silently drops non-numeric tokens and
  accepts an odd-length spectrum, producing an all-zero decay.
- RF-639 — an IRF dataset that does not overlap the simulator's time axis is
  interpolated to zeros; **Add** stores the empty decay as a dataset.
