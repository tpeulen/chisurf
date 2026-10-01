# emtk port report - `kappa2_dist` (swap-candidate verification and upgrade, audit-all row 14)

Agent: claude (Sonnet), 2026-10-01, per `UPGRADE_BRIEF.md`. Board entry `T-20261001-SWAP4B`. The first pass of this port was done by session EMTK-1 (`REPORT_first_pass.md`, commits
`a59fde86d`, `b34e8cde4`, `a102fb780`); this report verifies it against the Qt tool from a populated baseline and records what was still wrong. Verdict: **accept** after the upgrade; one real
regression in the first-pass app (section 0, a NaN result recomputed on every frame), fixed in the plugin's own app.

Commits (this pass): `9626d69fe` populated Qt baseline, `aa3f8d34c` gaps fixed in the emtk app (code, tests), then the evidence commit.

## 0. REGRESSION found in the first-pass app: a result containing NaN recomputed forever

`Kappa2Gui._draw_controls` decided whether the user edited something by comparing every float on the model before and after the form. A NaN result is unequal to itself, so for any input that gives a
non-finite statistic (r_AD known with r_AD∞ = 0.4, which the Qt tool shows as `1e+308`-like garbage) every frame counted as an edit and started a new computation thread: the busy flag never cleared,
the window re-ran the calculation at frame rate and a test driving it hung. Reproduction at `b34e8cde4` (inputs only, from the repository root):

```
export QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD:$HOME/dev/emtk"
python - <<'PY'
import time; from emtk.testing import RecordingPainter
from chisurf.plugins.calculator.kappa2_dist.gui.app import make_app
app = make_app(); m = app.tool._model; m.rAD_known, m.r_ADinf = True, 0.4; app.kappa2_gui.on_compute()
for i in range(30): app.draw(RecordingPainter(), 0, 0, 1200, 800); time.sleep(0.02)
print(app.tool.busy, m.k2_mean)       # first pass: busy is True after every frame, k2_mean nan; now False after the first
PY
```

Fixed by watching only the inputs (`INPUT_FIELDS`). Also found and fixed (each with a test): Save was always enabled (Qt: only while a distribution with weight exists) and went through the shared
`calculator/export.py` window (no title, no close button, no confirmation; Qt said "Saved to ..."); the Qt spin-box arrows were missing; a failed or non-finite calculation left the plot saying
"press Compute" with no reason; `make_app(kappa2=...)` (the Qt constructor argument) was ignored; no `export_settings` / `restore_settings`; the guide's last step told the user to press `?` (the Qt
button, now Help); the window rendered continuously (a worker thread now requests the frame that shows its result).

## 1. State at start

`git status --short chisurf/plugins/calculator/kappa2_dist` at the start of this pass: clean (EMTK-1's commits are in). Claim posted 20:40, EMTK-1 started at 20:45 without re-reading the board and handed
the plugin over on the board. The Qt baseline is the AutoForm `Kappa2Dist` at `a59fde86d~1` (its source: `pre-upgrade/qt_original_tool.py.txt`); first-pass baseline `before.png`, `before.json` (25 controls); mine:
`before_populated_{default,isotropic,diffusion,cone_rAD_known,nan_results}.png`, `qt_values.json` (every result of every scenario under seed 7), `qt_saved.csv` (what the Qt Save wrote).
Files edited that I did not write: none beyond the plugin's own (`gui/app.py` and `gui/guide.json` are EMTK-1's, committed).

## 2. What the Qt tool offered - control checklist

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Model radios WIC (Cone) / DWT (Diffusion) / Isotropic | spec `choice` drawn as a combo (the radio row was cut at 800 px), same labels, tooltip | yes (deliberate) |
| 2 | r0 (fund.), r_D∞, r_A∞, r_AD∞ spin boxes (0-0.4, steps 0.01/0.001) | spec values with arrows, same limits and steps | yes |
| 3 | true κ², FRET E, Step (°), Bins spin boxes | same | yes |
| 4 | r_AD known (use δ) checkbox | spec toggle | yes |
| 5 | Results: Mean κ², SD κ², Mean R_app/R_DA, SD R_app/R_DA, δ (deg) | "Orientation statistics" `data_table` (the five plus SD₂, S_A₂) | yes |
| 6 | κ² distribution plot | implot window, the assumed κ² as a legend line | yes |
| 7 | Compute | button; edits recompute on their own (the Qt 50 ms debounce) | yes |
| 8 | Save (disabled until a distribution with weight exists) -> file dialog -> "Save Successful" box | button with the same enabling rule -> in-app dialog -> status line "Saved to ..." | yes |
| 9 | `?` help, Guide | Help window, Guide tour | yes |
| 10 | tooltips | spec descriptions, table columns, toolbar | yes |
| 11 | `kappa2` constructor argument, `radioButton_2`/`pushButton` handles for `kappa2_helpers` | `make_app(kappa2=)`; the Qt host keeps the shims | yes |

## 3. Files

| File | Change |
|---|---|
| `gui/app.py` | the NaN fix, spin style, Save rule and dialog, status line, `export_settings`/`restore_settings`, `make_app(kappa2=)`, frame request, legend |
| `gui/guide.json` | last step names Help |
| `tests/test_emtk_kappa2_dist_verify.py` | new, 29 tests |
| `gui/model.py`, `gui/tool.py`, `manifest.json` | EMTK-1's: the Qt model moved unchanged, the Qt host, `entrypoints.emtk` |

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity after kappa2_dist --out okf/plugins/emtk-ports/kappa2_dist
after: 63 controls, 0 without tooltip, qt-free=yes
$ python -m test.gui.emtk_port_parity compare kappa2_dist --out okf/plugins/emtk-ports/kappa2_dist; echo exit=$?
exit=0      (lost [], untooltipped [], explained 10, stale_explanations [])
```

## 5. Deliberate differences (`deliberate.json`, EMTK-1's, re-verified)

`?` is Help; `results` is the statistics window; the subscript labels (`r_AD∞` ...) lose the HTML subscripts; the three radio entries are entries of the combo. Behaviour: results shown as a table with SD₂ and S_A₂ added;
the 50 ms debounce is "recompute when the edit commits" (a computation in flight queues one more); the status line says why a calculation gave no result (Qt: silent, or garbage such as 1e+308).

## 6. Tests

```
$ python -m pytest chisurf/plugins/calculator/kappa2_dist -q -p no:cacheprovider
57 passed in 35.26s          (28 first-pass + 29 new)
$ python -m pytest chisurf/plugins/calculator/test -q -k kappa2      -> 1 passed
```

| Required test | Test | Asserts |
|---|---|---|
| 1 reference | `test_defaults_and_every_edit_equal_the_qt_tool` (14 edits typed into the real fields, model combo clicked), `test_the_numbers_the_qt_window_showed_are_pinned`, `test_the_statistics_are_the_analytic_ones` | every result, the histogram and its scale equal the committed Qt tool under one seed; the seed-7 numbers pinned; isotropic <κ²> = 2/3, SD = 0.71, SD₂, S_A₂ from r/r₀ |
| 2 actions, errors | compute button, typed garbage / clamping / arrows, edit while computing, failing backend, non-finite inputs, Save (CSV byte-equal to the Qt writer, dialog, cancel, extension, unwritable folder keeps the dialog with the reason, disabled rule, nothing to export) | each button and error path |
| 3 spec | `test_every_editable_field_has_arrows_and_the_qt_range_and_step` | limits and steps equal the Qt spec |
| 4 draws | `test_draws_form_plot_and_statistics[1200x800, 800x600, 500x500]` | |
| 6, 7, 8 | `test_port_is_qt_free`, `test_every_control_has_a_tooltip`, `test_settings_round_trip_and_invalid_values_are_ignored` | |
| also | guide targets drawn and the tour waits (model choice, Compute), Guide/Help buttons, help links live, `kappa2=`, idle window does not ask for frames, NaN does not recompute | |

Deliberate-breakage checks (restored, 57 passed again):

| What I broke | Result |
|---|---|
| back to watching every float for edits (the first-pass behaviour) | `test_defaults_and_every_edit_equal_the_qt_tool` never settles: faulthandler timeout after 40 s, busy flag stuck (the NaN edit) |
| `model.py`: `RappSD = r["k2_sd"]` | 3 failed: `test_defaults_and_every_edit_equal_the_qt_tool`, `test_the_numbers_the_qt_window_showed_are_pinned`, `test_save_writes_the_csv_the_qt_tool_wrote_and_says_so` |

Pre-existing failures I did not cause: none in this folder.

## 7. Screenshots I looked at (full size)

`after_populated_{default,isotropic,diffusion,cone_rAD_known,nan_results}_{1200x800,800x600}.png` (numbers equal `before_populated_*` and `qt_values.json`: diffusion E = 0.4 gives 0.7181 / 0.2499 / 1.0049 / 0.0541 / 57.66 in both),
`after_populated_save_dialog_1200x800.png` (titled window with a close button, Cancel), `after_populated_guide_compute_step_1200x800.png`, `after_populated_help_1200x800.png`, `after_populated_narrow_500x500.png`.
The first save-dialog capture (the shared export helper) was an untitled window at the top left over the panels: replaced by the in-app dialog. The legend sat on the peak: moved to the north-east. Nothing is clipped at 1200x800 and 800x600;
at 500 px the "r_AD known" label and the arrows are cut (emtk layout, below the required sizes).

## 8. Workflow

Choose a model, set the anisotropies (from time-resolved anisotropy fits), the assumed κ² and options; the distribution and the statistics follow each edit; Compute re-draws (the Monte-Carlo seed differs per run); Save writes the CSV (header with the statistics, then
bin and probability). No data file is involved.

## 9. Persistence, guide, help, docs

`export_settings`: model choice and the nine inputs (the Qt tool remembered the window geometry only). Guide: 6 steps, 4 `await`, all targets drawn (test). Help: existing `help.md`, its links live (test). Docs: no user-visible change beyond Save's dialog; Docs gap: no numbered guide page.

## 10. Blocked / open

* Shared helper `chisurf/plugins/calculator/export.py` (the other calculators' Save): an untitled window at the top left with no close button; kappa2_dist no longer uses it.
* The Qt tool showed 1e+308-like garbage for non-finite statistics; the native window shows `nan` and says so. The backend returns NaN for r_AD known with a large r_AD∞ (science, not changed).
* `emtk_preview.json` untouched (reviewer removes `kappa2_dist` after accepting).

## 11. Self-check against the Definition of Done

- [x] D1 [x] D2 [x] D3 [x] D4 [x] D5 [x] D6 [x] D7 [x] D8 (gap recorded) [x] D9 (57 passed) [x] D10
