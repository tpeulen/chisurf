# emtk port report — `accurate_fret` (swap-candidate upgrade, audit-all row 5)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `accurate_fret` / `chisurf/plugins/burst/accurate_fret` |
| Port type | A: the committed Qt `AccurateFretTool` hosts an emtk `AccurateFretApp(tool, on_…=…)`; the earlier stream rewrote `app.py` into a standalone app with a controller |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Effort (hours) | ~1.5 |
| Commits | `f964c0eaf` accurate_fret: Qt baseline and current emtk state; `dd38807de` accurate_fret: emtk app at parity with the Qt tool; evidence commit "accurate_fret: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

```
 M chisurf/plugins/burst/accurate_fret/gui/__init__.py
 M chisurf/plugins/burst/accurate_fret/gui/app.py
 M chisurf/plugins/burst/accurate_fret/gui/tool.py
 M chisurf/plugins/burst/accurate_fret/gui/view_model.py
 M chisurf/plugins/burst/accurate_fret/manifest.json
?? chisurf/plugins/burst/accurate_fret/gui/controller.py
?? chisurf/plugins/burst/accurate_fret/test/test_native.py
```

All committed with the app (copies/diff in `pre-upgrade/`).

**Baseline method.** The working `app.py` is the rewritten one, so the committed Qt tool can only be built with HEAD sources:
`scripts/qt_head.py` loads HEAD `tool.py`, `app.py` and `view_model.py` under their real module names and runs the parity tool's
`qt_before` (`before.png`, `before.json`: 0 Qt controls, the window is the embedded emtk app); `scripts/head_app_inventory.py`
inventories that embedded HEAD app (`before_head_app.json`, 46 controls), which is the meaningful control list.

## 2. Control checklist (committed tool → current emtk)

| # | Committed (HEAD app / hidden Qt toolbar) | Current emtk | Present? |
|---|---|---|---|
| 1 | Calibrate (with progress) | Calibrate (controller job), Stop calibration / read | yes |
| 2 | From ndX, To ndX, Share in session, Store on setup, Export CSV | same, in "Data, session and catalogue actions" (+ Refresh dye catalogue, Refresh optical priors, database path) | yes |
| 3 | Guide, Help (`guide.json`, `help.md`) | Guide, Help | yes; tour fixed (below) |
| 4 | Burst Data & Columns: file + I_DD / I_DA / I_AA / Lifetime column fields | Open burst table, MMFDB burst datasets, Channels panel (four column choices) | yes (renames) |
| 5 | Photophysics & Prior: Donor Tau, Förster R₀, Linker σ, BG DD/DA/AA, Combine with Optics Prior, Show Dynamic FRET Line | Photophysics (tau_D(0), R_0, Linker width, Dynamic line), Background (Bg I_DD/DA/AA), Optics prior (Use the optics prior, Light path, Φ, g) | yes (renames, collapsed panels) |
| 6 | Correction-factor table, status console | Correction factors / Populations / Report tabs | yes (the HEAD table overprinted its text, `before_populated.png`) |
| 7 | E–S plot with static FRET line and a draggable E/S gate (E_min/E_max tags) | E–S populations, E–lifetime and FRET lines, Accurate-E histogram | gate dropped (deliberate, below) |
| 8 | Detector setup | Detector setup tab (shared editor) | yes |

Numbers: on the suite's simulated bursts (n = 100, no bootstrap) both give α 0.0798, β 1.4283, γ 0.6162, δ 0.0596, R₀ 52.0
(`capture_populated.py` output; `test_calibration_equals_the_qt_tool` compares every factor and population row).

## 3. Files

| File | Change |
|---|---|
| `gui/app.py` | stream's rewrite + my fixes: tour `wait_for_controls`, `reveal()` (opens the panel/header/dock of a step's target), `_header()` (collapsing headers register rects, open on reveal), result tabs register rects, Calibrate keyed `"Calibrate"`, Share keyed `"Share in session"`, plot rect recorded after the plot, histogram aliased `"E histogram"`, legends `LOCATION_NORTH_EAST`, histogram y range fitted to the counts (`COND_ONCE`, re-applied when the data change) |
| `test/test_emtk_accurate_fret_parity.py` | new, 9 tests |
| `gui/controller.py`, `test/test_native.py`, `gui/__init__.py`, `gui/tool.py`, `gui/view_model.py`, `manifest.json` | stream's, committed |

`guide.json` untouched (the legacy Qt tour reads it too).

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity after accurate_fret --out okf/plugins/emtk-ports/accurate_fret
after: 41 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/accurate_fret
$ python -m test.gui.emtk_port_parity compare accurate_fret --out okf/plugins/emtk-ports/accurate_fret; echo "exit=$?"
exit=0      (the Qt side has 0 controls; the real diff is compare_head_app.json, section 5)
```

## 5. Deliberate differences (`compare_head_app.json`: HEAD embedded app → current)

| Lost entries | Why / where |
|---|---|
| `bgaa`, `bgda`, `bgdd`, `donortau(ns)`, `försterr₀(å)`, `linkerσ(å)`, `combinewithopticsprior`, `showdynamicfretline`, `lifetime(tau)`, `burstdatacolumns`, `photophysicsprior` (+ `v…` header variants) | renamed and regrouped into the spec's panels (Background, Photophysics, Optics prior, Channels); collapsed by default, so absent from the default-state inventory |
| `0.000`, `4.000`, `52.000`, `6.000` | field values of the collapsed Photophysics/Background fields |
| `e_min0.20`, `e_max0.80`, `0.1`…`0.9`, `proximityratio/frete`, `stoichiometrys`, `e–sburstscatterfretline`, `staticfretline(s=0.5)` | the HEAD E–S plot (axis ticks, labels, legend). Its E/S **gate** (drag rectangle + E_min/E_max tags) lived only in the app (`gate_x_min` …) and was never passed to the calibration: a control that changed nothing. Not ported. The new plots draw the measured classes and FRET lines |
| `ndx` | the HEAD toolbar abbreviations "📥 ndX" / "📤 ndX"; now "From ndX" / "To ndX" |
| `statusconsole`, `noburstfileloaded.`, `loadabursttable…`, `presscalibrate.`, `(thedonorchannel…)` | status texts, reworded ("No burst table loaded.", one-line hint, warning without parentheses) |

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/accurate_fret -q -p no:cacheprovider
26 passed in 25.24s
```

| Required | Test | Asserts |
|---|---|---|
| 1 | `test_calibration_equals_the_qt_tool` | factor and population rows equal `AccurateFretTool`'s (subprocess) |
| 2 | `test_native.py` (stream): source/drop/load/calibrate/cancel/export/setup store | |
| 3 | `test_every_control_has_a_tooltip` (spec walk) | every spec field and button described |
| 4 | `test_draws_calibrated_at_both_sizes[1200x800, 800x600]` | factors and classes drawn |
| 5 | `test_every_guide_target_is_drawn_and_the_calibrate_step_waits`, `test_the_legend_leaves_the_donor_only_corner_free` | 9/9 targets drawn, await only on the Calibrate step and released by the button; legend NE, donor-only data at E≈0, S≈1 |
| 6 | `test_port_is_qt_free` | |
| 7 | `test_every_control_has_a_tooltip` | inventory empty |
| 8 | `test_settings_round_trip` | R₀ survives export/restore |

Deliberate breakage: histogram range fixed at 1.0 → `test_the_histogram_is_drawn_with_its_range_fitted_to_the_counts` failed; legend back to north-west → legend test failed (`{5} == {9}`); `wait_for_controls=False` → guide test
failed (`AssertionError: (6, 'Calibrate')`). Restored.

## 7. Screenshots read

| File | Observation / fix |
|---|---|
| `before_emtk_populated_1200x800.png` | donor-only cluster hidden under the E–S legend → legend moved |
| `after_populated_1200x800.png`, `_800x600` | donor-only at (0, 1), FRET 0/1 at S≈0.5, acceptor-only at S≈0; factors table |
| `after_populated_tau_1200x800.png` | E–lifetime with static/dynamic lines |
| `after_populated_hist_1200x800.png` | first grab: the E ≈ 0.77 peak cut off at the top (range set before data) → fitted range; a second grab came out blank (an exception in my first fix, `array or [0]`) → fixed; third grab correct |
| `after_1200x800.png`, `after_800x600.png` | empty: "Load a burst table …", empty plots with axes |

## 9. Persistence, guide, help, docs

* `export_settings()`: all calibration parameters + the channel-definition settings (stream's; more than the Qt tool's AutoForm state).
* Guide: 10 steps, 1 await, all targets drawn. Help: existing `help.md`.
* Docs: no user-visible change beyond the legend position.

## 10. Blocked / open

* The result tables are hand-drawn (`im.begin_table` in `_table`), against the "tables are specs" rule; porting them to
  `data_table` sections is open.
* `guide.json` step 9 asks the user to find the donor-only population at E ≈ 0 in the **E histogram**, but `efficiency_histogram()` (view model, same in Qt) bins only the FRET populations: the step cannot be followed. Either the histogram includes donor-only bursts or the step points at the E–S plot (also read by the legacy Qt tour, so not changed here).
* The E–S plot has no gate now; if a gate is wanted it must feed the calibration (a model attribute), not only the picture.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
