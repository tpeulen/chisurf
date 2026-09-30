# emtk port report — `flc-2d` (Wave 2)

Port and sections 0–11 by the implementing agent (Sonnet), 2026-09-30, who could not write this file;
the reviewer saved its hand-over text, updated section 10 with what the review did to the two emtk gaps, and
appended section 12. The agent was interrupted once by an API rate limit and resumed.

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `flc-2d` / `chisurf/plugins/fcs/flc_2d` |
| Port type | **B** — Qt `FlcTwoDTool` (`gui/tool.py`); `_FlcModel` sat in the same file and the work in the Qt class's handlers |
| Agent / date | implementing agent, 2026-09-30 (about 17 min of agent time across two runs) |
| Commits | `7c8ebf259` Qt baseline; `999fe82a2` native emtk app; `8092d7f21` evidence, log, known issues; reviewer: this report |
| Agent-board entry | `T-20260930-04` |

## 1. State at start

`git status --short -- chisurf/plugins/fcs/flc_2d` printed nothing; no live claim on the board. Files edited that the
agent did not write: `__init__.py` and `gui/__init__.py` (imported Qt eagerly; now lazy, PEP 562), `gui/tool.py`
(model cut out, handlers delegate to it), `gui/guide.json` and `gui/help.md` (wording only), `README.md`,
`manifest.json` (`entrypoints.emtk` only). `gui/flc_2d.view.json` and `gui/client.py` untouched.

## 2. Control checklist

One dock area of 7 tabs plus a toolbar and status bar.

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Toolbar Open, IRF, Sim, Run (Run greyed until a stream exists) | `button_row` actions `request_open`, `request_open_irf`, `request_simulate`, `request_run`; `enabled()`; `FileDialog`; `SnapshotJob` | yes |
| 2 | `?` and Guide | `Help` and `Guide` in the same row | yes (`?` → `Help`) |
| 3 | Status bar | `info` section `status_line` (error first) | yes |
| 4 | 2D-FDC: lag, win, tmin, tmax, bins | `value` fields | yes |
| 5 | Lifetime inversion: method, grid, τmin, τmax, log λ | `choice` (drop-down), `value` | yes |
| 6 | IRF: source, center, FWHM, skew, rise | `choice`, `value`, `toggle` | yes |
| 7 | Dynamics, Kinetics, 1D-MEM + Gaussian, Simulator | collapsible panels, same folds open/closed as Qt | yes |
| 8 | 2D-FLCS map, 2D residual with colormap | custom `image` section, `ImageCanvas` | yes |
| 9 | Lifetime distribution, Species correlation, IRF | custom `series_plot`, `implot` | yes |
| 10 | L-curve (log-log, corner marked) | custom `lcurve`, `implot`, red corner marker | yes |
| 11 | Open and IRF dialogs, window drop | `FileDialog`, `on_paths_dropped` | yes |
| 12 | Dock layout and geometry persistence | fixed tabs; scalar settings persist | partly |

Qt screenshots: `before.png`, `before_populated_<tab>.png` for all 7 tabs (60 s simulated stream, NNLS, 1D-MEM on).

## 3. Files

`gui/model.py` (new: `_FlcModel`/`FlcModel` plus `open_tttr`, `open_irf`, `set_irf`, `resolve_irf`, `simulate`, `run`,
`run_lcurve`, `update_irf_preview`, `run_dynamics`, `run_optional_mem` — the Qt handlers' code —, observers,
`enabled`, `request_*`, settings export/restore), `gui/flc_2d_emtk.view.json` (new), `gui/app.py` (new, `FlcApp`,
`make_app()`), `gui/guide.json`, `gui/help.md` (wording), `gui/tool.py` (imports the model), `gui/__init__.py` and
`__init__.py` (lazy), `test/test_emtk_flc_2d.py` (14 tests), `manifest.json` (`entrypoints.emtk`, `entrypoints.gui`
kept), `README.md`.

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity compare flc-2d --out okf/plugins/emtk-ports/flc-2d
{ "lost": [], "untooltipped": [] }
qt-free: True
exit=0
```

`after`: 51 controls, 0 without tooltip, Qt-free. `compare.json`: `lost` `[]`, `stale_explanations` `[]`, 49 `explained`.

## 5. Deliberate differences (49 entries in `deliberate.json`)

`?` → `Help`; hidden Qt item-view row numbers `1`–`7` are not controls; fields inside folds that start closed
(`gmem lags λ prior peaks τ₁ τ₂ k₁₂ k₂₁ cps`, open in `after_expanded_*.png`) and the options of closed drop-downs;
the method radios (`tikhonov`, `mem`) became a drop-down because emtk radio choices drew no per-button tooltip
(fixed in emtk afterwards, see 10.1; the drop-down is equivalent); the colormap combo appears once an image exists;
not ported: `cividis`, `plasma`, `turbo` and the pyqtgraph ImageView internals (`blur`, `divide`, `frame`, `mean`,
`menu`, `off`, `operation`, `roi`, `subtract`, `t`, `time`, `timerange`, `x`, `y`). Also not ported: Qt dock-layout
persistence. The status text after a 1D-MEM run stays "Building 1D-FDC + 1D-MEM…" exactly as in the Qt tool
(verified in `before_populated_2D-FLCS_map.png`).

## 6. Tests

```
$ python -m pytest chisurf/plugins/fcs/flc_2d -q -p no:cacheprovider
91 passed in 74.87s            (re-run by the reviewer after the agent's final restore)
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider
10 passed
```

Required tests 1–8 are in `test_emtk_flc_2d.py`: reference numbers recorded from the Qt tool before its work moved
(10 s stream: 199717 photons, map sum 65726.62, L-curve corner 7, 1D-MEM sum 3109.52; 60 s stream: relaxation
34.4825/s) and a test running the Qt tool side by side (identical arrays); actions, `enabled()`, busy greying and
readable errors; spec keys, custom-section callbacks and the 29 Qt fields kept; draws empty and populated on every
tab at both sizes; drop → load → Run → map (32,32), tau 8.00 ns; Qt-free; tooltips; settings round trip (30 settings
plus folder); guide targets resolve and the Sim step awaits the stream.

Deliberate breakage (each failed, each restored): test 1 (lag `1e-3` → `2e-3`), test 2 (`enabled()` no longer needs a
stream for Run), test 5 (`_dialog_done` starts no job).

Other failures, not from this port: `test/test_plugin_help_guide_seam.py` 22 and `test/test_prd_mentions.py` 2, all in
other plugins or stale allow-list lines; flc-2d passes its three seam tests and has no allow-list entry.

## 7. Screenshots looked at

`after_1200x800.png`, `after_800x600.png` (all seven tab labels whole), `after_populated_*.png` (60 s stream, NNLS,
1D-MEM: map with colormap, gamma, levels, axes), `after_tab_*_1200x800.png` (residual, lifetime, correlation,
L-curve with red corner, IRF — same shapes as the Qt baselines), `after_expanded_*.png`, `after_dialog_1200x800.png`.
Fixes the agent made after looking: method radios overlapped the grid field (now a drop-down); a two-column layout
clipped the `L-curve` and `IRF` tabs at 800×600 (now one tab strip plus a toolbar window); doubled empty-canvas text.
Nothing clipped, overlapping or axis-less remains. The toolbar window has about 40 px of empty space under the
buttons (minimum dock height).

## 8. Workflow

Data: the plugin's simulator (seed 1, τ 1/3 ns, k12=30, k21=10 per s) and `test/data/tttr/BH/132/BH_SPC132.spc`
(temp copy). Sim (`SnapshotJob("simulate")`, 1.2 M photons at 60 s) → Run (`SnapshotJob("run")`: 2D-FDC, 2D inversion,
lifetimes, L-curve, species correlation with rate fit, optional 1D-MEM) → peaks 0.90 and 3.17 ns, relaxation 29.0 ms,
identical to the Qt tool. Open, IRF and drop call `open_tttr` and `open_irf`.

## 9. Persistence, guide, help, docs

The Qt tool kept only geometry and dock layout; the app exports the 29 settings plus `colormap` and `folder`. Guide: 8
steps, awaits on Sim and Run released when the job finishes, not on the press. Docs: plugin README; **docs gap** — no
`docs/guides/NN_*.md` covers the 2D-FLCS tool (`17_filtered_fcs.md` is the Filter Calculator), so no screenshot replaced.

## 10. Blocked / findings (status after review)

1. **Radio `choice` had no tooltips — FIXED in emtk** (`608be8c`: `view_form._draw_choice` now sets the section's
   description on every radio button; tests fail without it). The port could switch back to radios; the drop-down is
   equivalent, so no change was requested.
2. **The docked tab strip neither scrolls nor wraps** (seven tabs need about 670 px): OPEN, recorded in
   `okf/references/known-issues.md`; avoided here with one full-width strip.
3. Legacy, unchanged: the stale status text after a 1D-MEM run.
4. The package `__init__.py` imported Qt eagerly and blocked the Qt-free proof; it is lazy now. Reviewed: the lazy
   `_build()` reproduces the earlier window class, icon, persist decorator and fallback class; the legacy tool still
   constructs offscreen with the identical 79-control inventory as the baseline.

## 11. Definition of Done

D1–D7, D9, D10 met; D8: README updated, docs gap above.

## 12. Review (reviewer, 2026-09-30)

Verified, not taken from the hand-over: commits touch only flc_2d files, the evidence folder and the agent's own log and
known-issues hunks; the whole plugin folder passes (91) after the agent's last restore; a fresh `after` gives the same
51 controls, 0 untooltipped, Qt-free; no Qt imports in `gui/app.py` and `gui/model.py`; the legacy Qt tool still
constructs with the baseline's 79 controls; populated map and L-curve screenshots match the Qt baselines. **Accepted.**
Follow-ups: the docked tab-strip overflow in emtk, `ImageCanvas` colormaps and PNG export, a docs guide page for the
tool, and dock-layout persistence.
