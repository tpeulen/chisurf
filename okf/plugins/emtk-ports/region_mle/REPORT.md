# emtk port report — `region_mle` (Wave 2)

Port and sections 0–11 by the implementing agent (Sonnet), 2026-09-30; saved here by the reviewer
because the agent could not write the file. Section 10 is updated with what the review found and
fixed; section 12 is the review.

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `region_mle` / `chisurf/plugins/microscopy/region_mle` |
| Port type | **B** — a Qt `AutoFormMleTool` (`gui/tool.py`); `gui/view_model.py` is already Qt-free and was reused |
| Agent / date | implementing agent, 2026-09-30 (about 24 min of agent time) |
| Commits | `1d630e6e5` Qt baseline; `d5207db8b` native emtk app; `51cbd6a13` evidence, log; reviewer: this report, header-editor test and screenshot, `deliberate.json` wording |
| Agent-board entry | `T-20260930-03` |

## 1. State at start

`git status --short -- chisurf/plugins/microscopy/region_mle` printed nothing; no other claim on the board.
Files edited that the agent did not write: `gui/view_model.py` (one hunk in `info_html`, section 10.3),
`gui/guide.json` and `gui/help.md` (text only: emoji button names, Qt-era wording), `README.md`,
`manifest.json` (`entrypoints.emtk` only). `gui/tool.py`, `gui/region_mle.view.json` and the other Qt files untouched.

## 2. Control checklist

Three Qt tabs (Analysis, Regions, Decay), screenshotted as `before_tab_*.png`.

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | `?` and Guide | hand-drawn `Help` and `Guide` (`help.md`, `guide.json`) | yes (`?` → `Help`) |
| 2 | info text | `info` section `info_html` | yes |
| 3 | CLSM files list + `+ Files`, `Database`, `Remove`, `Clear` | custom `path_list` callback, `FileDialog`, `DatasetPicker`, drop | yes (`Add files`) |
| 4 | IRF file list + four buttons | custom `path_list` (one file) | yes |
| 5 | Analysis region editor: add rectangle/ellipse/polygon, remove, combine rule, table, save, load | custom `region_list` drawing `chisurf.emtk.regions.RegionControls` | yes — opens by clicking the `Analysis regions` header (see 10.1, `after_region_editor_open_1200x800.png`) |
| 6 | Detector channels, Fit start/stop, Micro-time binning | spec `value` attrs | yes |
| 7 | Regions panel: Detection, Min photons | collapsible panel | yes |
| 8 | Fit (Fit23): τ γ r0 ρ l1 l2, fix toggles, 2I*, BIFL scatter | collapsible panel | yes |
| 9 | Load demo, Preview, Run, Export | `button_row`, `enabled()`, `SnapshotJob` | yes |
| 10 | Open results | `Open results…` + `FileDialog` | yes |
| 11 | Regions tab: filter, region list with τ badge, summary, image + colormap | filter, combo with badge, summary, `ImageCanvas` | yes (list is a combo) |
| 12–14 | Overlays: draggable analysis region; read-only molecule ellipses; selected marker | `ImageCanvas analysis= / found= / markers=` | done |
| 15 | Decay tab: residuals over log decay, linked x | custom `decay_panel`: two `implot` plots | done |
| 16 | Guided tour | `guide.json`, 7 steps | yes |

## 3. Files

`gui/model.py` (new, `RegionMleModel(RegionMleViewModel)`), `gui/region_mle_emtk.view.json` (new; three
top-level sections = three dock windows), `gui/app.py` (new, `RegionMleApp`, `make_app()`, four custom-section
callbacks), `gui/guide.json`, `gui/help.md` (text), `gui/view_model.py` (1 hunk), `test/test_emtk_region_mle.py`
(15 tests), `manifest.json` (`entrypoints.emtk`, `entrypoints.gui` kept), `README.md`.

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity compare region_mle --out okf/plugins/emtk-ports/region_mle
{ "lost": [], "untooltipped": [] }
qt-free: True
exit=0
```

`after`: 57 controls, 0 without tooltip, qt-free. `compare.json`: `before_controls` 70, `after_controls` 57,
`lost` `[]`, `stale_explanations` `[]`, 37 `explained`. The `after` inventory is the empty state, so controls that
exist only once an image is loaded or a header is opened appear in `deliberate.json` and in the populated PNGs.

## 5. Deliberate differences (37 entries in `deliberate.json`)

`?` → `Help`; `+ Files` → `Add files`; hidden Qt item-view row numbers (`2`–`7`) are not controls; colormap
entries drawn only when an image exists (`colormap`, `inferno`, `magma`, `viridis`, `gray`); not ported:
`cividis`, `plasma`, `turbo` (`ImageCanvas` offers four colormaps) and the pyqtgraph ImageView internals (`blur`,
`operation`, `mean`, `divide`, `subtract`, `off`, `t`, `x`, `y`, `timerange`, `frame`, `menu`, `roi`); the eight
analysis-region editor entries (`combine`, `allofthem`, …) are in a header that starts closed. Also: the region
list is a combo; no pyqtgraph histogram/LUT strip.

## 6. Tests

```
$ python -m pytest chisurf/plugins/microscopy/region_mle -q -p no:cacheprovider
47 passed in 18.17s            (32 existing + 14 by the agent + 1 by the reviewer)
```

Required tests 1–8 are in `test_emtk_region_mle.py` (reference τ = 1.00002 / 3.30177 / 2.08438 / 0.60221 ns,
photons 60294 / 59958 / 129646 / 140486, taken from the legacy view model's `run()` on the same demo; actions
and error texts; spec keys and custom-section callbacks; drawing empty and populated at 1200×800 and 800×600;
Preview/Run/Export/Open end to end and a canvas drag writing `settings.roi`; Qt-free; tooltips; settings round
trip) plus the guide test. The reviewer added
`test_the_analysis_region_editor_opens_when_its_header_is_clicked`.

Deliberate breakage (each failed, each restored): test 1 (`run()` loops over `files[:0]`), test 2 (error text
changed), test 5 (`_on_event` ignores `start_run`).

Other failures, not from this port: `test/test_plugin_help_guide_seam.py` and `test/test_prd_mentions.py` together
show 23 failures in other plugins or stale allow-list lines; `region_mle` passes its three seam tests.

## 7. Screenshots looked at

`after_1200x800.png`, `after_800x600.png` (Analysis window scrolls; list buttons wrap), `after_demo_*.png`,
`after_populated_*.png` (4 regions fitted, median τ 1.54 ns, region 2 selected: τ 3.302, photons 59958, 2I* 47.224;
image with outlines, numbers and marker), `after_decay_*.png`, `after_region_overlay_1200x800.png`,
`after_dialog_1200x800.png`, and (reviewer) `after_region_editor_open_1200x800.png`. Fixes the agent made after
looking: hint text overrun shortened, list buttons wrap by measured width, Regions and Decay moved into tabs as in
Qt so the image is not squashed, residual-plot label overlap. Nothing clipped or overlapping remains; the
opened editor shows a hover tooltip over the "Combine regions" row, which is the tooltip, not a defect.

## 8. Workflow

Data: the plugin's own demo (`spot_finder/demo.py`), copied to a temp dir before Run because a run writes
`<stem>_analysis/` and `joint_output.tsv` beside its input. Load demo → Preview (4 regions, τ NaN) → Run (τ and
photons above) → pick a region (info, marker and decay follow) → Export (`regions.tsv`) → Open results reloads a
saved `molecule_data.tsv`. Overlay behaviours done: drag the analysis region (rectangle, ellipse, polygon),
molecule ellipses, selected marker, region add/remove/combine/save/load via the editor. Not done: the pyqtgraph
histogram/LUT strip, blur/normalisation and ROI button of the Qt image widget.

## 9. Persistence, guide, help, docs

`export_settings()` keys: `detector_chs_text, mtr_start, mtr_stop, micro_time_binning, min_photons, region_set, tau,
gamma, r0, rho, fix_tau, fix_gamma, fix_r0, fix_rho, l1, l2, p2s_twoIstar, soft_bifl_scatter, files, irf_files,
regions, folder, colormap`. Guide: 7 steps, awaits on Load demo and Preview released by the outcome. Docs: plugin
README only; there is no `docs/guides/NN_region_mle.md` (docs gap).

## 10. Blocked / findings (status after review)

1. **Analysis-region editor unreachable — FIXED in emtk.** `RegionControls` calls
   `im.collapsing_header("Analysis regions", 0)`; emtk read the second argument as a bool and forced the header
   closed on every frame. This was general: about 30 call sites across the ports pass `0` or
   `TreeNodeFlags.DEFAULT_OPEN` (calculators, tttr_splitter, lightpath_simulator, burst tools) and none of those
   headers could be toggled. emtk commit `e76836b` makes an int a flags word that sets only the initial state
   (bool still forces; literal `1` still means open), with tests that fail without the fix. The reviewer drove the
   real app: clicking the header opens it and shows `Add rectangle`, `Add ellipse`, `Add polygon`.
2. **Demo reads as an empty image — OPEN, in known issues** (`okf/references/known-issues.md`, "region_mle: the
   simulated demo reads as an empty image"). Backend, also broken in the shipped Qt tool; tests and populated
   screenshots use a test-side `CLSMImage` shim.
3. `info_html` fix in the reused view model (it called `.get` on the result store and raised after every
   successful run); covered by test 1. `add_paths` duplicate counting fixed in the agent's own model.
4. `chisurf/emtk/*` is untracked in the working tree; the app depends on it, as `pch` does.
5. `ImageCanvas`: four colormaps only, no PNG export (emtk feature request from the `pch` report, still open).
6. The guide target `Regions` names both the folded panel and the tab; the app maps it to the panel header.

## 11. Definition of Done

D1–D10 met. D2: the editor exists and is reachable after the emtk fix. D5: the demo workflow needs the shim of 10.2
until the backend is fixed.

## 12. Review (reviewer, 2026-09-30)

Verified, not taken from the hand-over: commits touch only region_mle files, the evidence folder and the agent's
own log hunk; 46 tests passed (47 with the reviewer's); a fresh `after` gives 57 controls, 0 untooltipped,
Qt-free; `grep` for Qt imports in `gui/app.py` and `gui/model.py` prints nothing; both blockers were reproduced
independently (blocker 1 traced to `emtk.im_widgets.collapsing_header` and fixed; blocker 2 confirmed with
`CLSMImage` shape `(1, 1, 0)`); the populated screenshot shows the same four-region result as the Qt baseline.
**Accepted**, with follow-ups: fix the demo loader (10.2), the `ImageCanvas` colormaps and PNG export, and a
docs guide page for the tool.
