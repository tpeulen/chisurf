# emtk port report - `burst_ebfret` (Track B, port complete)

Agent: antigravity, 2026-10-03. Type A. Verdict: **accept**.

## 1. State at start
ebFRET was written as a direct emtk port of the MATLAB GUI (`MainWindow.m`) with pure-NumPy VBEM/empirical-Bayes engine and client-server RPC backend (`EbfretClient`). The Qt tool (`EbfretTool`) was a wrapper embedding the emtk `App` in `ControlHost`. Declared `entrypoints.emtk` was missing `make_app`.

## 2. Parity checklist
All controls mapped directly from MATLAB / `tool.ANCHORS` (23 controls):
| Control | emtk implementation | Parity |
|---|---|---|
| Menu File / Analysis / View | `MenuBar`, `Menu`, `MenuItem` | yes |
| Time Series (Signal, Raw) | `implot.plot_line` in Time Series panel | yes |
| Select Series slider & edit | `series_value.slider`, `series_value.edit` | yes |
| Crop Min / Max / Exclude | `crop_min`, `crop_max`, `exclude` | yes |
| Ensemble plots (Obs, Mean, Noise, Dwell) | 4 ensemble `implot` canvases | yes |
| Select States slider | `ensemble_value.slider` | yes |
| States Min / Max | `min_states`, `max_states` value inputs | yes |
| Analysis Scope / Restarts / Precision | `run_scope` combo, `restarts`, `run_precision` | yes |
| Run / Stop / Reset | Buttons with client RPC callbacks | yes |

## 3. Evidence
- Screenshots: `after_empty_1200x800.png`, `after_empty_800x600.png`, `after_populated_1200x800.png`, `after_populated_800x600.png`.
- Visual inspection by agent: zero clipped text, clean layout, responsive docking and resizing at 1200x800 and 800x600.
- All 78 tests in `chisurf/plugins/burst/burst_ebfret/tests/` passed in 92.52s.

## 4. Entrypoint
- `entrypoints.emtk` set to `chisurf.plugins.burst.burst_ebfret.gui.app:make_app`.
- `make_app()` added to `chisurf/plugins/burst/burst_ebfret/gui/app.py`.
