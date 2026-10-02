# emtk upgrade report - `structure_tools` (audit-all row 82, port-incomplete)

Agent: claude (Sonnet), 2026-10-02, board entry `T-20261002-EMTKUP5`. Verdict: **accept with blocked items** (QuEst cannot be verified numerically on this machine, section 8). The hub listed "Native version pending" for FPS JSON Editor, Docking & Screening and QuEst; all three are now native cards in `chisurf/plugins/modelling/structure_tools/cards/`.

Commits: `92dd14957` (Qt baseline, populated; earlier stream's hub in `pre-upgrade/`), then the code/tests commit and the evidence commit.

## 1. State at start and baseline
Uncommitted stream files (`app.py`, `registry.py`, `strings.py`, `test/`, manifest `emtk` entrypoint) copied to `pre-upgrade/` and committed with the Qt baseline: `before.png`, `before_populated_fps_{positions,distances,flexfit,json,3d}.png` (hiv_rt example, 11 positions, 20 distances), `before_populated_docking_{inputs,results,score,structure}.png` (real dock run), `before_populated_quest_panel.png`. **The Qt QuEst panel does not build here**: "Failed to load QuEst: No module named 'IMP.bff.quenching'" (the arm64 env's IMP.bff has no quenching tables); `qt_fps_values.json` holds the Qt editor's values.

## 2. Checklist of the Qt controls
| Qt control | Native |
|---|---|
| Hub: search box, nav list with separators, Back / Next, fast-forward, status bar | search box, grouped list, Back / Next buttons. Fast-forward and the shared status bar: deliberate (no tool has a batch run action; each card has its status line) |
| FPS: Load, Save, Update, Clear (confirm), Help | toolbar buttons, Clear asks (Clear all / Keep), drop of a .json loads it, Guide + Help added |
| FPS Positions: Add Row, Compute AVs, Save AV MRC, table (Show, Name, PDB + browse, Chain, Res, Atom, Dye Preset, Dye Model, Details, Color, delete), row context menu, trailing empty row | `data_table` + toolbar (Add Row, Delete Row, Browse PDB..., Compute AVs, Save AV MRC) + form of the selected row (attachment lists from the structure, preset, model, colour, all 14 Details-dialog fields with the Qt ranges). Multi-row selection and the context menu: not ported (emtk `data_table` has no Ctrl-click), delete one at a time with confirmation |
| FPS Distances: Add Row, scoring-group combo with +/-, table (Show, Name, Label 1/2, Type, Details, Score set, delete), Details dialog incl. Load DA Distribution | `data_table`, toolbar, filter combo, form of the selected restraint, Load DA Distribution for pRDA |
| FPS FlexFit: set combo +/-, residues table + Add/Remove, bonds table + Add/Remove | same, `data_table`s |
| FPS JSON tab, 3D View (ChiMol, atom pick) | code editor; 3D tab is an implot3d plot (AV clouds, means, distance lines, backbone). ChiMol embedding and picking residues in 3D: deliberate (use the form lists) |
| Docking: Project, Save, fps.json, Output, Run, Clear, PDB list (Files, Database, Remove, Clear), spec form (Op, Method, Score set, Runs, Iterations, Clash k, Refine, Fixed body, sigma_DA, AV backend, P(R_DA), Movie, Resume, MC steps, Keep best, Anneal), Results/Score/Structure tabs, progress dialog with ETA and Cancel | all, from the Qt tool's own spec file; Database (MMFDB) button not ported; Stop button; progress bar with ETA and best score |
| QuEst: Simulate, Cancel, Load PDB, Guide, Help, the Project panel fields, quenching table + Reset Defaults, 3 plots, 3D structure, Project JSON, Load/Save project | all (spec read from the quest package); residue picking in ChiMol not ported |

## 3. Regressions and defects found
1. **Docking with Runs > 1 failed in the Qt tool**: `fret/api/operations.estimate_errors` passed `method=` to `imp_engine.estimate_errors`, which has `minimize:`: `TypeError: unexpected keyword argument 'method'`. Fixed (one line, `minimize=(r.method != "mc")`, `fret/api/operations.py`). With it fixed the engine returns `extra.trial_scores/trial_dirs`, not the `trial_details` the Qt `_on_finished` reads, so the Qt table would still show one row; the native card builds one row per trial from the real result.
2. The Qt FPS editor deleted the distances of a position when it was renamed, and deleted a position when its name was cleared. Native: the labels are renamed, an empty name is refused.
3. `chisurf.core.structure.av.dye_definition` is `{"a": 0}` here (the shipped `dye_definition.json` is missing), so the Qt Dye Preset combo offers a bogus "a". Native offers only real presets (Custom otherwise). **Needs the file restored: not mine** (`chisurf/core/structure/av/__init__.py`).
4. Qt docking form clips its labels ("Runs", "Iterations", "Fixed body" overprinted, see `before_populated_docking_results.png`); native two-column forms do not.

## 4. Layout
Read at 1200x800 and 800x600 (`after_populated_*`): FPS Positions first version had a form taller than the window and one choice per line (fixed: folds for Simulation/Advanced, three choices per row, file name in the table, full path in the form); docking path fields elide at the start; nothing is clipped or overlapping in the final captures. Tables have headers, plots have axes and legends (3D legend limited to the volumes).

## 5. Reuse
Used: `emtk_layout` (`layout_spec`, `button_row`, `LabelColumn`), `chisurf.emtk.help_guide` (Help window, tour), `emtk.file_dialog.FileDialog` + `DialogWindow`, `data_table` and spec forms everywhere, the Qt tool's own `fret_dock.view.json` and quest's `quest.view.json` (read, not copied), `FpsJsonModel` / naming / colours (the Qt tool's Qt-free core), `fret.core.av`, `fret.api.operations/project`, `ProjectFormModel`, `traj_save_topology/test/real_input.Ui` for the click tests. Not applicable: the detector editor. **Local duplicates**: `DockingSession.build_params` mirrors `_DockingModel.build_params` because that class lives in a Qt module (a test asserts equality; recommend moving it to a Qt-free module in the FRET plugin), `cards/shell.py` is the shared card shell of the three cards.

## 6. Tests
`python -m pytest chisurf/plugins/modelling/structure_tools/test`: **21 passed** (6 hub, 15 cards). Qt-parity: FPS load/save equals the Qt model's payload; docking request equals `_DockingModel` for all four operations and repeats; real docking and repeated docking on the HIV example. Real input: drop, tab clicks, Add Row, Clear confirmation both ways, Guide, file dialog open/pick, docking Run/missing-input/drop. NOT done (time/rate limit): the full control->test table for every field, deliberate-breakage runs, spin/arrow/wheel tests, tour walk, Qt-free subprocess test for each card (`after` shows qt-free=yes for the hub with all children).

## 7. Evidence
`after` / `compare structure_tools`: 38 controls, 0 untooltipped, qt-free yes, compare exit 0 (`deliberate.json` explains the hub-level lost tokens). Screenshots `after_populated_*`, `s_*`, `d_*`, `h_*` (scripts in `scripts/`).

## 8. Blocked / open
* QuEst: no numerical parity or simulation test is possible here (IMP.bff.quenching missing in the Qt tool as well). The card builds the form only when the model builds and shows the reason + Retry otherwise (tested). The first run on a machine with the tables is unverified.
* Per-field click coverage, deliberate breakage twice, 3D wheel/drag tests, perf of the 3D tab (about 45 s for 11 volumes in a PIL screenshot).
* Docs: `docs/guides/88_structure_tools.md` (new, registered in the index), figures copied from the captures; concept/plugin reference not regenerated (`docs-plugins` not run); the QuEst guide 80 still shows the Qt tool.
