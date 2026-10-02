# emtk port report -- `fcs_saturation` (upgrade, audit-all row 63)

## 0. Header
| Field | Value |
|---|---|
| Plugin | `fcs_saturation` / `chisurf/plugins/calculator/fcs_saturation_calc` |
| Port type | A: Qt-free model + spec forms + data tables + implot plots |
| Commits | `27934ec43` Qt baseline + stream state; `9999d0221` emtk app at parity (code, tests); evidence/docs commit after it |
| Board | `T-20261002-EMTKUP6` |

## 1. State at start
Modified `manifest.json`; untracked `gui/app.py`, `gui/model.py` (copies in `pre-upgrade/`). The stream's app drew hand-made drag sliders (no typed entry), no tables, a state diagram of bare lines, ignored series colours, Qt toolbar names and guide targets that did not exist.

## 2. Control checklist (Qt -> emtk)
Compute, Guide, Help (toolbar) -> same buttons plus Load/Save scheme and Load/Save session (the Qt tool did these implicitly: preset list, auto session on close). Scheme, Laser power (spin + log slider "Power (log)"), Excitation lambda, Dye (MMFDB, filter list), Rate units, Include bunching, Number of states -> spec fields (typed, clamped, Enter, arrows, wheel). K_dark and K_exc matrices, Q table, Optics and measurement table (Name/Value/Fixed/Lo/Hi/Bounds/Error) -> `table` sections (double click to edit, checkboxes by click, diagonal / ground-state row / relaxation times read-only). State diagram (arrows with rates, node colours of the profile plot; rates edited in the tables instead of by badge drag: deliberate). Tabs State diagram / FCS curve / Info / Volume profile / Volume(P) / Diffusion time as a wrapping button row (a tab bar cannot wrap at 800 px). Plots with Qt's titles, axis labels, log axes, colours, dashes, markers; normalise, 1-component fit, three profile toggles. File drop of a scheme (gained).

## 3. Layout (1200x800, 800x600)
Before/after: `before_populated*.png`, `before_emtk_populated_*.png` -> `sat_<tab>_{1200,800}.png`. Found and fixed: the stream's controls column was a single long scroll of drag bars; at 800 px fold titles, the bunching label, the tab bar and the optics table columns were clipped (columns now have explicit widths; controls get 50 % of a narrow window; tabs wrap); a selected row's description note made a table lose its last row (note removed from Q, reserved for Optics); the toggle row of the profile tab did not wrap (stacked). Plot title of the residual plot shortened in-plot (Qt title is the tooltip).

## 4. Evidence
`after`: 81 controls, 0 without tooltip, qt-free yes. `compare` exit 0 (`deliberate.json`: choice options, parameter symbols, cell numbers, renamed labels).

## 5. Tests (`tests/`)
`python -m pytest chisurf/plugins/calculator/fcs_saturation_calc`: 180 passed (plugin total incl. the 20 older Qt/core/api tests).
* Parity (`test_emtk_saturation_parity.py`, 60): every series, summary, rates, brightness, parameter rows equal `golden_qt.json` (the Qt tool for 6 states, `scripts/capture_golden.py`) and the live Qt tool for every preset; guide anchors (V_eff/V0 = 1.000 at 0, ~1.33 at 50 uW, ~3.3 at 2 mW); every Qt-spec field in the emtk spec with range/choices; tooltips on every control and column; Qt-free; layout (clipping/overlap) on every tab x 2 presets x 2 sizes incl. 6 states; scheme and session round trips; real `~/.chisurf` untouched.
* Real input (`test_emtk_saturation_clicks.py`, 72): every control by pointer/keys/wheel/drag/drop -- control -> test: toolbar buttons (`compute_*`, `save_/load_session`, `save_/load_scheme_*`, drop); Scheme list, power typed/arrows/wheel/log slider, wavelength, dye, units, bunching, n_states typed/arrows/wheel; table cells (dark, exc, Q, optics: typed, clamped, refused, checkboxes, header click); six tab buttons; normalise, fit, profile toggles; drag pan and wheel zoom on each plot; guide (buttons, awaits, escape, walked to the end, every target real, tab per step); help (start tour, close, escape); small window flow.
* Deliberate breakage: round 1 (clamp removed) -> cross-section test failed; round 2 (relaxation rows made editable) -> its test failed. Both restored.
* Bugs found by the tests: a dropped/loaded missing scheme file was silently ignored (now an error); the guide's first step could not be completed (default already selected; now informational); an unclamped table edit; hover note hiding rows.

## 6. Reuse
Used: `imaging_emtk.testing.Driver`, `psf_calculator/tests/driving` layout checker (should move to the shared testing module; flagged), `chisurf.emtk.help_guide` (tour/help), `emtk_layout.button_row`, `emtk.view_form`, `data_table`, `FileDialog`/`DialogWindow`. Flagged duplicate: `gui/model.py` is a copy of the Qt tool's logic (`gui/tool.py`); kept (not deduplicated this pass) because parity is guarded by the golden file and live-Qt tests; replace the Qt tool's body by inheriting the model when the Qt tool is retired. Detector editor not applicable.

## 7. Docs
`docs/guides/56_fcs_saturation.md` (emtk wording, figure `docs/guides/figures/fcs_saturation_tool.png` regenerated from the app), `gui/help.md`, `gui/guide.json` rewritten for the emtk controls. Plugin reference unchanged (manifest only).

## 8. emtk gaps seen
* Data-table cell editor: Ctrl+A does not select the cell text (tests erase with Backspace).
* `table` with `tooltip_key` reserves two lines under the rows once a row is selected, shrinking the body (the spec cannot ask for the hover tooltip alone).
