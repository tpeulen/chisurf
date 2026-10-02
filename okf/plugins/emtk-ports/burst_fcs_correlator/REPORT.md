# emtk port report -- `burst_fcs_correlator` (upgrade, audit-all row 61)

Commits: `5be9fd3e4` Qt baseline + stream state + hermetic test settings; `7c5a377b1` populated Qt baseline; the rebuild/evidence commit "burst_fcs_correlator: one emtk app on spec forms, tables and the shared detector editor".

## 1. State and decision
Two emtk implementations existed: the Qt tool (`gui/tool.py`) hosted the old `BurstFcsGui` (`gui/app.py`, a thin surface over the tool's *unused* Qt widgets: the `_build_central` splitter was built and then replaced by the host), and the stream's controller-based `create_app`. Now there is one: `gui/app.py` `BurstFcsApp` over `BurstFcsController`; `BurstFcsTool` only hosts it in a `ControlHost` (the `embedded` flag, `controller`, `_model`, `_curves` and the `file_list` contract the burst workflow shell uses to hand over a burst folder are kept). `BurstFcsGui` and the dead Qt widget building are deleted.

## 2. Qt checklist -> emtk
The Qt widgets (`before_populated_qt_widgets.png`) -> Setup selector -> the shared one-page detector editor on the **Detector setup** tab (`chisurf/emtk/channel_definition.py`), with **Use setup for pairs** (saved FCS pairs of the setup, else one ACF per detector) and automatic adoption when another setup is chosen; Correlator group (FCS bins (B), cascades, Fine grid, Padding +-) and Fitting group (Mode None/Simple/MaxEnt, MaxEnt reg log10, tau_D min/max, t_min/t_max) -> spec panels with typed, clamped fields (MaxEnt-only fields greyed unless MaxEnt); FCS channel pairs list -> editable `table` (Use, name, channels A/B, micro-time gates) + Add/Remove/Load/Save/Show JSON; Burst folders or BUR/BST files list + buttons (+Files, Folder, Database, All, None, Remove, Clear) -> `table` + the same buttons, drops of files/folders/settings/pairs; curve filter + list -> `table` with filter box; Correlation / Diffusion-time distribution tabs -> two plots with the Qt axes and colours; the old surface's tau_min/tau_max drag region -> two drag lines setting t_min/t_max. Gained: Run FCS/Stop with progress, Example (seeded demonstration data), Export curves, Load/Save settings (Qt: the unused `_on_*` methods), the walked guide.

## 3. Demonstration data and the populated baseline
No raw TTTR + burst fixture existed. `demo.py` writes a deterministic SPC-130 stream (eight seeded bursts, two detectors, 4 ns decay, 13.5 ns / 3.3 ps header so it reads back by itself) and its `.bst`; the same generator is the tool's **Example** button and the guide's data. The populated Qt baseline used the shipped BH SPC-132 file with six index ranges (`scripts/capture_populated_qt.py`).

## 4. Layout
`before_populated_hosted.png` / `before_populated_qt_widgets.png` -> `after_<tab>_{1200,800}.png`. Fixed in the build: toolbar, status and progress in a window of their own above the tabs (Run reachable from every tab); pair table column widths and short headers so nothing clips at 800x600; curve table and plots share the right side; the empty distribution plot says why; the guide's card gets its own window while no control is awaited (Prev/Next/Close Tour were under the docks).

## 5. Bugs found by the tests
* Tour card buttons dead under dock windows (workaround as in burst_gs); while a step waits for its control Close Tour is still under the docks (Escape closes) -- emtk gap 1.
* The file list was not reachable from other tabs (toolbar moved out of the tabs).
* A dropped settings or pairs JSON file was added as an input.
* An empty-state plot tick label ('1') at the plot's right edge cut off.
* (Pre-existing) the docs figure script and `test_gui.py` operated on the dead Qt widgets.

## 6. Tests
`pytest chisurf/plugins/burst/burst_fcs_correlator`: 95 passed, 1 xfailed (the shared editor at 800x600). `compare` exit 0 (63 controls, 0 without tooltip, Qt-free; `deliberate.json`: Settings-tab labels and renames). Deliberate breakage twice, both caught: duplicate pair names accepted -> `test_invalid_pair_edits_are_refused_with_a_message`; Select-none broken -> `test_the_use_checkbox_all_none_remove_and_clear`.
* Parity (`test_emtk_burst_fcs_parity.py`): curves equal the Qt tool's backend call (`BurstFcsClient.correlate_file`) array for array, plus an independent `tttrlib` correlation of burst 0; every fit mode; settings model and the Qt AutoForm spec (every field, range, mode labels); tables; pairs of a setup; tooltips; Qt-free; layout at both sizes; real `~/.chisurf` untouched.
* Real input (`test_emtk_burst_fcs_clicks.py`, 48): every button and field -- Run (greyed/inert while running), Stop mid-run, errors, Example, Guide/Help and the tour walked, Files/Folder dialogs and cancel, drops, Use/All/None/Remove/Clear, Database picker, pair edits (valid and invalid), Add/Remove pair, Save/Load pairs, Show JSON, correlator fields (typed, clamped, arrows, wheel), fine grid, mode radio and the MaxEnt fields, fit window, settings dialogs, curve select/filter/export, plot pan, wheel and the fit-window lines, the embedded detector editor, small window.

## 7. Reuse
Embedded: the shared detector editor (+ its `parse_ranges`/`format_ranges`), `DatasetPicker`, `data_table`/spec forms, help/tour, `DialogWindow`/`FileDialog`, `load_fcs_channel_setups`; tests: `imaging_emtk.testing.Driver` via `SatDriver`, the PSF layout checker. Replaced duplicates: `BurstFcsGui` (a second implementation of the same window), the raw JSON text box, the hand-drawn inputs. Flagged: `wizard.py` (the legacy Qt wizard) still carries its own settings JSON helpers.

## 8. Docs
`docs/guides/16_fret_fcs.md` (Burst-wise FCS section rewritten for the emtk UI, the "Known defects" progress-bar note removed because the dialog no longer exists), figure `docs/guides/figures/16_burst_fcs.png` regenerated from the app on the demonstration data (and `docs/guides/screenshots/guides_15_25.py` `_grab_16_burst_fcs` rewritten for it), `gui/help.md`, `gui/guide.json`.

## 9. emtk gap
1. `EmTkGuidedTour` card buttons are under dock windows while a step awaits its control: in a `DockManager` app, `tour.start()` on a step with `await`, press "Close Tour" at its drawn rectangle: nothing happens (Escape works).
