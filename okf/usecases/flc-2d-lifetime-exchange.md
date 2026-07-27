---
type: Reference
title: Use case — 2D-FLCS lifetime exchange
description: Resolve lifetime species and their interconversion from a photon stream with the 2D-FLCS tool (2D fluorescence-decay correlation + inverse Laplace).
tags: [usecase, fcs, flcs, lifetime, tttr, dynamics]
timestamp: '2026-07-27T00:00:00Z'
---

# Use case: 2D-FLCS — lifetime species and their exchange

**Goal:** the question neither a lifetime fit nor an FCS curve answers on its own —
*how many fluorescence-lifetime species are in this photon stream, and how fast do
they interconvert?* The tool builds a **2D fluorescence-decay correlation** (2D-FDC)
at a macro-time lag `dT`, inverts it into a lifetime–lifetime distribution whose
diagonal is the lifetime spectrum and whose off-diagonal peaks are exchange, then
uses the resolved lifetimes as fFCS filters to correlate the species against each
other and fit a relaxation time and a rate matrix.

Where it sits: after [FCS correlation from raw TTTR](/usecases/fcs-correlate-tttr.md)
and beside [filtered-FCS filter calculator](/usecases/ffcs-filter-calculator.md) —
2D-FLCS derives the species patterns from the data instead of from a reference
decay, so it needs no separate calibration measurement.

**Tool:** `Spectroscopy → Fluorescence Correlation Spectroscopy → 2D-FLCS`
(`chisurf.plugins.fcs.flc_2d.gui.tool:FlcTwoDTool`, plugin id `flc-2d`); CLI
`flc-2d`; RPC `flc2d.load_tttr / correlate / fit / lifetime_spectrum /
lifetime_lcurve`.

**Data:** the plugin's own two-state exchange simulator (toolbar **Sim**) —
τ₁ = 1 ns, τ₂ = 3 ns, k₁₂ = 30 s⁻¹, k₂₁ = 10 s⁻¹, 20 000 cps per state, 60 s, so
the ground truth is a relaxation time of 1/(k₁₂+k₂₁) = **25 ms**. A real
measurement goes in through **Open**; `test/data/clsm/Leica_SP8.ptu` was used to
check the file path (3.1 M photons, 8192 TCSPC channels @ 0.016 ns).

## Steps

1. Open the tool. The window is one dock area with a **Settings** panel and six
   result tabs (2D-FLCS map, 2D residual, Lifetime distribution, Species
   correlation, L-curve, IRF); the status bar reads *"Open a TTTR file to
   begin."* and **Run** is disabled.
2. Get data in. Either **Open** a TTTR file (`.ptu/.ht3/.pt3/.spc/.h5`) — the
   status bar reports photons, TCSPC channels and resolution, and `tmax` is set
   to the full micro-time window — or unfold **Simulator**, set τ₁/τ₂, k₁₂/k₂₁,
   brightness and acquisition time, and press **Sim**. Either enables **Run**.
3. Set the 2D-FDC window: `lag` (dT, ms) somewhere inside the dynamics timescale
   and `win` (half-width ddT, ms); `tmin`/`tmax` gate the micro-time (decay) axis
   in ns; `bins` block-rebins the map before inversion.
4. Choose the lifetime inversion: `method` (Tikhonov / NNLS / MEM), the log-spaced
   trial-lifetime `grid` and its `τmin`/`τmax`, and `log λ` (0 = pick the weight
   automatically from the L-curve).
5. Pick the IRF: **Synthetic** (Gaussian `center`/`FWHM`/`skew`), **Detect** (put
   a synthetic pulse at the decay's rise), **File** (toolbar **IRF** opens a TTTR
   file, which also switches `source` to *File*), or **None** (tail fit).
6. Leave `corr` ticked so the species-resolved correlation and the rate-matrix fit
   run after the inversion; `cascades` sets the multi-tau depth.
7. Press **Run**. The status bar walks *Building 2D-FDC… → Inverting 2D spectrum…
   → Resolving lifetimes… → Computing species correlation…* and ends on the
   result line `tau = …, … ns; relaxation … ms (k12+k21=…/s)`.
8. Read the results tab by tab: the **2D-FLCS map** (lifetime–lifetime
   distribution), **2D residual**, **Lifetime distribution**, **Species
   correlation** (auto/cross curves of the filtered species), **L-curve**
   (regularisation diagnostics) and **IRF** (active IRF over the decay).
9. Optional: unfold **1D-MEM + Gaussian** and tick `run` to add the explicit
   maximum-entropy distribution and its Gaussian decomposition to the lifetime
   plot.

## Expected

- Two lifetime species near 1 ns and 3 ns in the lifetime distribution, and the
  same two on the diagonal of the 2D map, with exchange showing up off-diagonal
  once `lag` approaches the relaxation time.
- A relaxation time near **25 ms** and a rate pair near k₁₂ = 30 s⁻¹,
  k₂₁ = 10 s⁻¹ from the species correlation.
- A structureless 2D residual and an L-curve whose highlighted corner sits at the
  knee.
- Every control that is on screen changes the result; anything the analysis
  cannot do is said out loud rather than skipped.

## Observed (last run: 2026-07-27)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through the real
`FlcTwoDTool`: constructed, simulated, ran, then re-ran across ten setting
combinations and one real `.ptu`, with a screenshot read at every step.

**The physics comes out right, and fast.** On the default 60 s simulation
(1 201 098 photons) **Sim** took 1.5 s and **Run** 2.7–5.4 s end to end. The
lifetime distribution resolved **0.90 ns and 2.91 ns** against a truth of 1/3 ns,
and the species correlation returned **25.1 ms** relaxation
(k₁₂+k₂₁ = 39.9 s⁻¹ vs. 40 truth; the split, k₁₂ = 32.4, k₂₁ = 7.4, is within the
usual amplitude-ratio slop). The IRF tab is genuinely useful — the synthetic
prompt drawn over the measured decay is exactly the picture needed to judge the
`center`/`FWHM` guess. Loading a real 12.6 MB CLSM `.ptu` took 0.7 s and the whole
analysis 2.6 s. The MEM 2D inversion (2.8 s) logs its outer iterations.

**What a user cannot see, and what does nothing.** The rest of the run was about
the gap between the numbers underneath and the window on top:

- The **2D-FLCS map** — the output the plugin is named for — is drawn as a bare
  pixel block with **no axes at all** (screenshot `11_tab_2D_FLCS_map.png`): no
  τ₁/τ₂ scale, no ticks, no colour-bar units. A peak can be seen but not read.
  The same holds for the 2D residual (RF-403).
- That map resolved a **single** broad lifetime (`peak_lifetimes = [1.07 ns]`)
  while the 1D inversion in the *same* run resolved 0.90 and 2.91 ns, and its
  residual is anything but structureless — range −289 234 … +39 802, 6.9 % of
  pixels past ±10⁴, diagonal mean +7 622 against off-diagonal −2 596. The backend
  returns `chi2 = 2021.8` and the selected `reg = 54.0` in the same payload and
  the GUI shows neither, so a bad 2D fit is indistinguishable from a good one
  (RF-404).
- The **Kinetics (advanced)** panel — the `gMEM` toggle and the `lags` spin box —
  is **dead**: `run_global_mem` and `n_lags` are set in the model, described in
  the view spec, and never read by the GUI, although `fit/global_mem.py`
  implements the feature. Ticking gMEM changes neither the runtime (0.5 s) nor
  any output (RF-396).
- `tmin`/`tmax` gate the 2D-FDC only. The lifetime distribution, the L-curve and
  the IRF preview are computed on the full micro-time window regardless
  (RF-397) — and an inverted gate (`tmin` 10 ns > `tmax` 2 ns) is accepted
  silently, yields an **all-NaN 2D map** (a blank black panel,
  `30_badgate_map.png`) and a status bar that still reports
  *"tau = 0.90, 2.91 ns; relaxation 25.1 ms"* (RF-398).
- The `method` radio's **NNLS** — the default — never reaches the 2D inversion:
  it is mapped to Tikhonov, and `grid` is silently capped at 32 components for
  the 2D map (asked for 40, got a 32×32 spectrum) (RF-399).
- Halving the acquisition to 30 s (601 088 photons) left the inversion with one
  peak, so the whole dynamics stage **silently no-opped**: `corr` still ticked,
  the Species correlation tab blank (`32_30s_correlation.png`), status bar
  *"Resolved lifetimes: tau = 2.68 ns"* with no word about the skipped step. With
  `source = Detect` no peak is found at all and the status line degenerates to
  the malformed *"Resolved lifetimes: tau =  ns"* (RF-401).
- Ticking the 1D-MEM leaves the status bar reading *"Building 1D-FDC + 1D-MEM…"*
  forever — the final result line is written *before* the MEM step runs
  (`31_mem1d_lifetime.png`, RF-402).
- The species correlation is computed out to **268 s of lag for a 60 s
  acquisition**; the last decade is noise (G swings −0.68…5.46) and it sets the
  x-range, so the real decay uses half the plot (RF-405). Both auto-correlations
  are drawn in the same cyan, so the legend's *auto 0* / *auto 1* cannot be told
  apart on the canvas (RF-406).
- The **L-curve** panel marks as *"chosen"* the point with the **lowest**
  corner score of the 24 sampled (0.025, at the flat under-regularised end); the
  curvature+chord score peaks at index 7 and the visible knee is further right
  still, so the auto-selected weight (5.8·10⁻⁴) is effectively "no
  regularisation" (RF-407).
- The built-in simulator clips every overflowing micro-time into the last TCSPC
  channel: 16 921 photons (1.41 % of the stream) in bin 3126, **705×** its
  neighbours and **7.7×** the true decay maximum. It inflates the reduced χ² of
  the 1D inversion from 1.08 to 6.48 and normalises the IRF tab's decay to an
  artefact, so the real decay only reaches 13 % of the plot height (RF-400).

Peaks that land exactly on the trial-lifetime grid edge are reported without
comment: `source = None` gives *"tau = 0.30, 1.06 ns"* (0.30 = `τmin`) and the
real `.ptu`, run with the default synthetic 0.5 ns prompt against its own 8192
channels, gives *"tau = 8.00 ns"* — exactly `τmax`, the classic sign of a
meaningless inversion.

## UX / UI suggestions

- **Put units in the labels.** `lag`/`win` are ms, `tmin`/`tmax`/`τmin`/`τmax`/
  `center`/`FWHM` are ns — none of them say so; only the tooltip does. A `ms`/`ns`
  suffix on the spin boxes costs nothing and removes the one ambiguity that
  silently ruins a run.
- **Say what was actually used.** A one-line result header (photons, dT/ddT in
  ticks *and* ms, effective grid, chosen λ, χ² of both inversions) would make the
  silent caps and auto-choices visible without opening a debugger.
- **Warn on grid-edge peaks.** A resolved lifetime sitting on `τmin`/`τmax` should
  be flagged in the status line; today it reads like a result.
- **Prime the settings from the data.** After **Open**, the τ grid, the IRF centre
  and `lag` are still the simulator-scale defaults; deriving a starting `center`
  from the decay rise and a τ range from the micro-time window would spare every
  first run on a real file.
- **Progress.** Long steps only update the status bar via `processEvents`; the
  window is unresponsive during the 2D inversion. The shared `ChiSurfProgress` /
  AutoForm `progress` section would fit here, and matters more on the 3 M-photon
  files the tool otherwise handles well.
- **Normalise what is overlaid.** In the lifetime plot the 1D-MEM curve
  (amplitude ~1000) is drawn on the same axis as the NNLS distribution (~180), so
  the primary result is squashed at the bottom of the panel; both should be
  area-normalised, or the MEM given its own axis.
- **Log-y on the IRF panel.** A TCSPC decay is judged on a log ordinate; the
  linear normalised view hides exactly the tail the fit lives on.
- **Toolbar.** Four unadorned text actions (`Open`, `IRF`, `Sim`, `Run`); the
  house style is a `QToolButton` with an emoji glyph, and the IRF section's own
  description already refers to a button called *"📈 Open IRF"* that does not
  exist under that name.
- **Documentation.** There is no `docs/concepts/` page for 2D-FLCS and no numbered
  `docs/guides/` workflow — only the generated plugin catalogue entry and passing
  mentions in the filtered-FCS pages. Theory (what the 2D-FDC is, why the
  off-diagonal encodes exchange, the inverse-Laplace caveats) and an application
  guide are both missing.

## Bugs filed

- RF-396 — the *Kinetics (advanced)* panel is dead: `gMEM` / `lags` are never read.
- RF-397 — `tmin`/`tmax` never reach the lifetime inversion, L-curve or IRF preview.
- RF-398 — an inverted micro-time gate is accepted, produces an all-NaN 2D map and
  a success message.
- RF-399 — the **NNLS** method silently runs Tikhonov for the 2D inversion, and
  `grid` is silently capped at 32 there.
- RF-400 — the simulator clips overflow micro-times into the last TCSPC channel
  (1.41 % pile-up; χ² 6.48 vs 1.08).
- RF-401 — the dynamics stage is skipped in silence when fewer than two peaks are
  resolved; with none, the status line reads *"tau =  ns"*.
- RF-402 — the status bar is left on *"Building 1D-FDC + 1D-MEM…"* after the run
  finishes.
- RF-403 — the 2D map and 2D residual are drawn without lifetime axes or
  colour-bar units.
- RF-404 — the 2D fit's χ² and λ are discarded and the residual is shown
  unnormalised, so a failed 2D inversion looks like a successful one.
- RF-405 — the species correlation is plotted out to 268 s of lag for a 60 s
  measurement.
- RF-406 — both species auto-correlations are drawn in the same colour and named
  by index rather than by lifetime.
- RF-407 — the L-curve's *"chosen"* corner is the least corner-like sampled point.
