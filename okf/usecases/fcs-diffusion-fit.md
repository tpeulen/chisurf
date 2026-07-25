---
type: Reference
title: Use case — FCS diffusion fit (load a correlation curve, fit 3D Gauss)
description: Load a correlation curve into the FCS experiment, create a Parse-Model fit, pick the 3D-Gauss diffusion equation, restrict the fit range, fit, and read N, td and chi2r.
tags: [usecase, fcs, fitting, diffusion, gui]
timestamp: '2026-07-25T00:00:00Z'
---

# Use case: FCS diffusion fit

**Goal:** the standard FCS task — a user has a correlation curve from a
correlator (or from ChiSurf's own correlator) and wants the number of molecules
in the focus `N`, the diffusion time `t_d`, the brightness per molecule, and a
goodness-of-fit they can defend.

**Data:** `test/data/fcs/kristine/Kristine_with_error.cor` — Seidel/Kristine
format, 207 log-spaced lags from `1.36e-5` ms to `3422` ms, `G` from 4.22 down to
0.992, per-lag errors in the file (mean 0.0255), mean count rate 18.26 kHz,
acquisition time 58.7 s.

## Steps

1. Start ChiSurf. In the **Read data** dock, set **Experiment** = `FCS`.
2. Set **File type** = `Seidel Kristine` (the reader list also offers FCS-CSV,
   Zeiss Confocor3, China FCS, Ries SFCS, PyCorrFit, ALV and Correlator.com SIN).
3. In *File parameters → Noise model*, choose **Mode**. `From file (default)`
   uses the errors stored in the `.cor`; `Photon-noise (Suren)` recomputes them.
   **This choice changes the fitted diffusion time — see RF-019.**
4. Click **+ Data** (or drop the file on *Drop files here*) and load
   `Kristine_with_error.cor`.
5. Switch to the **Data** tab and select the `Kristine_with_error` row.
6. Pick `Parse-Model` in the model combo and click **Add fit**. A fit sub-window
   opens; the fit range is auto-detected as **0 … 206**.
7. In the **Analysis** dock, choose the equation from the model-file combo —
   `3D Gauss` for plain three-dimensional free diffusion
   (`b + 1/|N| (1+x/td)⁻¹ (1 + x/(s²·td))^(-1/2)`). The catalogue
   (`chisurf/core/models/fcs/models.yaml`) has 50 entries: bunching/triplet
   terms, two-component diffusion, 2D/3D, flow, anti-correlation.
8. Click **Fit**.
9. Read χ²ᵣ from the *Fit* tab annotation and `N`, `td`, `s`, `b` — with errors
   and likelihood intervals — from the *Info* tab. The *FCS parameters* block of
   the editor shows `S` (total count rate), `B` (background), `cpm` and `cpm_all`
   (counts per molecule).
10. Drop the sub-µs afterpulsing region: click into the **left** *Range
    selection* box, type `20`, press **Enter** (the boxes react to
    `editingFinished`, so the value must be committed), then click **Fit** again.
11. To account for the fast component, switch the equation to
    `3D Gauss, 1 bunching` and re-fit; compare χ²ᵣ.

## Expected

- Step 4 loads one FCS dataset (~2.4 s) and the *Fit* tab plots `G_c(t_c)`
  against `t_c (ms)` on a log axis with the data, the model, weighted residuals
  and the autocorrelation of the residuals.
- Step 8 fits in well under a second and the model tracks the data across five
  decades.
- With the file's own errors and range 20…206: **χ²ᵣ ≈ 2.41**, `N = 0.362`,
  `td = 1.056 ms`, `b = 1.0015`.
- With `Photon-noise (Suren)` and the same range: **χ²ᵣ ≈ 7.69**, `N = 0.371`,
  `td = 0.209 ms` — a 5× different diffusion time (RF-019).
- Step 10 lowers χ²ᵣ (12.22 → 7.69 with photon noise; 5.11 → 2.41 with the file's
  errors) because the first ~20 channels carry an afterpulsing artefact.
- `s` (the axial/lateral aspect ratio ω_z/ω_xy) should come out positive and of
  order 3–10, and `cpm` should equal `S/N`.

## Observed (last run: 2026-07-25)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, private RPC port to
avoid RF-012) through the real main window — experiment/reader combo boxes,
`macros.add_dataset`, the dataset tree, the **Add fit** tool button, the equation
combo of the `ParseFCSWidget`, the range spin boxes (typed + Enter) and
`FittingControllerWidget.button_fit`. Screenshots taken at every step and
inspected; the `cpm` code path was traced.

**The fitting works and looks good.** The reader picks up the 207 lags and their
errors, the log-axis plot is properly labelled (`G_c(t_c)` / `t_c (ms)`), the
model overlays the data over five decades, the shaded fit range moves when the
range is changed, the *Info* tab reports values, errors, percentages and
likelihood intervals, and the *Data table* (207 rows × 5 columns, `N=207 | χ²ᵣ`)
is clean. Fitting takes ~0.05 s.

**But every fit reports a physically impossible shape factor.** From the shipped
defaults, one click of **Fit** returns `s = −4.2635 ± 0.0661`, likelihood
interval `[−4.3296, −4.1973]` — a negative axial/lateral ratio, printed with the
same confidence as the good parameters. The equations use only `s²`, so ±s are
indistinguishable: restarting `s` at `+3.5` gives `+4.2288` with an *identical*
χ²ᵣ of 7.6918. Nothing bounds `s`, and the same hole bites the bunching model:
`3D Gauss, 1 bunching` converges to `ba = −0.36188 ± 9.49e-5 (0.0 %)` and
`bt = 6.2e-6 ms` (≈6 ps, three orders of magnitude below the 13.6 ns first lag,
"no estimate"), while χ²ᵣ gets *worse* (7.6918 → 7.7777). See RF-018.

**And the diffusion time depends on the noise model.** Same file, same equation,
same range 20…206, same start values: `Photon-noise (Suren)` (restored from user
settings on this machine) gives `td = 0.2086 ms`, `s = ±4.23`, χ²ᵣ = 7.69, while
`From file (default)` gives `td = 1.0564 ± 0.0224 ms` (2.1 %), `s = 0.3053`,
χ²ᵣ = 2.41. Both are reported with ~2 % intervals and no hint that the headline
number moved by a factor of five (RF-019).

**The FCS parameters block shows a wrong brightness.** After the fit the panel
(and the server-side fit DTO) report `cpm = cpm_all = 18.2639 kHz`, i.e. exactly
the total count rate `S`, although `N = 0.37083` — the correct counts-per-molecule
is 49.25 kHz. A traced `compute_cpm` shows the right value *is* computed during
the fit (49.2511) but only reaches the display after some later model update
(RF-021).

**Every FCS fit dumps six ERROR tracebacks at creation** — `parameter.set_value`
and `parameter.set_fixed` for `S`, `cpm`, `cpm_all` all fail with
`RemoteError: fit not found`, because the widget addresses the RPC with
`fit_index=getattr(self.fit, "fit_idx", None)` and `self.fit` is the *member*
`Fit` of the `FitGroup`, whose `fit_idx` is `None` (the group's is 0). The same
hole makes **Apply background correction** dead: it toggles, no `fit.update`
reaches the server, and the plot is unchanged (RF-020).

**Startup is noisy and one offered experiment is a trap.** Seven
`Failed to resolve class chisurf.core.experiments.rics.*` ERRORs appear at
startup, and the Experiment combo offers `RICS` — selecting it leaves the reader
list empty and raises `IndexError: No experiment readers defined for the current
experiment`. Meanwhile the shipped `Image correlation` and `tcPDA (3-colour)`
experiments are missing from the combo. Cause: the GUI never merges the shipped
`experiment_configs.yaml` (RF-022); with a fresh settings dir all nine
experiments are present, every one with readers, and there are zero ERRORs.

Also stumbled over: `test/gui/test_gui_chisurf_main.py` — the only end-to-end
"load data → add fit" GUI tests, including the FCS one — fails on
`gui.pushButton_2` (renamed to `toolButton`), so this workflow currently has no
working regression test (RF-023).

## UX / UI suggestions

- **Give the shipped FCS models bounds and units.** `models.yaml` carries only
  `equation` / `initial` / `description`. `s > 0`, `0 ≤ ba ≤ 1`,
  `bt ≥ first lag`, `N > 0`, `td > 0` are all knowable up front, and the per-
  parameter editor already has a *Bounds / Low / High* section to display them.
- **Label the units.** `td 0.20858`, `bt 6.2e-06` and the range boxes are bare
  numbers; the plot says `ms` but the editor and *Info* tab do not, and
  `acquisition_time: 5.87e+01` / `mean_count_rate: 1.83e+01` have no unit either.
- **Spell out `S`, `B`, `cpm`, `cpm_all`, `s`, `ba`, `bt`** — the *FCS
  parameters* block uses one- and two-letter names with no tooltip. `s` in
  particular is the aspect ratio ω_z/ω_xy, not a "sigma".
- **Say which noise model is in force, in the fit window.** The reader's *Mode*
  choice is persisted across sessions and silently rescales every χ²ᵣ (file
  errors mean 0.0255 vs photon-noise 0.0130). It belongs next to χ²ᵣ, not only in
  the Read-data dock the user filled in three steps earlier.
- **The rendered equation is invisible by default** — the description box is
  capped at 120 px for a 175 px document, so it shows the heading "Equation:" and
  nothing else; the typeset formula appears only after scrolling (RF-025). It is
  also black-on-white inside the dark theme.
- **The raw-equation line edit shows the tail of the formula**
  (`/abs(N)*(1+x/td)**(-1)/sqrt(1+1/s**2*x/td)`) with the leading `b+1` scrolled
  out of sight, and the model-file path is left-clipped to
  `f/chisurf/core/models/fcs/models.yaml`.
- **The relative-error buttons read `0%`, `0%`, `2%`, `NA`** with no label — a
  user cannot tell they are the fitted uncertainties, and `0%` is a rounded
  `0.1 %`.
- **Nothing indicates that channel 0…20 is an afterpulsing artefact.** The auto
  range includes it, one point at 5.4e-5 ms drives χ²ᵣ from 7.7 to 12.2, and
  restricting the range is the standard FCS move — an "exclude short lags" hint
  or a default lower bound would save every user the same discovery.
- **The `Parameter scan` tab is the same dead end as in the TCSPC workflow**:
  an empty black plot on a −0.5…0.5 axis, no parameter selector, no run button;
  its `Chi2-Surface` sub-tab clips the top y-axis label.
- **The *Residuals* tab plots against channel index** with no axis labels, while
  the *Fit* tab shows the same residuals against `t_c (ms)`.
- **The *Data table* has no error column** although the weights come from `ey`,
  and its last column (`mask`) is stretched over ~640 px while the five numeric
  columns are squeezed into the left third.
- **Internal names leak into the UI**: the fit is called
  `Parse-Model - ExperimentDataCurveGroup` in the fit list, the *Info* tab and
  the "Please wait fitting…" message, and its *Model type* is `ParseFCSWidget`
  (RF-024). The window title gets it right (`Parse-Model - Kristine_with_error`).
- **Developer trace text reaches the status bar** — after loading an FCS file the
  status bar reads `PDA TRACE: core_data.add_dataset finished successfully`, and
  after creating a fit `Parameter 'bt' has no controller to finalize.` (that
  warning is logged 24× per fit creation).
- **`Apply background correction` is indistinguishable from broken.** With the
  default `B = 0 kHz` the correction is a mathematical no-op
  (`background_factor_ac(18.26, 0) = 1.0`); with `B = 2 kHz` it takes effect only
  after an unrelated update and then rescales the model (k = 0.793) leaving
  χ²ᵣ = 4090 on screen with no prompt to re-fit. Disable it while `B = 0`, and
  re-fit (or warn) when it is switched on.
- The bottom dock tabs still truncate to *"Read…" "Dat…" "Anal…" "Plot setti…"
  "Con…" "Log…"* at 1700 px, and the fit window's custom title-bar button reads
  `C...e` — as in the TCSPC workflow.

## Bugs filed

- RF-018 — FCS parse models have no bounds: `s` fits negative, `ba` negative,
  `bt` far below the first lag, all reported with tight intervals.
- RF-019 — the reader's noise-model choice moves the fitted diffusion time by 5×
  with no warning.
- RF-020 — `ParseFCSWidget` addresses its RPCs with a `None` fit index; every
  call fails "fit not found" (6 ERROR tracebacks per fit; dead background-
  correction checkbox).
- RF-021 — `cpm` / `cpm_all` display the total count rate instead of `S/N` right
  after a fit.
- RF-022 — the GUI never merges the shipped `experiment_configs.yaml`, so an
  upgraded install offers a dead `RICS` experiment (IndexError on selection) and
  hides `Image correlation` / `tcPDA (3-colour)`.
- RF-023 — `test/gui/test_gui_chisurf_main.py` (the load-data → add-fit tests,
  incl. FCS) fails on the renamed `pushButton_2`.
- RF-024 — fits are named after the container class
  (`Parse-Model - ExperimentDataCurveGroup`) and typed by widget class
  (`ParseFCSWidget`).
- RF-025 — the model editor's rendered equation is out of view by default.
