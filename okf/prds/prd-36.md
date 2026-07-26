---
type: PRD
prd: "36"
title: "PRD-36: Dockable-Tool Base Migration Tracker"
description: Tracks the per-tool rollout of the shared dockable-tool base across remaining QMainWindow plugin tools so drag-drop, dock, geometry, and MMFDB-connectivity boilerplate is implemented once.
status: in-progress
phase: "cross-cutting"
resource: chisurf/gui/widgets/tools
tags: [prd, gui, plugins]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
Tracks the incremental rollout of the shared dockable-tool base (`ChisurfDockTool` + `PathDropListWidget`) across every remaining `QMainWindow` plugin tool, so the path drag-drop, docking, window-geometry persistence, and lazy MMFDB-connectivity boilerplate is implemented once rather than re-forked per tool. It documents the per-tool migration recipe (subclass the base, swap the drop widget, delete duplicated drop handlers, route MMFDB acquisition through the base, lazy-load the GUI tool, add an offscreen construction smoke test), lists tools already migrated, and enumerates the priority-A drag-drop and priority-B plain-window backlog. Non-`QMainWindow` wizard tools are out of scope for this base.

# Status
In progress. The base, smoke-test pattern, and the repo-wide read-only-construction guard exist; eight tools are on the base and a backlog of ~18 tools remains.

# Goal

Track the per-tool rollout of the shared dockable-tool base
(`chisurf/gui/widgets/tools/ChisurfDockTool` + `PathDropListWidget`, PRD-23 Task 1)
across every remaining `QMainWindow` plugin tool, so the drag-drop / dock / window-
geometry / MMFDB-connectivity boilerplate is implemented once and not re-forked. This
is the incremental rollout half of **PRD-23**; the base, smoke-test pattern, and the
read-only-construction guard already exist.

# What the base provides (reuse, don't fork)

- `PathDropListWidget(parent, *, path_filter=None)` — the drop list (optionally
  extension-filtered) every tool copied.
- `ChisurfDockTool(QMainWindow)` — window-level path drag-drop → `on_paths_dropped`
  hook (default → `_add_paths`), geometry persistence (`tool_settings_name`), and
  lazy MMFDB accessors (`acquire_mmfdb_connection`/`mmfdb_connection`/`mmfdb_connected`)
  that do **no** work on construction.

# Migration recipe (per tool)

1. Subclass `ChisurfDockTool` instead of `QtWidgets.QMainWindow`; set
   `tool_settings_name`.
2. Replace any private `DropListWidget` with `PathDropListWidget` (pass `path_filter`
   if it filtered by extension).
3. Delete the tool's window-level `dragEnterEvent`/`dropEvent` (the base dispatches to
   `on_paths_dropped` → `_add_paths`).
4. Route MMFDB connection acquisition through `acquire_mmfdb_connection` (delegate the
   tool's `_db()` to it); no `MFDatabase`/`_get_global_db` in the view.
5. Lazy-load the GUI tool in the plugin `__init__.py` (PEP 562 `__getattr__`) so the
   `api`/`cli` import headlessly.
6. Add an offscreen construction smoke test (PRD-23 Task 3) asserting it constructs,
   `isinstance(tool, ChisurfDockTool)`, and opens no MMFDB connection on init.

# Done (reference + rollout)

- [x] `burst/burst_selection` — reference transformer.
- [x] `tttr/tttr_microtime_shifter` — reference transformer.
- [x] `tttr/tttr_time_windows` — first rollout; drove the `path_filter` generalization
      (extension-filtered drop list).
- [x] `burst/accurate_fret`, `microscopy/img_coloc`, `microscopy/img_drift`,
      `microscopy/img_precision` — born on the base (new tools, never forked the
      boilerplate); they were never on the backlog below.
- [x] `modelling/fps_json_editor` — priority-B rollout; the base's window-level drop is
      overridden to load the first dropped `*.fps.json` into the editor, geometry is
      persisted under `FpsJsonEditorTool`, and a construction smoke test pins both.
      The plugin's own `test_root_import_does_not_import_gui` boundary check moved to a
      clean subprocess, since the new GUI smoke test legitimately imports `gui.tool`
      into the same session.

The canonical list of migrated tools is `grep -rn "class .*(ChisurfDockTool)"
chisurf/plugins`; keep this section in sync with it.

# To migrate

**Priority A — drag-drop tools (highest ROI; they copied the drop widget / drop
handlers):**

- [ ] `burst/burst_bva/gui/tool.py` — `QMainWindow`, drag-drop.
- [ ] `burst/burst_mle_analysis/wizard.py` — drag-drop (verify it is a `QMainWindow`,
      not a `QWizard`/`QWizardPage`; only the `QMainWindow` form fits this base).
- [ ] `tttr/ptu_alex_creator/wizard.py` — drag-drop (same `QMainWindow` caveat).

**Priority B — plain `QMainWindow` tools (adopt for geometry + MMFDB status + the
read-only-construction guarantee; no drop list to dedupe):**

- [ ] `tttr/trace_browser/gui/tool.py`
- [ ] `tttr/tttr_image_browser/gui/tool.py`
- [ ] `tttr/tttr_lut_tools/gui/tool.py`
- [ ] `pch/gui/tool.py`
- [ ] `calculator/fret_calculator/gui/tool.py`
- [ ] `fluorescence_decay/irf_estimator/gui/tool.py`
- [ ] `fluorescence_decay/lltf/lltf_gui.py`
- [ ] `modelling/hydropro/gui/tool.py` (`HydroProTool`; the old top-level
      `hydrogui.py` no longer defines a window)
- [ ] `traj/traj_tools/gui/tool.py`
- [ ] `core/project_browser/gui/tool.py`
- [ ] `core/lightpath_simulator/gui/tool.py`
- [ ] `core/globalview/gui/tool.py`
- [ ] `core/help/gui/tool.py`

**Out of scope for this base (not `QMainWindow`):**

- `modelling/fret/gui/wizard.py`, `modelling/fret/gui/pair_selection_wizard.py` and
  any `QWizard`/`QWizardPage` tools — `ChisurfDockTool` is a `QMainWindow` base. A
  separate thin-wizard base (or just construction smoke tests + read-only init) covers
  them. The detector wizard (`DetectorWizardPage`) already has a construction smoke
  test.
- `cookiecutter-chisurf-plugin/...` template — update the template to subclass the
  base once the API is stable so new plugins start conformant.
- `tttr/tttr_header_edit/gui/tool.py` — its tool is a plain `QWidget` (`TagsEditor`),
  never a `QMainWindow`; it was listed in error.
- `core/mmfdb_admin/gui/tool.py` (`MMFDBWidget`) and `core/setup/gui/tool.py`
  (`UnifiedSettingsTool`) already subclass `NavigationPanelTool`, itself a
  `QMainWindow` base carrying the navigation-panel contract. Reconciling the two bases
  is its own decision, not a per-tool migration; both were listed in error.

# Notes / status (2026-06-24)

- The list of `QMainWindow` tools was enumerated via
  `grep -rln "class .*(QMainWindow)" chisurf/plugins`; the `[drag-drop]` tag means the
  file references `setAcceptDrops`/`pathsDropped`/`DropListWidget`/`dropEvent`.
- The read-only-construction rule is already **enforced repo-wide** by
  `test/test_no_db_writes_in_widget_init.py` (no Qt needed), so migrations cannot
  regress it.
- Each migration is GUI and needs `QT_QPA_PLATFORM=offscreen` + Qt bindings to run its
  smoke test.

# Relationships
- The rollout backlog for [PRD-23](prd-23.md) Task 1 (thin dockable tools); each migration also advances Task 3 (smoke tests) and reinforces Task 4 (read-only construction).
- Touches the [plugin system](/architecture/plugin-system.md) and the [Plugins target](/specs/plugins.md); read-only-construction rule keeps tools from opening [MMFDB (current)](/architecture/mmfdb.md) connections on init.
