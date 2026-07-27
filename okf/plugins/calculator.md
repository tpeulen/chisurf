---
type: Plugin Group
title: Calculator plugins
description: Small physical-quantity estimators — FRET, phasor and acquisition-planning calculators — gathered under a single calculators hub, plus the κ² orientation-factor calculator.
resource: chisurf/plugins/calculator/
tags: [plugins, calculators]
timestamp: '2026-07-05T00:00:00Z'
---

Calculators are lightweight, mostly-stateless tools that turn a handful of inputs into
a derived fluorescence quantity — no dataset or fit required. They live under
`chisurf/plugins/calculator/`, and a hub plugin groups them (together with the FCS and
FRET-line calculators from other groups) into one two-panel launcher.

| Plugin dir | Display name | What it does |
| --- | --- | --- |
| `calculator/hub` | Main:Tools:Calculators | Hub that groups the FRET-line, FRET/homoFRET, FCS, RICS-precision, phasor-plot and κ²-distribution calculators and embeds the selected one in a two-panel view. |
| `calculator/fret_calculator` | Main:Tools:FRET-Calculator | Combined heteroFRET and homoFRET parameter calculator (R₀, E, distances, anisotropy). |
| `calculator/phasor_calculator` | Main:Tools:Phasor-Calculator | Interactive phasor plot: universal semicircle with reference-lifetime grid, a FRET trajectory and a two-component mixing line; declarative AutoForm view. |
| `calculator/kappa2_dist` | Structure:FRET:Kappa2 Distribution | Compute/visualise the κ² orientation-factor distribution (WIC, DWT, isotropic); AutoForm view, also embedded in the hub; shared with the modelling group. |
| `calculator/rics_precision` | Main:Tools:RICS-Precision | **Planning tool: takes no data at all.** Predicts, from the intended acquisition settings plus an expected `D`, the relative error a raster-scan correlation measurement would achieve, and sweeps the pixel dwell time to show where the optimum sits. The curve is U-shaped for a physical reason: scan too fast and the molecule has not moved between neighbouring pixels, so the fitted lags sit on the flat top of the decay and the derivative w.r.t. `D` vanishes; scan too slowly and they sit in the floor. Compute is Qt-free in `core.py` (`sweep_dwell`, `line_time_for`, `default_dwell_range`) over `core/experiments/ics/precision.py` (analytic estimator covariance + Monte-Carlo propagation, the MIA `RICSPE` port). AutoForm GUI (`gui/precision.view.json` + `PrecisionViewModel`, `RicsPrecisionTool`) with a **log-log** error-vs-dwell plot — a badly-matched dwell is wrong by orders of magnitude and on a linear axis flattens the usable 2-10 % range into a line — the user's own setting marked as a diamond, a numbers table carrying the implied line/frame time, and CSV export; headless `rics-precision` CLI (`--json` for scripting, which is the practical way to sweep `D` rather than the dwell). Honest limits are surfaced rather than hidden: each point is itself Monte-Carlo (~10 % at the default repeat count) so the minimum is an order of magnitude, not a setting to dial in; and precision is quoted **per frame count, not per unit time**, so a slower scan in the comparison is also a longer acquisition. Documented in theory ({doc}`concepts/scan_precision`) and application (guide 45). |
| `core/f_test` | Main:Tools:F-Test | F-test comparing two nested model fits (confidence ↔ χ² threshold) plus the χ²-max upper limit of a single fit; declarative AutoForm view with a *From fit* loader, also embedded in the hub. |

The hub demonstrates the plugin composition pattern: it discovers sibling calculators
via their `manifest.json` and embeds each one's panel rather than reimplementing them.
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
