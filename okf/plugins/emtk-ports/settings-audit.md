# Settings plugins: Qt vs emtk audit (2026-10-01)

Objective (owner): migrate from Qt to emtk; swap a plugin to emtk **only when it is fully tested** and passes four
checks: **1 looks good, 2 feature parity with Qt, 3 works, 4 tested**. This audit applies them to the 13 settings-type
plugins. Method: `python -m test.gui.emtk_port_parity before|after|compare <id>` in a hermetic settings folder, then the Qt
and emtk window read **side by side** (images in `settings-audit/<id>.png`: Qt left, emtk right, 1200x800, empty state).
Raw `compare` numbers are not used for the verdict (no explained differences are recorded and Qt table cells count as
controls); the verdict is from reading the pairs. Limits: empty/offline state only (no MMFDB server, no user data), so
behaviour with data is judged from tests, not from the picture.

## Verdicts

| Plugin | Look | Parity | Works | Tests (native) | Verdict |
|---|---|---|---|---|---|
| `setup` (Settings hub) | poor: opens on a generic YAML editor, large blank panel, description printed twice | **poor**: Qt hub = Getting Started wizard + 15 destinations; emtk uses a generic file editor for 10 of them (its own checklist says so) | partly | 1 file / 5 | **not ready** |
| `ai_settings` | weak: one flat column, labels at the far edge, sliders for numbers | missing the three section headers (API configuration / Models / Generation), Guide button, result area | yes | 21 | **not ready** |
| `plot_settings` | weak: panel does not fill the window, all sections open at once | missing colour swatches/pickers (hex text only) and the **live preview plot** (empty "Preview" header) | yes | 16 | **not ready** |
| `style_manager` | good | good: editor, Style File, New, Save, Apply, reset (Qt "Clear All Styles" = emtk "Reset styles") | yes | 5 (edit/save/apply/reset, cancel/failure, new, controls, Qt-free) | **ready** (candidate; see below) |
| `user_editor` | poor: nearly blank | **poor**: the whole Account form (username, display name, e-mail, role, affiliation, ...), search and table are missing | unknown (needs an MMFDB with users) | 24 | **not ready** |
| `model_manager` | poor: a text list | **poor**: Qt = searchable table (Model / Experiment / Status / Spec / Parameter UI / Shared) + selected-model pane + Disabled toggle; emtk = plain text lines (CLAUDE.md: tables are `data_table`) | yes | 15 | **not ready** |
| `plugin_manager` | decent (docks, list, details, global settings) | partial: list is text lines without Version / Category / Status / Requires columns; no dependencies table or search box in the details | yes | 37 | **not ready** |
| `setup_channel_definition` | plain: stacked full-width buttons | partial: Qt single page with the detector table; emtk is six tabs and only the Setups tab was captured here | yes | **0** (the shared editor is tested through other plugins) | **not ready** (no tests of its own) |
| `fcs_channel_preset` | good | good: detector setup, Public, Reload, A/B pairs, table, Save/Apply/Import/Export/Delete/Close, Help, Guide | yes | 11 (CRUD, drafts, invalid records, duplicates, export/import, MMFDB path, public flag, tooltips, Qt-blocked draw) | **ready** |
| `tttr_lut_tools` | okay | empty state differs: Qt draws the two plots (raw TAC histogram with the orange region, corrected preview) before any data, emtk shows a text prompt; parameter set matches | yes | 23 | **not ready** until the plots are checked with data |
| `boarding` | plain | Qt wizard has 8 steps (Welcome, Settings, Fix / Initialize, Experiments, Dependencies, Detector setup, FCS channels, Finish) with Back/Next; emtk has 4 pages (Welcome, Repair settings, Status, Finish), no Back/Next, no embedded detector or FCS editors | yes | 23 | **not ready** |
| `switch_user` | not compared: the Qt dialog blocks offscreen (its `before` capture hangs) | unknown | unknown | **0** | **not ready** (no tests, no baseline) |
| `menu_switch` | n/a (emtk only, no Qt tool) | n/a | yes | **0** | n/a, needs tests |

Two plugins pass all four checks today (`style_manager`, `fcs_channel_preset`). `style_manager` is accepted on the empty-state
pair plus its five tests; its Open/Save As file dialogs are covered only by the generic dialog tests, so a populated-state
screenshot pair is still owed before it is called final.

## What "swap" means in the app and what was done

In the working tree the launcher (`registry.select_gui_entrypoint`, part of the owner's uncommitted emtk-entrypoint migration,
absent from HEAD) opens the emtk version in the default mode **whenever a manifest declares `entrypoints.emtk`**, so every plugin
above with weak results was already swapped. A readiness gate now keeps the Qt tool the default for plugins listed in
`chisurf/core/plugin/emtk_preview.json` (`mode = emtk` still opens the preview, for testing). A plugin leaves the list only
with an accepted report in `okf/plugins/emtk-ports/<id>/` (guard test). The list: `setup`, `ai_settings`, `plot_settings`,
`user_editor`, `model_manager`, `plugin_manager`, `setup_channel_definition`, `tttr_lut_tools`, `boarding`, `switch_user`.

## Work plan (one PRD-153 cycle each, in this order; every cycle ends with a report and removes the id from the preview list)

1. `model_manager`: table (`data_table`) with search, selected-model pane, Disabled toggle. Smallest, clearest gap.
2. `user_editor`: account form, search, table (needs an MMFDB with users for the populated state: use a temp database).
3. `plot_settings`: colour swatches/pickers, live preview plot, section layout filling the window.
4. `ai_settings`: grouped sections, labels beside fields, Guide, result area.
5. `plugin_manager`: table columns, dependencies table, search.
6. `setup_channel_definition` and `tttr_lut_tools`: populated-state pairs (detector table; plots with data), tests of their own.
7. `boarding`: the eight steps with Back/Next and the embedded editors.
8. `setup` (hub): adopt the dedicated panels of the accepted plugins instead of the generic YAML editor, open on Getting Started;
   last, because it depends on the others.
9. `switch_user` / `menu_switch`: tests, and a Qt baseline for `switch_user` by constructing the dialog non-modally.

## Evidence

`settings-audit/<id>.png` (Qt left, emtk right). Raw capture in `/tmp/sa` is not kept; re-derive with
`CHISURF_SETTINGS_DIR=<tmp> MMFDB_SETTINGS_DIR=<tmp> MMFDB_DATABASE_PATH=<tmp>/m.db python -m test.gui.emtk_port_parity before <id> --out <dir>`
(then `after`). Trap: `before switch_user` never returns (modal dialog); run it under a timeout.

## Settings hub (`setup`) upgraded, 2026-10-03

Step 8 of the work plan is done: the hub hosts the dedicated accepted panel of every destination and opens on Getting Started
([report](setup/REPORT.md)). Where to pick this up: (1) Acquisition simulator sections that are Qt-only (per-species table,
kinetics, decay editor, channel switches, vendor card dialogs); (2) the ChiSurf Settings per-setting Help column and its colour,
folder and theme pickers; (3) `switch_user` / `menu_switch` (step 9); (4) the reviewer removes `setup` from
`chisurf/core/plugin/emtk_preview.json` (the preview list is then empty).
