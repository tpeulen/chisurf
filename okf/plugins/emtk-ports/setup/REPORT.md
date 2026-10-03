# emtk port report - `setup` (the Settings hub)

Upgrade of the existing emtk app (UPGRADE_BRIEF + PRD-153), 2026-10-03. Verdict: **ready for the swap** (reviewer removes `setup` from `chisurf/core/plugin/emtk_preview.json`; not edited here). The hub opens on Getting Started and hosts the DEDICATED accepted emtk panel of every destination; no destination falls back to the generic YAML editor.

## 0. Header

| Field | Value |
|---|---|
| Plugin | `setup` (`chisurf/plugins/core/setup`), Setup -> Settings |
| Type | A: Qt `NavigationPanelTool` (search + list + stacked panels + Back / fast-forward / Next + Guide / ?) -> emtk hub hosting child apps |
| Commits | `b3e5fc8f0` baseline + pre-upgrade; `53f8d2a46` code + tests; evidence + report + docs + log (third commit) |
| Board | `okf/agent-board.md` (claim appended) |

## 1. State at start

The plugin folder held the earlier stream's uncommitted `__init__.py` / `manifest.json` changes and untracked `gui/app.py`, `gui/model.py`, `gui/guide.json`, `gui/help.md`, `test/test_native.py`, `EMTK_CHECKLIST.md`. The audit (settings-audit.md): the emtk hub opened on ChiSurf Settings and used a generic YAML editor for 10 of 15 destinations. Archived in `pre-upgrade/` (test_native.py, EMTK_CHECKLIST.md, the tracked diffs). **Not archived:** the earlier `gui/app.py`, `gui/model.py`, `gui/guide.json`, `gui/help.md` were rewritten before they were copied (my oversight; see `pre-upgrade/README.md`).

## 2. Qt hub: control checklist (populated baseline `qt/before_populated_*`, both sizes, every destination read)

| # | Qt control | emtk | Present |
|---|---|---|---|
| 1 | Search box (substring of the destination name) | search box, same filter (`visible_panels`, test equals Qt rule); Enter opens the first match (extension) | yes |
| 2 | 15 destinations in order (Getting Started ... Plugin Check), scrolling list | same labels and order (test compares with `SETTINGS_PANELS`), list scrolls with the wheel | yes (no pictograms: deliberate, emtk default look) |
| 3 | opens on Getting Started | yes; the saved selection is restored (`export_settings`/`restore_settings`) | yes |
| 4 | Guide and ? (top right) | Guide (tour with awaits on search, destination click, Next) and ? (help window) | yes |
| 5 | status line `Ready` | `Ready`; errors and fast-forward progress | yes |
| 6 | Back / Next (greyed at the ends) | same, greyed | yes |
| 7 | fast-forward (double arrow) | `>>` visits every remaining destination, status `Fast-forward n/15: name`, becomes `||`, second press / Back / hand pick stops | yes |
| 8 | Getting Started wizard (8 steps) | hosted `BoardingApp` | yes |
| 9 | ChiSurf Settings: Language, search, tree (Setting/Value/Help), Help, Reload, Save | Language combo (stores `gui.language`, switches the catalogue), search, typed fields over the merged view (packaged defaults under the user values, save writes only differences like Qt), Open file / Reload / Validate / Help / Save / Save as / Edit source. The per-setting Help column (docs text) is not shown (see deliberate) | partly |
| 10 | Acquisition: Output folder + `...`, Chunk Size, Real-time Sim, Active Device Type, device setup | new panel `gui/acq_app.py` (spec form): Folder + Browse (folder chooser), Chunk Size 1000-65536, Real-time Sim (Simulation only), device type, simulator Acquisition / Geometry / Microtime / Performance parameters, every change stored at once. Per-species table, kinetics matrices, decay editor, channel switches and vendor card dialogs are Qt-only sections: kept untouched (gap) | partly |
| 11 | Styles, Plots, Models, User Editor, AI Settings, Plugins, Channel Definition, FCS Definitions, TTTR LUT Tools, Plugin Check | hosted accepted apps `StyleManagerApp`, `PlotSettingsApp`, `ModelManagerApp`, `UserEditorApp`, `AISettingsApp`, `PluginManagerApp`, `SetupChannelDefinitionApp`, `PresetApp`, `LutToolsApp`, `PluginCheckApp` | yes |
| 12 | Updates (quiet check, no popup) / Packages | hosted `UpdaterApp` built with `suppress_initial_notification` (as the Qt hub) / `PackageApp` (`make_package_app`: the old hub showed the updater twice) | yes |

## 3. Files

`gui/app.py` (hub, `UnavailablePanel`, `ConfigurationApp` for ChiSurf Settings only), `gui/model.py` (`Panel.entry`, `visible_panels`, `step_target`, merged `SettingsDocument`), `gui/acq_app.py` + `acq_settings_emtk.view.json` + `acq_sim_defaults.json`, `gui/hosted.py` (quiet updater), `gui/guide.json`, `gui/help.md`, `gui/settings_help.md`, `test/` (seeded world, 3 test files), `__init__.py` / `manifest.json` (earlier stream), docs. One line in `plot_settings/gui/app.py` (see section 6). `chisurf/emtk/channel_definition.py` and `~/dev/emtk` untouched.

## 4. Hosting (draw_child and events)

The hub draws the open panel with `draw_child(local_coordinates=True)` into the region right of the list, between the header strip and the status line. It forwards pointer press / release / move, **wheel**, keys, **key_release**, **focus_lost** (to every hosted app) and **file drops** in region-relative coordinates. Presses outside the region stay with the hub; keys go to the search box until a click into a panel. The emtk window does not scroll, so the list is a `begin_child`.

## 5. Evidence

`emtk/after_populated_*_{1200x800,800x600}.png` (every destination, populated: temp settings with a settings file, detector setups, 11 MMFDB users, updater fakes, models/plugins registries) next to `qt/before_populated_*`; hub states `after_populated_state_{search_plug,help,guide,fastforward_done}`. All 30 pairs read at full size. Qt at 800x600 is cramped and clips (its minimum width is 850); emtk fits. `after.json`, `compare.json` (exit 0, 97 explained, `stale_explanations` empty, 0 untooltipped, Qt-free yes), `deliberate.json`.

## 6. Regressions and layout fixes found on the way

- The new `guide.json` used string targets and broke the **Qt** hub's tour parser (`dict("search")`); targets are `{"name": ...}` now (test_plugin of plot_settings caught it).
- The emtk window never scrolls: the destination list is a child; the wheel scrolls it (test at 800x300).
- `plot_settings`: the preview forced its axis limits every frame (`COND_ALWAYS`), so the wheel could not zoom the plot even standalone: `COND_ONCE` (2 lines; plot_settings tests green). Wheel zoom and drag pan are tested through the hub.
- The hosted updater popped "Update Available" on open; the Qt hub suppresses it: built quiet.
- Packages showed the updater twice; now the package manager.
- A provider key exported in the shell appeared (masked) in AI Settings: the seeded world removes `*_KEY/*_TOKEN` variables (test).
- Sidebar 200 px (>=1100 wide), 180 (>=900), 152 below, so panels keep room at 800x600.
- A hosted panel's own Close button (FCS) did nothing visible: status line says so.
- Help text had literal `**`.

## 7. Tests

`chisurf/plugins/core/setup/test`: hub (structure, Qt-equal destination names and stepper rules, real-click opening of every destination at both sizes, layout, search typing/Enter/filter, wheel on the sidebar, Back/Next/fast-forward, Guide with awaits, Help, hosting fakes for pointer/wheel/key/key_release/focus_lost/drop, unavailable panel + Retry, remembered selection, tooltips, Qt-free subprocess with Qt forbidden, real-`~/.chisurf` untouched guard that ignores `logs` and the bytecode cache), hosted input (wheel scrolls Models/Plugins/Plugin Check/Plots, wheel zooms and drag pans the Plots preview, file drop reaches LUT Tools, Acquisition typing/Browse/device/simulator, ChiSurf Settings language/help/save/defaults-merge), `test_native.py` (kept). Deliberate breakage twice (child wheel forwarding removed; `step_target` always first panel): the wheel and stepper tests failed, restored. Final run: `117 passed in 663.97s` (`chisurf/plugins/core/setup/test` + `chisurf/plugins/core/plot_settings/test`, hermetic, real `~/.chisurf` guard active). `python -m test.gui.emtk_port_parity compare setup` exit 0.

## 8. Reuse

Used unchanged: the accepted apps of 13 destinations and their guides/help; `EmTkHelpWindow`/`EmTkGuidedTour`, `draw_sections`/`FormState` spec forms (Acquisition), `FileDialog` (folder mode), `Driver` (`emtk_test_input`), the updater fakes, `user_editor/test/seeded_db`, `settings_utils.get_chisurf_settings/prune_defaults`. New shared piece: none. Duplicates: the Qt-only simulator sections (species table etc.) were NOT re-implemented (gap). The old generic YAML editor remains only for the one destination that is a settings-file editor.

## 9. Docs

New `docs/guides/97_settings_hub.md` (figures `97_settings_*.png` from the emtk app), `docs/guides/index.md`, `docs/reference/plugins/setup.md`, `gui/help.md`, `gui/settings_help.md`.

## 10. Open gaps (5-line repros in `okf/references/known-issues.md` terms)

1. Acquisition simulator per-species table / kinetics / decay / channel switches / vendor card dialogs: Qt-only AutoForm sections (`acq_channels`, `state_table`, `rate_matrix`): repro `AcquisitionSettingsWidget` in Qt vs `acq_app`.
2. ChiSurf Settings: no per-setting Help column and no colour/folder/theme pickers (Qt `SettingsItemDelegate`).
3. Children keep their own Help/Guide buttons; the hub's top-right Guide/? explain the hub (Qt adopts the active panel's).
