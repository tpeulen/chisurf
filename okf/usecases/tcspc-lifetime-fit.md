---
type: Reference
title: Use case — TCSPC lifetime fit (load decay, pick IRF, fit)
description: Load a TCSPC decay from a text file, create a Lifetime fit, assign the IRF, fit, and read chi2r and the lifetimes.
tags: [usecase, tcspc, fitting, lifetime, gui]
timestamp: '2026-07-25T00:00:00Z'
---

# Use case: TCSPC lifetime fit

**Goal:** the bread-and-butter task — a user has a measured fluorescence decay and
the matching instrument response (prompt), and wants the fluorescence lifetime(s)
with a goodness-of-fit they can defend.

**Data:** `test/data/tcspc/ibh_sample/Decay_577D.txt` (decay, 4094 channels) and
`test/data/tcspc/ibh_sample/Prompt.txt` (IRF), both IBH text format, `dt = 0.0141`
ns/channel, 10 MHz repetition rate.

## Steps

1. Start ChiSurf. In the **Read data** dock, set **Experiment** = `TCSPC`.
2. Set **File type** = `TXT/CSV`.
3. In *File parameters*, set the reader for this file family: header on,
   `Skiprows = 11`, CSV routine, polarization `VM`, `dt = 0.0141` ns/ch,
   `rep. = 10` MHz, VV/VH off.
4. Click **+ Data** (or drop the file on *Drop files here*) and load
   `Decay_577D.txt`. Repeat for `Prompt.txt` — the IRF must be loaded as its own
   dataset before it can be assigned.
5. Switch to the **Data** tab, select the `Decay_577D.txt` row.
6. Pick `Lifetime ` in the model combo box and click **Add fit**. A fit sub-window
   opens and the fit range is auto-detected.
7. In the analysis dock (**Convolve** section), click the **…** button next to
   **IRF**, and choose `Prompt.txt` from the dataset list.
8. Click **Fit**.
9. Read χ²ᵣ from the *Fit* tab annotation, and the parameter values plus their
   uncertainties from the *Info* tab.
10. To resolve a second component, click the green **add** button in the
    **Lifetimes** section and click **Fit** again; compare χ²ᵣ.

## Expected

- Step 6 fills the fit range with the reader's auto range (here **522 … 3793**),
  and the *Fit* tab annotation shows the same numbers.
- Step 8 fits in well under a second; with the Prompt as IRF the one-exponential
  fit reaches **χ²ᵣ ≈ 1.63**, τ ≈ 4.2 ns, and the weighted residuals are flat
  apart from the rising edge.
- Without an IRF assigned the same fit stops at **χ²ᵣ ≈ 5.22** — the IRF step is
  what makes the fit trustworthy, not a formality.
- Step 10 lowers χ²ᵣ further (observed 5.22 → 4.13 for the no-IRF case).

## Observed (last run: 2026-07-25)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through the real main
window: experiment/setup combo boxes, `macros.add_dataset`, `onAddFit`, the
`ConvolveWidget` IRF selector, the green **add** button, and
`FittingControllerWidget.onRunFit` — i.e. the same objects the toolbar and the
mouse drive. Screenshots taken at each step and inspected.

**The science works.** With the IRF assigned, the fit converged in ~0.4 s to
χ²ᵣ = 1.6267 (DW = 1.2669), τ = 4.2 ns; residual and autocorrelation panels, the
shaded fit range, the IRF overlay and the *Info* tab (values, errors, likelihood
intervals, prior notes) all render correctly and look professional. Adding a
second component moved χ²ᵣ 5.219 → 4.133 (τ₁ = 6.93 ns, τ₂ = 4.05 ns, x₂ = 0.95).
The *Data table* tab (4 094 rows × 6 columns, N and χ²ᵣ in the corner) is good.

**But the whole workflow silently dies if another ChiSurf is already running.**
This run started while a second `python -m chisurf` held 127.0.0.1:8765/8766. The
new instance adopted that foreign RPC server after a bare `meta.ping`, so every
fitting call — `fit.range.auto`, `fit.set_fit_range`, `fit.update`, `fit.run`,
`model.finalize`, `fit.set_result_idx` — returned *"fit not found"*. Nothing was
shown to the user: the range spin boxes displayed **522 / 3793** while the fit's
actual range stayed **(0, 0)** and the plot annotation read *"Range 0, 0"*; the
**Fit** button returned in 0.03 s, the progress dialog reported *"Fitting
finished!"*, and χ²ᵣ stayed **-0.0000** with every parameter untouched. Typing the
range into the spin boxes by hand did not help — that path is RPC-only too. Re-run
on a private port, the identical script fits correctly, which isolates the cause.
See RF-012 / RF-013 / RF-014.

Two clicks from a fresh fit also crash the app: the IRF picker lists the
auto-created **Global Dataset** next to the TCSPC curves, and selecting it raises
an uncaught `AttributeError: ExperimentDataGroup object has no attribute 'x'`
(RF-015).

## UX / UI suggestions

- **Say which IRF is in use.** Before a pick the field reads *"Click on button to
  load IRF -…"* while the **FWHM** box next to it already shows a number — the
  user cannot tell whether they are fitting with an IRF or not, and the χ²ᵣ
  penalty for getting this wrong is a factor of three. Make the empty state
  explicit ("no IRF — using δ-pulse").
- **No units anywhere in the model panel or the *Info* tab.** `dt`, `start`,
  `stop`, `ts`, `lb`, `IRF_w`, `IRF_k`, `tL1`, `n0`, `rep` are all bare numbers.
  `ts = 9.33` is ambiguous (channels or ns?) and its interval `[-1720, 1738.7]`
  cannot be judged without knowing. Add a unit column / suffix.
- **Flag meaningless uncertainties instead of printing them straight.** The *Info*
  tab lists `sc ±24.4 (1046679.8 %)` and `ts ±1.73e+03 (18528.5 %)` in the same
  style as `tL1 ±0.00095 (0.0 %)`. A user can copy the first two into a paper.
- **`xL1 ±nan(nan%)` / "no estimate"** is the redundant (sum-to-one) amplitude —
  print "derived" rather than `nan`.
- **The *Parameter scan* tab is a dead end**: an empty black plot on a −0.5…0.5
  axis with no parameter selector, no run button and no hint of what to do.
- **Axis labels.** *Distribution* has x = "Lifetime" with no unit and no y label;
  *Residuals* has an unlabelled x axis in channel index while the residual panel
  on the *Fit* tab uses ns for the same quantity.
- **Clipped text, several places.** The **FWHM** value box collides with its label
  and loses its leading digits (`0.254` renders as `.254`); the bottom dock tabs
  truncate to *"Read…" "Dat…" "An…" "Plot se…" "Co…" "Lo…"* even at 1700 px; the
  third ribbon row ("ndXplorer") is cut off at the panel edge; the fit window's
  custom title-bar button reads `C...e`; the IRF dialog's column headers are
  clipped along their top edge. See RF-016 for the FWHM one.
- **The *Data table*'s last column ("IRF") is stretched over ~700 px** while the
  five numeric columns are squeezed into the left third.
- **The IRF picker is a bare frameless list** — no title, no *Select IRF* heading,
  no OK/Cancel; a row click applies immediately with no confirmation.
- **`r[MHz]`, `#PhB`, `#PhF`, `Stps`, `#Run`, `lb`, `sc`, `iw`, `ik`** are
  abbreviated past the point of guessability; the labels have room to be longer or
  need tooltips.
- **χ²ᵣ renders as `X.²`** in the *Distribution* tab annotation (it is correct in
  the *Data table* header) — a font/glyph fallback problem.

## Bugs filed

- RF-012 — a second ChiSurf instance adopts the first one's RPC server; all
  fitting silently no-ops.
- RF-013 — auto/manual fit range is displayed but never applied when the RPC call
  fails (no local fallback).
- RF-014 — "Fitting finished!" and a successful history entry are recorded even
  when the fit did not run.
- RF-015 — the IRF picker offers the Global dataset and crashes when it is chosen.
- RF-016 — the Convolve **FWHM** value box is clipped and hides leading digits.
- RF-017 — `Convolve.__init__` raises a bare `IndexError` on a dataset with an
  empty `dx`.
