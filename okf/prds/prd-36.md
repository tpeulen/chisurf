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
In progress. The base, smoke-test pattern, and the repo-wide read-only-construction guard exist; fifteen tools are on the base and a backlog of ~12 tools remains.

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
- [x] `burst/accurate_fret`, `burst/burst_gs`, `microscopy/img_coloc`,
      `microscopy/img_drift`, `microscopy/img_frc`, `microscopy/img_tracking`,
      `calculator/rics_precision` — born on the base (new tools, never forked the
      boilerplate); they were never on the backlog below.
- [x] `modelling/fps_json_editor` — priority-B rollout; the base's window-level drop is
      overridden to load the first dropped `*.fps.json` into the editor, geometry is
      persisted under `FpsJsonEditorTool`, and a construction smoke test pins both.
      The plugin's own `test_root_import_does_not_import_gui` boundary check moved to a
      clean subprocess, since the new GUI smoke test legitimately imports `gui.tool`
      into the same session.
- [x] `traj/traj_tools` — priority-B rollout; geometry is persisted under
      `TrajectoryToolsTool`, and the base's window-level drop routes the first dropped
      path to the panel currently in front via the `trajectory_filename` property the
      trajectory panels share (panels without it say so in the status bar rather than
      swallowing the drop). The tab bar also tracks the active panel now, and the
      duplicated `PotentialEnergyWidget` tab was removed.
- [x] `calculator/fret_calculator` — priority-B rollout; the first migration of a tool
      with **no file input at all**. Geometry stays owned by the manifest-declared
      window statefulness (`apply_manifest_statefulness`) and the base's
      `save/restore_window_geometry` helpers are deliberately left uncalled, so the
      two mechanisms do not both write a geometry key; `tool_settings_name` is set
      per the recipe. Because the base enables window-level drops for every dock
      tool, `on_paths_dropped` is overridden to raise a declared `Information`
      message ("takes no dropped files") instead of accepting a drop and doing
      nothing. The plugin root now resolves its Qt tool through PEP 562
      `__getattr__`, so `api`/`core`/`backend` import with no Qt binding — pinned by
      a clean-subprocess boundary check alongside the construction smoke test.

- [x] `burst/burst_bva` — priority-A rollout, and the first tool whose drop target was a
      **line edit** rather than a drop list: `_FolderLineEdit` (a `QLineEdit` with its own
      `dragEnterEvent`/`dropEvent`) is gone, the folder box no longer accepts drops at
      all, and the base's window-level drop feeds `on_paths_dropped`. That also fixed a
      swallowed drop: the field-level handler wrote *any* dropped path into the folder box
      and then `_set_folder` silently ignored it unless it was a directory, so a dropped
      file left the box showing a folder BVA was not using; a non-directory now raises a
      declared `Information` message and the box is left alone. Geometry stays owned by
      the manifest-declared window statefulness plus the tool's own dock-layout
      persistence, as for `calculator/fret_calculator` and `pch`, so the base's
      `save/restore_window_geometry` are deliberately left uncalled; `tool_settings_name`
      is set per the recipe. The plugin root resolves `BVATool` through PEP 562
      `__getattr__`, so `api`/`core`/`backend`/`cli` import with no Qt binding — pinned by
      a clean-subprocess boundary check alongside the construction and drop smoke tests.

- [x] `pch` — priority-B rollout, and the first tool whose single file input makes the
      base's window-level drop *do* the work: `_on_load` was split so the file dialog
      and `on_paths_dropped` share one `_load_path`, and a dropped photon-stream file
      is now loaded exactly as the toolbar's **Load TTTR** action loads it. The
      accepted extensions are one `TTTR_SUFFIXES` constant feeding both the dialog
      filter and the drop filter, so the two cannot drift; a drop of anything else
      raises a declared `Information` message instead of being swallowed. Geometry
      stays owned by the manifest-declared window statefulness, as for
      `calculator/fret_calculator`, so the base's `save/restore_window_geometry` are
      deliberately left uncalled. The plugin root now resolves `PCHApp` through PEP 562
      `__getattr__`, so `api`/`backend`/`cli` import with no Qt binding — pinned by a
      clean-subprocess boundary check alongside the construction smoke test.

The canonical list of migrated tools is `grep -rn "class .*(ChisurfDockTool)"
chisurf/plugins`; keep this section in sync with it.

# To migrate

**Priority A — drag-drop tools (highest ROI; they copied the drop widget / drop
handlers):**

- [ ] `burst/burst_mle_analysis/wizard.py` — drag-drop (verify it is a `QMainWindow`,
      not a `QWizard`/`QWizardPage`; only the `QMainWindow` form fits this base).
- [ ] `tttr/ptu_alex_creator/wizard.py` — drag-drop (same `QMainWindow` caveat).

**Priority B — plain `QMainWindow` tools (adopt for geometry + MMFDB status + the
read-only-construction guarantee; no drop list to dedupe):**

- [ ] `tttr/trace_browser/gui/tool.py`
- [ ] `tttr/tttr_image_browser/gui/tool.py`
- [ ] `tttr/tttr_lut_tools/gui/tool.py`
- [ ] `fluorescence_decay/irf_estimator/gui/tool.py`
- [ ] `fluorescence_decay/lltf/lltf_gui.py`
- [ ] `modelling/hydropro/gui/tool.py` (`HydroProTool`; the old top-level
      `hydrogui.py` no longer defines a window)
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
