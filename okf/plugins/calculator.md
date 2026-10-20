---
type: Plugin Group
title: Calculator plugins
description: Small physical-quantity estimators — FRET, phasor, PSF, FCS-saturation and acquisition-planning calculators and the κ² orientation-factor calculator — each its own Tools › Calculators ribbon button.
resource: chisurf/plugins/calculator/
tags: [plugins, calculators]
timestamp: '2026-10-20T00:00:00Z'
---

## Where to pick this up

2. Measure: **no Calculators hub (done 2026-10-20).** Every calculator is its own Tools › Calculators
   button and opens in a dock of its own (the emtk shell gives each tool one); `calculator/hub`
   (registry, `CalculatorHubApp`, `csg_calculators`) is deleted with no shim. What the hub held
   and where it went: the selection + per-child settings → each calculator's own plugin state;
   the lazy background build → the shell's own; the description header → the ribbon tooltip
   (manifest `description`). Measure: `test/plugins/test_ribbon_layout.py` (`EXPECTED["Tools"]
   ["Calculators"]`), `test_plugin_icon_manifest.py::test_listed_plugins_have_distinct_icons`
   (RICS Precision 🧭, Kappa2 🎯, FCS Saturation ☀️, PSF Calculator 🧿 were re-picked for that).
   Open: the Tools tab is wide now; see [ribbon](../subsystems/ribbon.md) item 9.

1. Measure: **Static κ² from a computed distribution (landed 2026-10-13, imp.bff + chisurf, not pinned).** *compute κ²*'s
   result reaches the TCSPC FRET models' static average through the families' `kappa2_distribution` port; the rule
   for what *show κ²* draws is `chisurf/core/models/tcspc/kappa2_controls.py#used_kappa2_pairs`. Re-measure with
   `chisurf/plugins/fret_line/test/test_kappa2_regime.py` (narrow `[0.09,0.1,0.11]` vs isotropic: max |ΔE| = 0.24;
   static delta at 2/3 vs dynamic at 2/3: ΔE = 0). **Blocks the pixi `test` env:** its IMP.bff comes from the
   pinned build, so the three new tests there fail (the model has no `kappa2_distribution` port, `get_state` lacks it)
   until imp.bff's pin moves past the commit that added the port — no pixi.lock bump was made in this change.
   Trap: an empty `GraphPort([])` is *integer*-typed, and a float distribution written into it later is truncated
   to zeros ("carries no weight"); the node and the spec's port default are constructed float-typed explicitly.
   Open: the legacy Qt *show κ²* dialog (`chisurf/gui/widgets/models/tcspc/kappa2_helpers.py`) shares the rule but
   is otherwise untouched Qt.

Calculators are lightweight, mostly-stateless tools that turn a handful of inputs into
a derived fluorescence quantity — no dataset or fit required. They live under
`chisurf/plugins/calculator/` (the F-test and the FRET-line generator in their own groups),
and every one is its own **Tools › Calculators** ribbon button — no hub lists them.

| Plugin dir | Display name | What it does |
| --- | --- | --- |
| `calculator/fret_calculator` | Tools:Calculators:FRET Calculator | Combined heteroFRET and homoFRET parameter calculator (R₀, E, distances, anisotropy). |
| `calculator/phasor_calculator` | Tools:Calculators:Phasor Calculator | Interactive phasor plot: universal semicircle with reference-lifetime grid, a FRET trajectory and a two-component mixing line; declarative AutoForm view. |
| `calculator/kappa2_dist` | Tools:Calculators:Kappa2 Distribution | Compute/visualise the κ² orientation-factor distribution (WIC, DWT, isotropic); AutoForm view; the TCSPC FRET models' *compute κ²* reuses it; shared with the modelling group. |
| `calculator/fcs_saturation_calc` | Tools:Calculators:FCS Saturation | Excitation saturation and effective-volume expansion in FCS for arbitrary multi-state kinetic schemes. |
| `calculator/psf_calculator` | Tools:Calculators:PSF Calculator | 3-D point-spread function (vectorial Richards-Wolf, scalar Airy, Gaussian) viewed as a volume. |
| `fret_line` | Tools:Calculators:FRET Line Generator | Static, dynamic, WLC and mixture FRET lines for the smFRET 2D histograms. |
| `calculator/rics_precision` | Tools:Calculators:RICS Precision | **Planning tool: takes no data at all.** Predicts, from the intended acquisition settings plus an expected `D`, the relative error a raster-scan correlation measurement would achieve, and sweeps the pixel dwell time to show where the optimum sits. The curve is U-shaped for a physical reason: scan too fast and the molecule has not moved between neighbouring pixels, so the fitted lags sit on the flat top of the decay and the derivative w.r.t. `D` vanishes; scan too slowly and they sit in the floor. Compute is Qt-free in `core.py` (`sweep_dwell`, `line_time_for`, `default_dwell_range`) over `core/experiments/ics/precision.py` (analytic estimator covariance + Monte-Carlo propagation, the MIA `RICSPE` port). AutoForm GUI (`gui/precision.view.json` + `PrecisionViewModel`, `RicsPrecisionTool`) with a **log-log** error-vs-dwell plot — a badly-matched dwell is wrong by orders of magnitude and on a linear axis flattens the usable 2-10 % range into a line — the user's own setting marked as a diamond, a numbers table carrying the implied line/frame time, and CSV export; headless `rics-precision` CLI (`--json` for scripting, which is the practical way to sweep `D` rather than the dwell). Honest limits are surfaced rather than hidden: each point is itself Monte-Carlo (~10 % at the default repeat count) so the minimum is an order of magnitude, not a setting to dial in; and precision is quoted **per frame count, not per unit time**, so a slower scan in the comparison is also a longer acquisition. Documented in theory ({doc}`concepts/scan_precision`) and application (guide 45). |
| `core/f_test` | Tools:Calculators:F-Test | F-test comparing two nested model fits (confidence ↔ χ² threshold) plus the χ²-max upper limit of a single fit; declarative AutoForm view with a *From fit* loader. |

The phasor calculator is a fully declarative tool — its whole UI is a `view.json`
rendered by [GUI & AutoForm](/subsystems/gui-autoform.md), a good reference for the
"declarative UI where possible" principle in [Plugins target](/specs/plugins.md).
All calculators are discovered and activated the same way as any other plugin
([plugin system](/architecture/plugin-system.md)), receiving a `PluginContext` for the
rare cases they read session state; most are pure functions of their form inputs.
Related domain: the phasor calculator shares math with imaging [Phasor-FLIM](imaging.md),
and the κ² calculator feeds FRET [modelling](modelling.md). The RICS-precision
calculator is the group's one *acquisition-planning* member: it answers before the
measurement rather than after it, and it sits here — not with the
[imaging](imaging.md) pipeline whose theory it draws on — for the defining reason of
the group, that it consumes no dataset at all.
