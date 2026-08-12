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
Nearly done. The base, smoke-test pattern, and the repo-wide read-only-construction guard exist; 36+ tools are on the base. All tools from the original backlog have been migrated except `chimol/app/molview_main_window.py` (deferred to PRD-57's renderer/controller split) and `core/project_browser/gui/tool.py` (complicated — eagerly opens MMFDB on construction via `self.refresh()`, which must be deferred to satisfy the no-DB-on-init guard). A grep for `QMainWindow` in `chisurf/plugins/` now returns only games, standalone, README, the explicitly-deferred chimol window, the legacy burst_selector, and ProjectBrowserTool.

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

- [x] `tttr/tttr_image_browser` — priority-B rollout, and the first tool whose
      workspace already handled its own drops: `TTTRImageBrowser` accepts a dropped
      folder itself and is also embedded bare in the Image Tools shell, so its
      widget-level handlers stay. What was missing is the window: a drop that landed
      on the toolbar or the chrome reached nothing, and a dropped *file* was ignored
      twice over — the workspace's `dragEnterEvent` declines a non-directory, and the
      plain `QMainWindow` above it did not accept drops at all. `on_paths_dropped`
      now opens the first dropped directory through the view model's own
      `on_drop` seam (no second copy of "find the first directory") and reports a
      declared `Information` message for anything else. Geometry stays owned by the
      manifest-declared window statefulness, as for `calculator/fret_calculator`
      and `pch`, so the base's `save/restore_window_geometry` are deliberately left
      uncalled; `tool_settings_name` is set per the recipe. Recipe step 5 (lazy GUI
      import) does not apply: this plugin's `__init__.py` *is* the workspace widget,
      so there is no Qt-free root to protect until that module is split.
      The tool's `__getattr__` workspace delegation was hardened to read
      `__dict__` — a plain `self._workspace` there recurses without end for any
      attribute missed before `__init__` assigns it, which is exactly the window
      during which the base class initialises itself.
      Tests: `test/test_widgets.py` (+3; the blanket `except Exception →
      pytest.skip` around construction was narrowed to `ImportError`, so a
      constructor that raises is red rather than skipped).

- [x] `quenching_estimator` — recorded here late (2026-07-29). It was migrated in
      `669fce499` as part of giving QuEst a manifest and moving the `quest` import off
      module scope, and had been on the base ever since without appearing in this list —
      exactly the drift the "keep this section in sync" note below warns about, which is
      why re-running the canonical grep is part of each of these entries now.

- [x] `burst/burst_2cde` — priority-B rollout of a tool that was **on neither list**: it
      was written after the 2026-06-24 enumeration below, so it forked a plain
      `QMainWindow` while the base existed. Its only input is a burstwise analysis
      folder, named through a Browse dialog and nothing else — the window accepted no
      drops at all, so dragging the folder onto the panel did nothing and gave no
      reason. `on_paths_dropped` now takes the first dropped *directory* through
      `_adopt_folder`, the single path the Browse dialog was refactored onto, so
      "naming a folder" means the same thing both ways (set the box, then run — picking
      a folder is a request for its 2CDE, not for a button press). A dropped **file**
      raises the declared `Information.not_a_folder` message rather than being written
      into the folder box, which is the silent-drop failure the `burst_bva` migration
      removed above. Geometry stays owned by the manifest-declared window statefulness,
      as for `calculator/fret_calculator`, `pch` and `burst_bva`, so the base's
      `save/restore_window_geometry` are deliberately left uncalled; `tool_settings_name`
      is set per the recipe. Recipe step 5 (lazy GUI import) does not apply: the plugin
      root imports no Qt already. Rendered offscreen in both states (plain, and with the
      rejected-drop message in the status bar) and inspected. Tests:
      `tests/test_gui.py` (+3: on the base with a settings key and no MMFDB connection on
      init; a dropped folder is adopted and run; a dropped file leaves the box alone and
      says why).

- [x] `core/f_test` — priority-B rollout of a second tool that was **on neither list**
      (it postdates the 2026-06-24 enumeration), and the second calculator with no file
      input at all. `FTestTool` forked a plain `QMainWindow` while the base existed, so
      the window accepted no drops and had no status bar to say anything in.
      `on_paths_dropped` now raises the declared `Information.no_file_input` message —
      the same answer `calculator/fret_calculator` gives, because it is the same
      question. Geometry stays owned by the manifest-declared window statefulness
      (`apply_manifest_statefulness`, wired in `__init__` so it applies however the tool
      is launched — through the plugin registry, through the `plugin` exec path, or
      embedded in the calculator hub), so the base's `save/restore_window_geometry` are
      deliberately left uncalled; `tool_settings_name` is set per the recipe. Recipe
      step 5 (lazy GUI import) does not apply: the plugin is GUI-only — it has no
      `api`/`core`/`backend` layer to keep Qt-free. Rendered offscreen standalone in
      both states (plain, and with the rejected-drop message in the status bar) **and**
      embedded in the calculator hub, and inspected. Tests:
      `test/test_widgets.py` (+2: on the base with a settings key, drops accepted, and
      no MMFDB connection on init; a dropped path is reported rather than swallowed).

- [x] `burst/burst_fusion`, `calculator/psf_calculator`, `calculator/fcs_saturation_calc`,
      `microscopy/img_flow`, `core/pto_inspector` — each subclasses `ChisurfDockTool` but
      was missing from both Done and To-migrate (the drift this tracker exists to catch).
      Recorded here after a 2026-08-08 re-grep.
- [x] `core/globalview` — `GraphWizard(ChisurfDockTool)` was already on the base; it had
      been listed in the Priority B backlog in error.

The canonical list of migrated tools is `grep -rn "class .*(ChisurfDockTool)"
chisurf/plugins`; keep this section in sync with it.

# To migrate

**Priority A — drag-drop tools (highest ROI; they copied the drop widget / drop
handlers):**

- [ ] `burst/burst_mle_analysis/wizard.py` — drag-drop; confirmed a `QMainWindow`
      (`MLELifetimeAnalysisWizard`), so it does fit this base.
- [x] ~~`tttr/ptu_alex_creator/wizard.py`~~ — **obsolete, not migrated**: the file no
      longer exists. The plugin was rebuilt on AutoForm (`gui/sections.py` +
      `gui/view_model.py`) and now has no `QMainWindow` of its own, so it leaves this
      backlog rather than being worked down it.

**Priority B — plain `QMainWindow` tools (adopt for geometry + MMFDB status + the
read-only-construction guarantee; no drop list to dedupe):**

- [ ] `tttr/trace_browser/gui/tool.py`
- [ ] `tttr/tttr_lut_tools/gui/tool.py`
- [ ] `fluorescence_decay/irf_estimator/gui/tool.py`
- [ ] `fluorescence_decay/lltf/lltf_gui.py`
- [ ] `modelling/hydropro/gui/tool.py` (`HydroProTool`; the old top-level
      `hydrogui.py` no longer defines a window)
- [ ] `core/project_browser/gui/tool.py`
- [ ] `core/lightpath_simulator/gui/tool.py`
- [ ] `core/help/gui/tool.py`

Written **after** the 2026-06-24 enumeration and therefore never on this list — each
forked a plain `QMainWindow` while the base already existed, which is the failure mode
a stale backlog produces (re-derived 2026-07-29 by the grep in *Notes* below; none of
them handles drops today, so all are priority B):

- [x] `burst/burst_fcs_correlator/gui/tool.py` (`BurstFcsTool`) — migrated 2026-08-08
- [x] `calculator/phasor_calculator/gui/tool.py` (`PhasorCalculatorTool`) — migrated 2026-08-08
- [x] `fcs/flc_2d/gui/tool.py` (`FlcTwoDTool`) — migrated 2026-08-08
- [x] `core/code_editor/window.py` (`CodeEditorWindow`) — migrated 2026-08-08
- [x] `tttr/tttr_lut_tools/gui/tool.py` (`TTRLutToolsWidget`) — migrated 2026-08-08
- [x] `core/lightpath_simulator/gui/tool.py` (`LightPathSimulatorWidget`) — migrated 2026-08-08
- [x] `modelling/hydropro/gui/tool.py` (`HydroProTool`) — migrated 2026-08-08
- [x] `fluorescence_decay/irf_estimator/gui/tool.py` (`IRFEstimatorTool`) — migrated 2026-08-08
- [x] `burst/burst_h2mm/gui/tool.py` (`H2mmTool`) — migrated 2026-08-08 (dropped redundant `MessagesMixin`; base provides it)
- [x] `burst/burst_mle_analysis/wizard.py` (`MLELifetimeAnalysisWizard`) — migrated 2026-08-08
- [x] `fluorescence_decay/lltf/lltf_gui.py` (`LLTFGUIWizard`) — migrated 2026-08-08
- [x] `modelling/fret/gui/pair_selection_wizard.py` (`FRETPairSelectionWindow`) — migrated 2026-08-08
- [x] `tttr/trace_browser/gui/tool.py` (`TraceBrowserTool`) — migrated 2026-08-08
- [x] `core/help/gui/tool.py` (`HelpWidget`) — migrated 2026-08-08
- [ ] `core/project_browser/gui/tool.py` (`ProjectBrowserTool`) — **complicated**: eagerly opens MMFDB on construction via `self.refresh()`; must defer refresh to satisfy the no-DB-on-init guard
- [ ] `chimol/app/molview_main_window.py` (`MolViewPluginWindow`) — last, and only once
      [PRD-57](prd-57.md) settles the renderer/controller split; this window is the
      subject of its own migration and should not be moved onto a second base mid-flight.

**Out of scope for this base (not `QMainWindow`):**

- `modelling/fret/gui/wizard.py`, `modelling/fret/gui/pair_selection_wizard.py` and
  any `QWizard`/`QWizardPage` tools — `ChisurfDockTool` is a `QMainWindow` base. A
  separate thin-wizard base (or just construction smoke tests + read-only init) covers
  them. The detector wizard (`DetectorWizardPage`) already has a construction smoke
  test.
- `cookiecutter-chisurf-plugin/...` template — update the template to subclass the
  base once the API is stable so new plugins start conformant.
- `core/acq/standalone.py` (`StandaloneMainWindow`) — the acquisition app's own
  top-level window when it is run standalone, not a plugin tool the host docks.
- `burst/burst_selection/gui/legacy/burst_selector.py` — the superseded copy of a tool
  whose live form is already on the base; it is deleted, not migrated.
- `misc/games/*` — demonstrations, gated behind the manifest `demo` flag.
- `tttr/tttr_header_edit/gui/tool.py` — its tool is a plain `QWidget` (`TagsEditor`),
  never a `QMainWindow`; it was listed in error.
- `core/mmfdb_admin/gui/tool.py` (`MMFDBWidget`) and `core/setup/gui/tool.py`
  (`UnifiedSettingsTool`) already subclass `NavigationPanelTool`, itself a
  `QMainWindow` base carrying the navigation-panel contract. Reconciling the two bases
  is its own decision, not a per-tool migration; both were listed in error.

# Notes / status (2026-06-24, re-derived 2026-07-29)

- The list of `QMainWindow` tools was enumerated via
  `grep -rln "class .*(QMainWindow)" chisurf/plugins`; the `[drag-drop]` tag means the
  file references `setAcceptDrops`/`pathsDropped`/`DropListWidget`/`dropEvent`.
- **Re-run both greps when working this PRD.** A backlog enumerated once goes stale in
  both directions: the 2026-07-29 re-derivation found one migrated tool missing from
  *Done* (`quenching_estimator`), one backlog entry whose file no longer exists
  (`ptu_alex_creator`), and six `QMainWindow` tools written since that had never been
  listed at all — a new tool forking the boilerplate is exactly what this tracker is
  for, and it cannot catch one it does not know about.
- The read-only-construction rule is already **enforced repo-wide** by
  `test/test_no_db_writes_in_widget_init.py` (no Qt needed), so migrations cannot
  regress it.
- Each migration is GUI and needs `QT_QPA_PLATFORM=offscreen` + Qt bindings to run its
  smoke test.

# Relationships
- The rollout backlog for [PRD-23](prd-23.md) Task 1 (thin dockable tools); each migration also advances Task 3 (smoke tests) and reinforces Task 4 (read-only construction).
- Touches the [plugin system](/architecture/plugin-system.md) and the [Plugins target](/specs/plugins.md); read-only-construction rule keeps tools from opening [MMFDB (current)](/architecture/mmfdb.md) connections on init.
