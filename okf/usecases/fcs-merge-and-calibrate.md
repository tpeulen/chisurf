---
type: Reference
title: Use case — merge repeated FCS runs, then turn τ_D into D, r_h and a concentration
description: Average a folder of repeat correlation curves into one .cor with per-point errors, push it into ChiSurf, and use the confocal diffusion/volume calculator to calibrate Veff on a reference dye and convert the fitted diffusion time of an unknown sample into a diffusion coefficient, a hydrodynamic radius and a concentration.
tags: [usecase, fcs, correlation, merge, calibration, diffusion, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: merging FCS repeats and calibrating the confocal volume

**Goal:** the two steps that bracket
[the FCS diffusion fit](/usecases/fcs-diffusion-fit.md) and that nothing else in
the suite does.

*Before the fit:* an FCS measurement is never one 10-minute correlation — it is
ten 1-minute repeats, so that a curve ruined by an aggregate or a bleaching event
can be thrown away and so that the scatter **between** repeats supplies the
per-point error bars a weighted fit needs. The **FCS-Merger** turns that folder
of chunks into one `.cor` carrying `y ± ey`.

*After the fit:* the fit returns a **diffusion time τ_D in µs**, which is a
property of the instrument as much as of the molecule. Nobody publishes τ_D. The
**Diffusion/Volume calculator** closes the loop that makes it physical: measure
τ_D of a dye whose **D is known** (Rhodamine 110, 470 µm²/s at 25 °C), which
fixes the effective volume *Veff* and the beam waist of *this* microscope on
*this* day; then hold that volume fixed and read the unknown sample's D, its
hydrodynamic radius r_h through Stokes–Einstein, and — from the fitted G(0) =
1/N — its absolute concentration in nM.

**Data used this run:**

* `test/data/fcs/kristine/Kristine_with_error.cor` and
  `Kristine_without_error.cor` — copied into one scratch folder to stand in for a
  chunk folder. 207 lag channels, duration 58.66 s, count rate 18.264 kHz. The
  two files carry the same `y`, which is what made the merge arithmetic easy to
  check exactly.
* The MMFDB reference-dye table behind the calculator's dye combo — 16 species
  with a `d25_um2_s` (ATTO 488/655, Alexa 633/647, Cy5, Fluorescein, Oregon Green
  488, Rhodamine 110/123, BSA, …), each citing Kapusta (2010), PFG-NMR.

**Tools:**

* *Spectroscopy → Fluorescence Correlation Spectroscopy → FCS-Merger*
  (`chisurf/plugins/fcs/fcs_merger`, a one-page `QWizard` around the shared
  `WizardFcsMerger`). Headless equivalents: the `fcs_merger` CLI and the RPC
  methods `fcs_merger.merge_folder` / `.parse_folder` / `.average`, all thin
  wrappers over `chisurf.core.fluorescence.fcs.merge`.
* *Spectroscopy → Fluorescence Correlation Spectroscopy → Diffusion/Volume
  Calculator* (`chisurf/plugins/fcs/fcs_calculator`, `ConfocalCalcWidget`) — an
  `AutoForm` over `fcs_calculator.view.json` with four custom sections
  (constraint radios, reference dye, molecular shape, settings JSON). Headless:
  the `fcs_calculator` CLI and `fcs_calculator.compute`.

## Steps

### A. Merge the repeats

1. Open **FCS-Merger**. One wizard page, *Correlation merging*: a path box with
   **help** and **clear** buttons, a read-only **Target** box with **save**, a
   five-column table (*Use, File, CR A (kHz), CR B (kHz), Duration (s)*) and two
   plots — the individual curves on the left, the merged mean on the right.
2. **Drop the chunk folder** on the path box (or type it). Every `.cor` and
   legacy `.json.gz` in the folder is read, one table row each, all ticked, and
   both plots draw immediately. The **Target** box fills in with the file that
   **save** will write: `<folder>.parent / <folder-name>.cor` — i.e. *beside* the
   folder, not in it, and not editable.
3. **Triage.** *Double-click a row* to untick it — the curve turns dashed grey in
   the left plot and leaves the mean on the right. This is the whole point of the
   page: drop the run whose count rate collapsed or whose curve has an aggregate
   spike. Read *CR A / CR B / Duration* to decide (see *Observed* — those columns
   are off-screen by default, and the count rates are wrong).
4. **save**. Writes the Kristine-format `.cor`: lag, G(τ), a metadata column
   carrying the **summed** acquisition time in row 0 and the duration-weighted
   mean count rate in row 1, and — when more than one curve was merged — a fourth
   column with the standard error `std(y)/√n` over the curves.
5. Push it into ChiSurf (`add_to_chisurf`): sets experiment **FCS**, setup
   **Seidel Kristine**, and adds the saved file as a dataset. It appears in the
   dataset list named after the *folder*.

### B. Calibrate the volume on a reference dye

6. Open **Diffusion/Volume Calculator**. Six linked quantities in *Diffusion /
   volume* (τ, D, r_h, S, Veff, T, η) and three in *Occupancy* (1/N, N, conc).
   The **Constraint (choose one)** radios at the top decide which of D / r_h /
   Veff is the input and which two are computed: with **Fix D** (the default),
   τ and D give Veff.
7. Set **T (°C)** to the measurement temperature — with *Use water η(T)* ticked,
   η follows automatically (22 °C → 0.9548 mPa·s).
8. Pick **Rhodamine 110** in *Reference dye*, leave *Apply with Temp/η scaling*
   selected, press **Apply Dref**. D becomes 433.705 µm²/s — the catalogue's
   470 µm²/s at 25 °C, scaled to 22 °C through T/η.
9. Type the calibration dye's **fitted τ_D** into **τ (µs)** — 28 µs here. Veff
   drops to **0.298067 fL** and r_h reads 0.522 nm (a sane dye radius). That
   volume, together with **S** (the axial/lateral aspect ratio from the same fit,
   5.0), *is* the calibration. Note it down — the tool has no "store calibration"
   (see *Observed*).

### C. Read the unknown sample

10. Select **Fix Veff** and re-enter the calibrated **0.298067 fL**. D and r_h
    become the outputs.
11. Type the sample's fitted **τ_D** — 220 µs → **D = 55.199 µm²/s** and
    **r_h = 4.102 nm**. (Checked by hand: w_xy = (Veff/π^{3/2}S)^{1/3} = 0.2204 µm,
    D = w_xy²/4τ, r_h = k_BT/6πηD — both agree to all printed digits.)
12. Type the fitted **1/N** — G(0) − 1 = 0.3333 → **N = 3.000** molecules and
    **Conc = 16.713 nM**. N, 1/N and the concentration are three views of one
    number and update each other in both directions.
13. Optional, *Molecular shape*: pick Sphere/Ellipsoid/Cylinder, give a size and
    an aspect, press **Apply shape→D** to see what D a rigid body of that shape
    would have — a 5 nm sphere at 22 °C gives 90.57 µm²/s, so the sample above
    (55.2) is either bigger or far from spherical. **This overwrites the
    calibration** (see *Observed*).
14. *Settings JSON* → **Export JSON** writes every field, including the dye,
    constraint and shape, to a file that **Import JSON** restores.

**Expected result:** a single `.cor` whose lag axis, G(τ) and per-point errors are
the average of the accepted repeats, whose metadata row carries the summed
duration and the mean count rate; and, from it, a diffusion coefficient, a
hydrodynamic radius and an absolute concentration for the sample — all traceable
to one reference dye measured on the same instrument.

## Observed (last run: 2026-07-28)

Driven offscreen (`QT_QPA_PLATFORM=offscreen`, `arm64` env) with the real
`ChisurfWizard` / `WizardFcsMerger` and `ConfocalCalcWidget`, screenshots grabbed
and read at every step.

**The physics is right; the plumbing around it is not.** Every closed-form
quantity the calculator produces reproduced an independent hand calculation to
all printed digits — Veff from τ and D, D and r_h back out of a fixed Veff, the
Stokes–Einstein inversion across 5–60 °C, the water-viscosity model (1.5012 mPa·s
at 5 °C, 0.6904 at 37 °C), the T/η scaling of the reference D, and N ↔ 1/N ↔ c.
The merge arithmetic is likewise correct in `y`: with two identical inputs the
mean is that input to the last digit, the acquisition times sum and the errors
collapse to float noise.

What a user actually gets is worse than that, in four places:

* **Every count rate the merger shows or writes is 2000× too small** (RF-730).
  The 18.264 kHz file displays as `0.01` kHz in the table, and the merged `.cor`
  stores `0.009132`. The shared core primitive gets this right and carries a
  comment warning about exactly this factor; the GUI page keeps its own older
  copy of the parser. The count rate is the *only* thing in the table that tells
  a repeat apart — and it is also what the Kristine weighting model uses when
  there is no error column.
* **The merged file poisons the fit that consumes it** (RF-731). Where two
  repeats agree exactly, `std` is exactly 0, the error column gets a 0, and the
  Kristine reader's `w = 1/ey` turns it into `inf`. Pushing the merged curve
  straight into ChiSurf through the page's own *add to ChiSurf* produced a
  dataset with **24 infinite weights out of 206 points** and finite weights up to
  2.8 × 10¹⁰ — accompanied only by a `RuntimeWarning` on stderr that no GUI user
  ever sees. Any fit on it is decided by those 24 channels.
* **The round trip is not the identity.** The first lag channel is silently
  dropped (207 → 206 rows, RF-732), and a folder holding a *single* `.cor` comes
  back with its existing error column **deleted** (4 columns in, 3 out, RF-733) —
  so "re-merging" a curve to reorganise a folder quietly discards the errors it
  arrived with.
* **Unticking every row merges everything anyway** (RF-735). With both boxes
  clear the left plot draws both curves dashed-grey as excluded while the right
  panel shows a full merged curve, and **save** writes the average of both. The
  two halves of the same window disagree, and the code path is an unannounced
  `if not selected: use all`.

The merger's toolbar has **two controls that do nothing** (RF-734): **clear** is
connected to no slot at all (and its handler would raise `AttributeError` on a
leftover `self.settings` if it were), and **help** toggles a 210 px panel that is
entirely blank — it makes the already-cramped table narrower and shows no text.

The window itself is badly proportioned. The table pane is pinned at ~125 px
while its five columns need 500; at **every** window size from 1100 to 1400 px
only *Use* and a truncated *File* are visible, so `Kristine_with_error` and
`Kristine_without_error` both render as `Kristine_w...` — indistinguishable — and
the three numeric columns a user needs to triage repeats are reachable only via a
horizontal scrollbar. The **Target** row is worse: the label, the path box and
**save** are crushed into ~220 px, so the destination reads `fcsscalc/cor.cor`.
Neither plot has axis labels or units.

In the calculator, the three fields that are **outputs** — r_h and Veff under
*Fix D* — are visually identical to the inputs: white background, black text,
live up/down arrows (RF-736). The palette line meant to distinguish them assigns
`Base` to `Base`. Typing or stepping in them is correctly refused, but silently,
so the field simply appears broken. The widget clearly *has* the vocabulary: the
η box, when *Use water η(T)* is ticked, greys out properly.

Two smaller traps: **Apply Dref** and **Apply shape→D** silently flip the
constraint back to *Fix D*, which destroys a calibrated Veff (0.298067 → 1.097465
fL in one click, with no warning and no undo — RF-737); and the *Aspect* box is
enabled and ignored for the default *Sphere*, because the handler that disables it
is wired only to `currentIndexChanged` and never runs at construction (RF-738).

Settings JSON round-tripped every field except `invN`, which came back as
0.333333238 instead of 0.333333333 — a rounding artefact of `N` being displayed
with 3 decimals while its exact reciprocal `1/N` is shown with 9.

Nothing crashed, and neither tool took measurable time on this data.

## UX / UI suggestions

* **Give the merger table the room it needs.** Put the table and the plots in a
  `QSplitter` with a sensible initial ratio, `resizeColumnsToContents()` after a
  load, and elide filenames in the middle (`Kristine_…_with_error`) rather than at
  the end, so repeats that share a prefix stay distinguishable.
* **Show the merge in numbers, not only in the plot.** A one-line summary under
  the *FCS Merged* panel — *"3 of 10 curves excluded · 421 s total · 18.3 kHz ·
  206 lag channels"* — would have made three of the defects above visible at a
  glance.
* **Make the target path editable** (or offer a *Save as…*). It is currently
  derived from the folder name, written outside the folder the user picked, and
  overwrites silently.
* **Name the dataset after the measurement.** `add_to_chisurf` names the pushed
  dataset after the containing folder, so a session full of merged repeats is a
  list of `cr5`, `chunks`, `cor`.
* **Label the correlation plots** — *lag time τ (s)* and *G(τ)*, log-x — and
  consider hiding the first lag channels by default; the after-pulsing spike at
  1.4 × 10⁻⁵ s dominates the left third of both panels.
* **Show which calculator fields are results.** Grey them the way the η box is
  greyed, hide the spin arrows on read-only fields, or move the three computed
  quantities into their own *Results* panel. Six identical spin boxes where three
  are inputs and three are outputs is the central confusion of the widget.
* **Keep the calibration.** Add *Store calibration* / *Recall calibration*
  (Veff + S + T + dye, with the date), and warn before an action that would
  overwrite a stored Veff. Step 9's number currently survives only in the user's
  notebook — and one click on *Apply shape→D* erases it.
* **Show the reference-dye provenance in the UI.** The catalogue entry carries the
  citation, the method (PFG-NMR) and the URL; the combo shows only the name. A
  line under the combo — *"470 µm²/s @ 25 °C, Kapusta (2010), PFG-NMR"* — and a
  note of the scaled value actually applied would make the calibration
  self-documenting.
* **Say what τ means.** *τ (µs)* is the diffusion correlation time from a fit;
  the tooltip says so, but the panel would read better as *Diffusion time τ_D
  (µs, from the FCS fit)*, and *S* as *aspect ratio w_z/w_xy (from the same fit)*.
* **Pull the numbers from the fit.** The whole workflow is *read τ_D, S and 1/N
  off a fit, retype them into a calculator*. A **From selected fit** button would
  remove the transcription step entirely — and it is the natural place to also
  carry over the temperature.

## Bugs filed

RF-730 (count rate 2000× low in the merger's table and output), RF-731 (zero
error values become infinite fit weights), RF-732 (first lag channel silently
dropped), RF-733 (single-curve merge deletes the input error column), RF-734
(*clear* and *help* are dead controls), RF-735 (unticking every row merges all of
them), RF-736 (read-only calculator outputs look like inputs), RF-737 (*Apply
Dref* / *Apply shape→D* destroy a calibrated Veff), RF-738 (*Aspect* enabled and
ignored for the default *Sphere*).

## Related

* [FCS correlation from raw TTTR](/usecases/fcs-correlate-tttr.md) — produces the
  chunk folder this page merges.
* [FCS diffusion fit](/usecases/fcs-diffusion-fit.md) — consumes the merged
  `.cor` and produces the τ_D, S and 1/N typed into the calculator.
* [filtered-FCS filter calculator](/usecases/ffcs-filter-calculator.md) — the
  species-selective correlation.
* [PCH molecular brightness](/usecases/pch-molecular-brightness.md) — the other
  way to get ⟨N⟩, independent of a diffusion model.
