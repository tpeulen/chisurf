---
type: PRD
prd: "23"
title: "PRD-23: Thin Widgets / View–API Separation"
description: Makes GUI widgets pure view — no data processing, no database or acquisition-library calls, no side effects on construction — with mandatory construction smoke tests and a shared dockable-tool base.
status: in-progress
phase: "cross-cutting"
resource: chisurf/gui/widgets/tools/
tags: [prd, gui]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
PRD-23 makes GUI widgets pure view: they call only the api/RPC client, hold no database or photon-library logic, and perform no side effects (especially no database writes) on construction. It mandates a construction smoke test per tool to catch missing-import and side-effect-on-init regressions, and introduces a shared dockable-tool base implementing Load/Save, drag-drop, dock management, and connectivity-aware MMFDB behaviour once instead of per plugin. This removes the class of bugs where logic hidden inside a widget ships broken, and enforces the GUI half of the transformer contract.

# Status
In-progress (cross-cutting, STATUS TABLE authoritative). **Task 1 is complete**: every tool window in `chisurf/` now subclasses `ChisurfDockTool`, enforced by `test/test_tool_window_base.py` against a shrinking allowlist of the five windows that are not tools. Residual-logic extraction and the static guard against database writes in widget `__init__` have landed for the reference transformers; Tasks 2 and 3 remain open for the rest of the tools.

# Goal
GUI widgets become pure **view**: no data processing, no DB/`tttrlib` calls, no side effects on construction. All state and I/O live behind the api/RPC layer. Mandatory construction smoke tests and a shared dockable-tool base remove the class of bugs where logic hidden in widgets ships broken.

# Evidence (why)
- A missing `QComboBox` import crashed `DetectorWizardPage` at construction — never caught because the widget-build path had no test.
- The FCS dialog wrote to MMFDB **on construction** (migrating/registering as a side effect), causing the "auth required" / write-on-open issues.
- Each tool re-implements Load/Save, drag-drop, docks differently (shifter vs others), so fixes don't propagate.

# Design
- **View-only widgets.** Widgets call the api/RPC client only; no `tttrlib`, no `MFDatabase`, no registration logic in `gui/`. Construction is read-only and cannot perform DB writes (the [PRD-16](prd-16.md) split, enforced).
- **Mandatory construction smoke test** per tool (mirror `test/gui/test_detector_wizard_page.py`): build the widget offscreen, assert it constructs — catches missing-import / side-effect-on-init regressions.
- **Shared dockable-tool base** (`ChisurfDockTool` or similar): standard Load/Save tool-menu, drag-drop target, dock management, MMFDB-connection status, and the "From MMFDB / Save to MMFDB vs file" connectivity-aware behaviour — implemented once, reused by every transformer tool.
- Lean on the existing MVC controller work (MVC complete) so state lives in the model/controller, not the widget.

# Tasks
1. Define `ChisurfDockTool` base (tool-menu, docks, drag-drop, MMFDB status, connectivity-aware load/save) and migrate the Microtime Shifter + FCS dialog + detector wizard onto it.
2. Move any residual `tttrlib`/DB logic out of `gui/` into `api/` + RPC.
3. Add construction smoke tests for every tool; make it a checklist item for new transformers (PRD-16 conformance).
4. Forbid DB writes during widget `__init__` (read-only construction); migration/registration only on explicit user action.

# Definition of Done
- [ ] Widgets are view-only (no DB/`tttrlib`); construction is read-only.
- [x] A shared dockable-tool base is used by the transformer tools; Load/Save/docks are not re-implemented per plugin. *(Done 2026-08-10: every tool window in `chisurf/` is a `ChisurfDockTool`; `test/test_tool_window_base.py` fails on a new `QMainWindow` subclass.)*
- [x] Every tool has a construction smoke test; new transformers must add one. *(Done 2026-08-10: `test/gui/test_every_tool_constructs.py` discovers all 114 tools from the manifests and builds each in its own process, so a new plugin is covered the moment it declares `entrypoints.gui`.)*

# Definition of Clean
Layer purity (view ↔ api/RPC); no side effects on construction; GUI smoke tests mandatory; reuse the base, don't fork.

# Implementation status

**Task 2 (move residual DB logic out of `gui/`) — landed for both reference transformers (the non-GUI half).**

- **Burst Selection.** The raw-input registration/lookup logic that lived in `gui/tool.py` (importing `register_result`/`MFDatabase`/`resolve_database_path` into the view) moved to `api/mmfdb.py`: `file_md5`, `sample_id_for_raw_path`, `raw_artifact_id_for_path`, `raw_file_data_format`, `register_raw_input_for_sample`, and a new `acquire_mmfdb_connection()` (global-or-default connection acquisition). `gui/tool.py` now imports these from `..api.mmfdb` (re-exported under the old private names for callers/tests) and its `_db()` is a one-liner over `acquire_mmfdb_connection()`. The view no longer imports `MFDatabase`/`register_result`/`resolve_database_path`.
- **Microtime Shifter.** `api/mmfdb.py` gained `active_mmfdb_connection()`; the GUI `_db()` and the `MicrotimeShiftMMFDBPipeline` default both use it, so the view no longer imports `_get_global_db` directly.
- **Import side-effects (overlaps Task 4).** Both plugin `__init__.py` files no longer import the Qt GUI tool eagerly — `BurstSelectionTool`/`MicrotimeShifterTool` resolve lazily via module `__getattr__` (PEP 562). The `api`/`cli` layers are now importable **headlessly** (no Qt binding required), which the new `tests/test_api_mmfdb.py` exercises (and which previously made the api/cli tests uncollectable when Qt was absent).

**Task 1 (shared dockable-tool base) — landed.** `chisurf/gui/widgets/tools/` provides `ChisurfDockTool(QMainWindow)` and `PathDropListWidget`. The base factors the boilerplate both transformer tools had copied: window-level path drag-drop (dispatched to an overridable `on_paths_dropped` hook → `_add_paths` by convention), the byte-identical drop-list widget, window-geometry persistence helpers, and lazy MMFDB-connectivity accessors (`acquire_mmfdb_connection` hook, `mmfdb_connection`, `mmfdb_connected`) that do **no** work on construction. Burst Selection and Microtime Shifter now subclass it: each deleted its private `DropListWidget` (now `PathDropListWidget`) and its duplicated window `dragEnterEvent`/`dropEvent`, and routes connection acquisition through the `acquire_mmfdb_connection` hook.

**Task 3 (construction smoke tests) — landed for both reference transformers.** `test/gui/test_chisurf_dock_tool.py` covers the base (read-only construction, drop dispatch, MMFDB hooks, geometry). Each tool has an offscreen construction smoke test that builds the real widget (not `__new__`) and asserts it constructs, reuses `ChisurfDockTool`, and opens no MMFDB connection on init: `burst_selection/tests/test_construction_smoke.py` (new) and the existing `tttr_microtime_shifter/tests/test_gui.py` (augmented).

**Task 4 (read-only construction) — enforced repo-wide.** Beyond the two tools (whose smoke tests assert `_mmfdb_db is None` after construction), the rule is now an automated static guard: `test/test_no_db_writes_in_widget_init.py` AST-parses every GUI module and fails if any class `__init__` *directly* calls an MMFDB write/open entrypoint (`register_*`, `MFDatabase(...)`, `save_setup`/`add_*`, `set_object_sample_id`, `reconcile_schema`, …); calls inside nested callbacks defined in `__init__` are deferred and not flagged (meta-tested both ways). The guard is AST-only (no Qt — runs in any CI). The one pre-existing violation it surfaced — `lightpath_simulator/gui/easy_mode.py` opening `MFDatabase` in a dye-table widget's `__init__` (which can trigger schema-reconcile writes) — was fixed by deferring the adapter open to first tooltip render (`_ensure_db_adapter`). The allowlist is empty.

**Third tool migrated — TTTR Time-Window (`tttr_time_windows`).** It had the same copied `DropListWidget` + window drag-drop, but its list filtered by supported TTTR extension. Rather than fork, `PathDropListWidget` gained an optional `path_filter` predicate (None = accept all, preserving the burst/shifter behavior; a predicate restricts drag-accept and drop), so the tool now reuses the shared widget (`PathDropListWidget(..., path_filter=_is_supported_path)`), subclasses `ChisurfDockTool`, drops its window `dragEnter`/`dropEvent`, and lazy-loads its GUI in `__init__.py`. Covered by `tttr_time_windows/tests/test_construction_smoke.py` and an added base test for the filter variant. This proves the base generalises beyond the two reference transformers, including the extension-filtered drop case.

**Task 1 finished (2026-08-10): every tool window is on the base, and a guard keeps it that way.** The "migrate opportunistically" phase is over — opportunism is what left the list half-done and unmeasured. Counting direct `QMainWindow` subclasses across `chisurf/` by AST: **11 → 5**, and the five that remain are not tools (the application's own `Main` window, `ChisurfDockTool` itself, and the three games). Migrated in this pass:

- **`NavigationPanelTool`** (`chisurf/gui/widgets/navigation.py`) — the highest-leverage one, because it is the shell every navigation-style plugin tool is built on. It was `HelpGuideMixin + QMainWindow`, i.e. a second, parallel kind of tool window; it is now a `ChisurfDockTool` that lays its content out as navigation-plus-panels, so every shell inherits the shared error/warning reporting, path drag-drop and lazy store access.
- **`ProjectBrowserTool`**, **`MaxentDecayWidget`**, **`MolViewPluginWindow`** (chimol), **`StandaloneMainWindow`** (SM Acquisition), and the legacy **`BurstSelectionTool`**.

Two things fell out of the migration:

- `ProjectBrowserTool.__init__` called `self.refresh()`, opening the project store **while constructing** — the exact shape of the FCS bug, and invisible to the write-only static guard because it is a read. The load moved to `showEvent`; the smoke test asserts both halves (nothing on construction, populated on show), because deferring a load is also how you silently lose it.
- `chisurf/plugins/core/acq/standalone.py` imports Qt inside a `try` so CLI-only mode works without it. The base import had to go in the same guarded block with an `object` fallback, or importing the module headlessly would raise.

**The guard.** `test/test_tool_window_base.py` is an AST check (no Qt, no display) that fails on any new direct `QMainWindow` subclass, against a **shrinking** allowlist of the five non-tools — plus a second test that fails when an allowlist entry goes stale, so the list cannot quietly grow a hiding place. Smoke tests for the migrated windows: `test/gui/test_migrated_tool_windows.py`.

**Task 3 finished (2026-08-10): one discovery-driven test replaces 114 hand-written ones.** `test/gui/test_every_tool_constructs.py` reads every plugin manifest, and builds each tool that declares `entrypoints.gui` **in its own subprocess** — which is not fastidiousness: a tool that blocks would wedge the session and one that segfaults would take the suite with it, and both kinds exist. Marked `slow` (process startup × 114 ≈ 13 min), so it is run deliberately with `--run-slow`.

Measured on the first full run: **111 of 114 construct, 1 blocks, 2 segfault**, and **none** opens a metadata-store connection while constructing — so Task 4's rule holds everywhere the guard can see. The three exceptions are tracked in the test's shrinking `BLOCKING`/`CRASHING` sets, which fail if a listed tool starts working, and written up in [known issues](../references/known-issues.md):

- `mmfdb_admin` fires four blocking RPCs from `__init__` (`mmfdb.status` ×2, `mmfdb.users.list`, `mmfdb.security.auth.login`), so with no server it freezes ~20 s. Not fixed here on purpose: `_verify_admin_access` is a permission gate, and where it should fire when there is no server is a design decision, not a mechanical deferral.
- `psf_calculator` and `lightpath_simulator` segfault while constructing; both start background work in `__init__`.
- Fixed in passing: `acq` crashed outright, because it keyed "are we inside chisurf?" on `import chisurf` succeeding — which it always does — rather than on `chisurf.cs` existing.

**One bug the guard found in the infrastructure, not in a tool.** `chisurf/core/settings/env_bootstrap.py` prepended the environment's `lib` to `DYLD_LIBRARY_PATH` on macOS. dyld reads that once at process start, so it did nothing for the process that set it and silently overrode library resolution for every **child** — where Qt's font engine then bus-errors on the first `create_text_icon`. It presented as "one tool crashes, but only when the parent is pytest". Only the harmless `DYLD_FALLBACK_LIBRARY_PATH` remains; `test/test_env_bootstrap_dyld.py` guards both halves, and `test/fio` + `test/core` still pass 1629 tests with zero loader errors.

**Still to do:** Task 2 for the tools beyond the reference transformers (residual `tttrlib`/DB logic in `gui/`), the three tracked construction defects, and the detector wizard — a `QWizardPage`, not a `QMainWindow`, so it does not fit this base and needs its own answer.

# Relationships
- Enforces the GUI half of [PRD-16](prd-16.md) (transformer contract); adds construction smoke tests as a conformance checklist item.
- Generalizes fixes made to the reference-transformer tools.
- Leans on the completed MVC controller separation so state lives in the model/controller.
- Targets the [Plugins target](/specs/plugins.md); widgets talk only through the [RPC target](/specs/rpc.md).
