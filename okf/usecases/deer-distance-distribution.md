---
type: Reference
title: Use case — DEER/PELDOR distance distribution (load a dipolar trace, fit P(r))
description: Load a Bruker BES3T or CSV 4-pulse DEER trace into the DEER experiment, create a Gaussian, Rice, Tikhonov or MaxEnt fit, fit the dipolar evolution and read the spin-spin distance distribution P(r).
tags: [usecase, deer, peldor, epr, fitting, distance-distribution, gui]
timestamp: '2026-07-27T00:00:00Z'
---

# Use case: DEER/PELDOR distance distribution

**Goal:** the EPR counterpart of a FRET distance — a user has a 4-pulse DEER
(PELDOR) dipolar evolution trace `V(t)` from a spin-labelled sample and wants the
spin–spin distance distribution `P(r)`: either a parametric distance
(mean ± width, from a Gaussian or Rice component) or a model-free `P(r)` from a
regularised inversion, together with a goodness-of-fit they can defend.

ChiSurf treats DEER as a first-class **experiment** (`Experiment = DEER` in the
Read-data dock), not a plugin: one reader, four models, the ordinary
add-fit → fit → read-Info loop. The inversion is self-contained (numpy/scipy
only, `chisurf/core/models/deer/`).

**Data:** `test/data/deer/` — three fixtures redistributed from the DeerAnalysis
test suite (MIT, Jeschke lab):

| file | format | trace |
|------|--------|-------|
| `deer_twostate.DSC` / `.DTA` | Bruker BES3T, complex | 588 points, 0 … 4.696 µs, estimated noise σ = 3.00e-3 |
| `deer_ringtest_4pdeer.DSC` / `.DTA` | Bruker BES3T, complex | 355 points, 0 … 2.832 µs, σ = 1.39e-3 |
| `deer_trace.csv` | headerless ASCII, time in ns | 356 points, auto-converted to 0 … 2.84 µs, σ = 1.48e-2 |

## Steps

1. Start ChiSurf. In the **Read data** dock, set **Experiment** = `DEER`.
2. **File type** offers a single reader, `DEER (BES3T/CSV)`. The *File
   parameters* section is empty apart from the hint *"DEER: open a Bruker BES3T
   (.DSC/.DTA) or CSV/text trace."* — the reader's phase-correction,
   normalisation and experiment-type switches have no control (RF-434).
3. Click **+ Data** (or drop the file on *Drop files here*) and pick
   `deer_twostate.DSC`. The reader finds the `.DTA` companion, phase-corrects the
   complex trace, normalises `V(t₀) = 1`, estimates the noise from the imaginary
   channel and stores `t`, `V`, `V_imag`, `phase`, `t0`, `scale` and
   `noise_level` in `meta_data['deer']`.
4. Switch to the **Data** tab and select the `deer_twostate` row.
5. Pick a model in the model combo and click **Add fit**:
   - `DEER Gaussian(s)` — one or more Gaussian distance components (add/remove
     with the green **add** / red **del** buttons);
   - `DEER Rice` — a single 3D-Rice component (ν, σ);
   - `DEER model-free (Tikhonov)` — regularised `P(r)`, with an **Auto-α**
     choice of `gcv` or `lcurve`;
   - `DEER model-free (MaxEnt)` — maximum-entropy `P(r)`.
   The fit range is auto-detected as the whole trace (0 … 587).
6. In the **Analysis** dock, review the parameter groups: *Modulation*
   (λ, t₀ [µs], scale), *Background* (`hom3d` / `exp` / `strexp`, k [µs⁻¹], d),
   *Distance grid* (r_min, r_max — `0 = auto`, n_points) and the model's own
   distance group. λ and t₀ are pre-seeded from the trace (λ from the tail
   plateau, t₀ from the reader), so the fit starts near the solution.
7. Click **Fit**.
8. Read χ²ᵣ from the *Fit* tab annotation, `P(r)` from the *Distribution* tab,
   its bootstrap band from *P(r) 95% CI*, and the parameter values with
   covariance errors and likelihood intervals from the *Info* tab. The two
   model-free models add an *L-Curve* tab showing roughness ‖L·P‖ against
   residual ‖K·P − F‖ with the selected α marked.
9. To resolve a second population with the parametric model, click **add** in the
   *Distance (Gaussians)* group and re-fit; compare χ²ᵣ.

## Expected

- Step 3 loads one DEER dataset per file; the *Fit* tab plots `V(t)` against
  `t (µs)`.
- A fit converges in seconds (parametric) to under a minute (model-free) and the
  model tracks the dipolar oscillation and the intermolecular background.
- `deer_twostate` is a two-population sample, so a single Gaussian should leave
  visible residual structure and the model-free `P(r)` should show more than one
  feature.
- `deer_trace.csv` is a clean single-distance trace and should reach χ²ᵣ ≈ 1.

## Observed (last run: 2026-07-27)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through the real main
window in five passes: the experiment/reader combo boxes, `+ Data` with all three
fixtures, the dataset tree, the model combo, **Add fit**, the AutoForm model
editor, `FittingControllerWidget.button_fit`, and every tab of every fit
sub-window, with screenshots read at each step.

**The DEER analysis itself is sound.** All three fixtures load; the BES3T reader
picks up the `.DTA` companion, and the CSV reader auto-detects the nanosecond
time axis and returns 0 … 2.84 µs. On `deer_trace.csv` one Gaussian gives
**χ²ᵣ = 1.206, DW = 1.857** with structureless residuals at r = 31.82 Å,
σ = 3.82 Å — a textbook fit. On `deer_twostate` the four models agree on the
nuisance parameters (λ ≈ 0.50, k ≈ 0.024 µs⁻¹) and on the dominant distance:

| model | χ²ᵣ | time | distance result |
|-------|-----|------|-----------------|
| Gaussian ×1 | 8.9672 | 10 s | r₁ = 37.077 ± 0.017 Å, σ₁ = 4.972 ± 0.023 Å |
| Rice | 8.9625 | 12 s | ν = 36.737 Å, σ = 4.996 Å |
| model-free (Tikhonov, gcv) | 6.8387 | 35 s | peak 36.5 Å + shoulder ≈ 46 Å + minor peak ≈ 24 Å |
| model-free (MaxEnt) | 20.5230 | 62 s | one broad peak ≈ 37.5 Å on a uniform pedestal |

The Tikhonov result is the honest one: it is the only model that resolves the
second population, and its L-Curve tab shows where α was placed. The *Info* tab
is excellent — values, covariance errors with percentages, likelihood intervals,
and an explicit "*bounds only (not in objective) … no informative prior — the fit
is plain least squares*" note.

**MaxEnt is the odd one out and it under-fits (RF-436).** On the same trace, with
the same seeded start values, it stops at χ²ᵣ = 20.52 — three times the Tikhonov
value and worse than a two-parameter Gaussian — and its `P(r)` keeps a flat
0.007 pedestal across the whole 15 … 65 Å grid, the signature of an entropy
weight chosen far too large. It is also the slowest model by a factor of two.

**Every fit opens showing a model that has not been computed (RF-435).** For all
four models, a freshly created DEER fit reports **χ²ᵣ = 30113.9309**, draws the
model as a flat line at zero and shows weighted residuals of 150 … 340. Nothing
warns that this is a not-yet-evaluated model rather than a catastrophic
mismatch; calling `model.update()` by hand yields χ²ᵣ = 560.9 from the seeded
start values, i.e. the seeding works and only the initial evaluation is missing.
Worse for the model-free models: their **L-Curve tab is already populated and
selected** when the window opens, so the first thing a Tikhonov user sees is a
completed α-scan next to a zero model.

**Two model-editor defects are visible in every DEER model.** Parameter labels
written as bare HTML entities are printed literally — the Rice model's only two
shape parameters read **`&nu;[&#8491;]`** and **`&sigma;[&#8491;]`**, the
modulation depth reads `&lambda;` and the regularisation weight `&alpha;`, while
`t<sub>0</sub>[µs]` in the same table renders correctly as t₀[µs] (RF-432).
And every parameter-group table is drawn 6 px per row too short, so the last row
is sliced in half — in the Rice editor σ is a half-height smear under ν, with
275 px of empty dock below it (RF-433).

**The Read-data dock has no controls at all (RF-434).** The DEER reader exposes
`phase_correction`, `normalize` and `exp_type`, and its controller docstring
promises to render them "when available", but there is no `deer.view.json` —
every other experiment reader (TCSPC, FCS, PCH, PDA, ICS) ships one — so
`hasattr(reader, "view_spec")` is False, the AutoForm branch is skipped inside a
bare `except: pass`, and the dock shows one hint label above 700 px of nothing.
A user cannot turn off phase correction on a trace the automatic phasing gets
wrong, nor stop the normalisation for an un-normalised trace.

Two things that looked like bugs and are not, recorded so the next run does not
re-file them: (a) the model combo is repopulated and reset to index 0 by
`onCurrentDatasetChanged`, so a model picked *before* the dataset is silently
discarded — pick the dataset first, then the model; (b) the *Fit* tab appearing
stale after a fit (pre-fit χ²ᵣ, zero model) reproduces **only** when a second
in-process RPC server is forced onto a private port and `model.finalize` fails —
on the stock app the plot refreshes correctly. That the plot refresh rides on the
finalize round-trip is worth knowing.

One unresolved oddity: in the pass that created four fits in one session, the
third **Add fit** silently produced no new fit (the previous fit stayed current);
it did not reproduce when the same dataset was driven in a fresh session, so it
is not filed.

## UX / UI suggestions

- **Show the phase and the imaginary channel.** The reader computes the applied
  zero-order phase and keeps `V_imag`, and checking that the imaginary channel is
  flat is the standard first move of every DEER user — neither is plotted or
  reported anywhere in the GUI.
- **Say `0 = auto` where it matters, once.** The regularisation weight shows as
  `&alpha; = 0` under a panel called *Auto-α* (Tikhonov) or *Entropy
  regularisation* (MaxEnt); *Distance grid* spells it out (`r_max[Å] (0=auto)`)
  and the α row does not.
- **One spelling per quantity.** The Tikhonov panel says *Auto-α* in its choice
  label and `&alpha;` in the row underneath, for the same parameter.
- **Give the long fits a progress indication.** Tikhonov takes ~35 s and MaxEnt
  ~60 s on a 588-point trace, both behind a single **Fit** click with no
  determinate progress; the parametric models take 10 s.
- **Open on the *Fit* tab.** A new Tikhonov/MaxEnt window opens on *L-Curve*.
- **Label the *Distribution* y-axis.** It has an `r (Å)` x-axis and no y-axis
  title, while the neighbouring *P(r) 95% CI* tab labels the same quantity
  `P(r) (x0.001)`. The χ²ᵣ annotation box also sits on top of the y-axis tick
  labels in both.
- **Report the distance, not just the parameters.** For the model-free models the
  headline number a user quotes — the mean distance and its width from `P(r)` —
  is nowhere in the *Info* tab; only λ, k and α are listed. `⟨r⟩`, the mode and
  the FWHM belong next to χ²ᵣ.
- **Nothing states the distance unit outside the labels.** The models work in Å
  (labels say `[Å]`), while the DEER literature and the `.DSC` files are usually
  quoted in nm; a unit toggle, or at least the unit in the *Distribution* axis
  title, would prevent a factor-of-ten error. (The `DeerGaussians.means` /
  `.sigmas` docstrings say "nm" — they are Å.)
- Known cross-workflow items reproduce here unchanged: the *Parameter scan* tab
  is an empty −0.5 … 0.5 plot with no controls, the *Residuals* tab plots against
  point index with unlabelled axes, the fit sub-window opens at 566 × 350 inside
  a 1223 × 915 MDI area, the bottom dock tabs truncate to *"Read…" "Dat…"
  "Anal…"*, and the fit window's title-bar button reads `C...e`.

## Bugs filed

- RF-432 — parameter labels that are pure HTML entities (`&nu;`, `&sigma;`,
  `&lambda;`, `&alpha;`, `&epsilon;`) are printed raw in every parameter table.
- RF-433 — every parameter-group table is 6 px per row too short, clipping the
  last row.
- RF-434 — the DEER reader ships no `view.json`, so phase correction,
  normalisation and experiment type are unreachable from the GUI.
- RF-435 — a newly created DEER fit shows an unevaluated (all-zero) model and
  χ²ᵣ = 30113.93.
- RF-436 — the DEER MaxEnt model under-fits (χ²ᵣ = 20.5 against 6.8 for
  Tikhonov and 9.0 for a single Gaussian) and leaves a uniform pedestal in
  `P(r)`.
