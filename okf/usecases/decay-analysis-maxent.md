---
type: Reference
title: Use case — Decay Analysis hub (MaxEnt lifetime distribution, IRF estimation, G-factor)
description: Model-free lifetime analysis of a TCSPC decay — run MaxEnt MEM on the current fit, estimate an IRF from a decay, and calibrate the detector G-factor from VV/VH data.
tags: [usecase, tcspc, maxent, mem, irf, g-factor, anisotropy, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: Decay Analysis hub — model-free lifetime distribution

**Goal:** the user has already fitted a decay with a discrete lifetime model and
wants the answer *without* assuming how many exponentials there are: a
maximum-entropy **lifetime distribution** over the same decay and IRF. The same
hub also carries the two calibration steps that feed a decay analysis — blind
**IRF estimation** from a decay, and the detector **G-factor** from VV/VH data.

**Data:**
- `test/data/tcspc/ibh_sample/Decay_577D.txt` (decay, 4094 channels) and
  `test/data/tcspc/ibh_sample/Prompt.txt` (IRF), IBH text, `dt = 0.0141` ns/ch,
  10 MHz.
- `test/data/tcspc/Jordi/02_18-577+7.5uM(577)UP_8ps.dat` and
  `test/data/tcspc/Jordi/H2O_8-0 ps_2048 ch.dat` — VV/VH stacked files,
  2048 channels per channel-set at **8 ps/channel** (the value lives in the file
  *name*, not in the file).

The MEM panel has no file loader of its own: it reads the decay, the IRF and the
nuisance parameters **from the current ChiSurf fit**, so steps 1–5 are the
prerequisite (they are the [TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md)
use case in short form).

## Steps

1. Start ChiSurf. **Read data** dock: **Experiment** = `TCSPC`, **File type** =
   `TXT/CSV`; reader parameters header on, `Skiprows = 11`, CSV routine,
   polarization `VM`, `dt = 0.0141` ns/ch, `rep. = 10` MHz.
2. **+ Data** → `Decay_577D.txt`, then again → `Prompt.txt`.
3. **Data** tab: select `Decay_577D.txt`, choose `Lifetime ` in the model combo,
   click **Add fit**.
4. Analysis dock → **Convolve** → **…** next to *IRF* → pick `Prompt.txt`.
5. Click **Fit**.
6. Open **Spectroscopy:Decay Analysis** (ribbon). The hub lists five numbered
   panels: *1. IRF Estimation*, *2. MaxEnt MEM*, *3. Lazy Lifetime Analysis* ⚠,
   *4. Histogram-Microtime*, *5. VV/VH G-Factor*.
7. Select **2. MaxEnt MEM**. Click **🔄 Refresh** to pull the decay, the IRF and
   the fit range out of the current fit.
8. Switch the left tab to **Settings** and check what Refresh filled in: τ grid,
   timeshift, background, IRF background, lamp scatter, regularisation `nu`.
9. Click **🎯 Run**. Read the distribution on the **Distribution** tab and the
   weighted residuals above the decay.
10. Click **📈 L-curve** to scan `nu` over ±2 decades and pick the corner.
11. Go to **1. IRF Estimation**, **📂 Load Decay** a VV/VH `.dat` file, then
    **🔮 Estimate IRF**; read τ, k, A, C in *Estimation Results*.
12. Go to **5. VV/VH G-Factor**, **Load VV/VH File**, read *G-Factor* and
    *StdDev*, then tick **Background Correction**.

## Expected

- Step 5 gives χ²ᵣ ≈ 1.63 with τ ≈ 4.15 ns over range 522…3793.
- Step 7 fills the *Data / IRF* box with the decay's file name and the IRF, sets
  the MEM fit range to the fit's own range, and seeds τ_min from the IRF FWHM.
- Step 9 produces a distribution peaked at the fitted lifetime (≈ 4.2 ns) with
  flat weighted residuals, in a couple of seconds.
- Step 10 leaves the best `nu` selected in the spin box and plots the L-curve.
- Step 11 returns an IRF narrower than the decay and a tail lifetime in the
  physical range of the sample.
- Step 12 returns a G-factor near 1 for a well-matched detection path, with an
  uncertainty small enough to be usable as a calibration constant.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, private RPC port)
through the real widgets — main-window combo boxes, `macros.add_dataset`, the
**Add fit** tool button, the `ConvolveWidget` IRF picker, `onRunFit`, then
`LifetimeAnalysisTool` with its navigation list and each panel's own buttons.
Screenshots taken at every step and inspected.

**The MEM analysis itself is right, and fast.** Refresh carried everything over
correctly: data `Decay_577D.txt (N=4094)`, `IRF: model.convolve.irf`, fit range
`(522, 3793)`, `timeshift 2.7147 ch`, `lamp scatter 0.0444`, and τ_min auto-set
to `0.134 ns` from the IRF FWHM. **Run** took **1.2–2.1 s** and returned
`chisq = 1.352`, `S = -12.06`, `Q = 1.358` with a sharp peak at **τ = 4.219 ns**,
⟨τ⟩ₓ = **4.108 ns** — against the discrete fit's τ = 4.149 ns, χ²ᵣ = 1.626. A
small satellite at ≈ 2 ns carries a few percent. The weighted-residual panel is
flat across 7…52 ns. This is exactly the cross-check a user wants, and it works.

**Everything around it is where the run went wrong.**

- **The L-curve button computes for 5.5–6.5 s and then silently discards its own
  answer.** `nu` stayed at `0.001` before and after, although the scanned grid
  (16 log-spaced points over ±2 decades) does not contain 0.001 at all. The
  corner is never applied because the guard tests `chisurf.math`, a module that
  no longer exists. The scatter plot is drawn, but its **chi² axis carries no
  tick labels**, there is no corner marker and no `nu` annotation, so the user
  cannot even read the answer off the plot. See RF-170.
- **Every IRF estimation ends in a modal error dialog — including the successful
  ones.** The estimate finishes in 0.12 s, the results and plots update, and then
  the status-bar update raises `TypeError: showMessage(...): 'timeout' is not a
  valid keyword argument`, which the handler turns into a red *"Estimation
  Error"* box quoting the PyQt signature; the handler's own status-bar call then
  raises the identical error a second time, uncaught. The status bar is left
  frozen on *"Estimating IRF…"* forever. Two files, two identical dialogs. In the
  offscreen driver this modal blocked the whole run for minutes. See RF-169.
- **The IRF panel reports lifetimes in the wrong unit.** VV/VH `.dat` files carry
  no `dt`, so the panel falls back to `1.0 ns/channel` and **disables** the
  *Time/Channel (ns)* box, so the user cannot correct it. The 8 ps/channel water
  prompt is plotted on a 0…2047 **ns** axis and its lifetime is reported as
  **27.6563 ns** instead of 0.221 ns — a factor of 125. See RF-171.
- **On one of the two files the estimator returned nonsense and said nothing.**
  For `02_18-…UP_8ps.dat` the rise/tail detector picked `t0 = 1807` of 2048 —
  inside the zero-padded tail — so the exponential fit returned
  `k = 470.85 ns⁻¹`, i.e. **τ = 0.0021 ns**, displayed to four decimals like a
  real result. The forward-model overlay then fills the entire plot with a dense
  orange comb that hides the measured decay and the estimated IRF (screenshot
  `F1_irf_estimated.png`). See RF-172.
- **The G-factor is computed as a mean of per-channel ratios**, which is biased
  upward at low counts, and the number next to it labelled *StdDev* is the
  population spread of those ratios, not the uncertainty of G. On the water file
  the panel reported `G = 1.7418 ± 1.3884` where the ratio of summed counts is
  1.3211 and the standard error of the mean is 0.0718. On simulated Poisson data
  with a **true ratio of exactly 1.0** at 10 counts/channel the same estimator
  gives 1.1172. See RF-173.

The hub shell itself behaves well: the five panels load lazily, the ⚠ marker on
the experimental *Lazy Lifetime Analysis* panel is visible in the list, the
Back/Next stepper is present, and the G-factor panel's two-plot layout (decay
overlay with the shaded matching region, plus `r(t)`) is clear and complete.

## UX / UI suggestions

- **The MEM panel opens on an empty blue rectangle.** Straight after selecting
  *2. MaxEnt MEM* the *Decay / fit / IRF* plot is a solid navy fill on a 0…1 axis
  with nothing in it, and the only hint that data must be pulled in is the text
  *"No data loaded"* on the **Settings** tab — which is not the tab that is
  showing. Put an explicit empty state ("press 🔄 Refresh to read the decay and
  IRF from the current fit") in the plot itself.
- **No numbers anywhere for the MEM result.** `chisq`, `S`, `Q`, the peak τ and
  ⟨τ⟩ₓ all exist in the result dict and none of them is shown; the user gets a
  curve and no goodness-of-fit. A one-line result strip under the distribution
  would make the panel self-contained.
- **The IRF trace vanishes from the *Decay / fit / IRF* panel after Run** while
  the panel keeps its title — before the run the IRF is drawn in red, after it
  only decay and model remain.
- **Three unlabelled spin boxes stacked under one label.** *tau grid [ns]* is
  `0.134 / 6.000 / 192` and *L-curve span [dec]* is `2.00 / 2.00`, with nothing
  saying which is min, max, bins, left, right. Label or suffix them.
- **The Settings panel clips its own widgets**: every spin box loses its
  up/down arrows at the right edge, and *"Current fit data: ./test/data/tcspc/ibh_sa…"*
  is elided with no tooltip.
- **The L-curve plot needs axis numbers, a corner marker and `nu` labels** — as
  drawn it is a bare scatter with an unlabelled x axis.
- **"Estimate IRF" gives no progress feedback** and blocks the window; the status
  bar is the only channel and it is stuck (RF-169). Route it through the hub's
  shared status bar / `begin_task` like the other panels.
- **The IRF panel's file dialog offers only `*.dat` (VV/VH)** while the panel is
  the natural place to estimate an IRF for the text decays the rest of ChiSurf
  loads; *Load from Dataset* covers that, but the naming does not say so.
- **The G-factor panel shows `dt [ns/ch] = 1.000000` and `tau [ns] = 0.000000`**
  as editable defaults with no indication that they are placeholders, right next
  to a *"Warning: Load FP VV/VH data to estimate l1/l2."* which is the only
  guidance in the panel.
- **Empty plots draw a fake axis**: the fresh IRF panel shows a *Time (ns)
  (x0.001)* axis running −400…400 before any data is loaded.

## Bugs filed

- RF-169 — IRF estimation always ends in a modal *"Estimation Error"* and a
  re-raised `TypeError` (`showMessage(..., timeout=)`).
- RF-170 — the MaxEnt L-curve never applies the detected corner: the guard tests
  the removed `chisurf.math` module.
- RF-171 — VV/VH decays load with `dt = 1 ns/channel` into a **disabled** spin
  box, so the IRF panel's time axis and lifetime are off by the true `dt`.
- RF-172 — the IRF rise/tail detector can select the zero-padded tail and the
  panel then presents `τ = 0.0021 ns` as a result.
- RF-173 — the G-factor is a mean of per-channel ratios (biased upward at low
  counts) and its *StdDev* is the population spread, not the error of G.
