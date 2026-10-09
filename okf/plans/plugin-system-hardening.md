# Plugin System Hardening Implementation Plan

> **For Hermes:** Use subagent-driven-development for independent implementation/review tasks; preserve the shared working tree and do not commit or push.

**Goal:** Make plugin discovery deterministic and safe against invalid user metadata, and make emtk-only tools reachable without importing their Qt alternatives.

**Architecture:** Keep the manifest/AST discovery architecture and existing dependency ordering. Validate metadata before dataclass construction without importing jsonschema on the startup path (measured cold import/validation ~1.0 s). Discovery builds a fresh snapshot; first search-path occurrence wins for conflicting IDs/module names and warnings name both sources. Do not alter the emtk acceptance gate or ongoing plugin ports.

**Tech Stack:** Python 3.12, pathlib/AST/importlib, pytest, qtpy/PyQt5 and emtk; tests run in the arm64 environment.

## Baseline diagnosis (2026-10-03)

- `load_manifest` calls `from_dict` without validation. JSON lists, list-valued entrypoints/requires and unhashable IDs raise during discovery; RPC null can be silently discarded.
- `PluginRegistry.discover` checks absolute path parts, so every plugin beneath `~/.chisurf/plugins` is skipped. Restrict filtering to paths relative to each search root.
- Duplicate IDs produce two returned manifests and only the last registered manifest. Use first search-path occurrence consistently and warn.
- `_legacy_plugins` is appended on every rescan. Replace it with a fresh snapshot just like `_manifests`.
- `_read_manifest_metadata` ignores `entrypoints.emtk` when determining CLI-only status.
- `invalidate_plugin_cache` does not invalidate Python's import finders after plugin installation.
- Baseline command: `QT_QPA_PLATFORM=offscreen PYTHONPATH="modules/chimol:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." /Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest test/core/test_plugin_registry.py test/core/test_plugin_manifest.py test/core/test_plugin_metadata_reader.py test/core/test_plugin_entrypoint_resolution.py test/core/test_plugin_cli_registration.py test/core/test_emtk_preview_gate.py test/test_plugin_dependencies.py -q` -> 650 passed, 9 failed, 1 skipped. Six are static GUI-export checks, three dependency-declaration checks. Investigate rather than weakening tests or touching active port manifests indiscriminately.

## Task 1: Reject malformed manifests without aborting discovery

**Files:** Modify `chisurf/core/plugin/manifest.py`; create `test/core/test_plugin_manifest_robustness.py`.

1. Write one parameterized regression for JSON scalars/arrays, invalid IDs, malformed entrypoints/dependency maps/RPC lists, Unicode and read failures. Assert `load_manifest` returns None with a diagnostic containing the source path; a healthy sibling remains discoverable.
2. Run the tests and capture expected red output before implementation.
3. Extend existing lightweight validation to reject invalid consumed field shapes and nested entrypoints/RPC objects; validate before `from_dict`. Catch file/Unicode/parse failures at the file boundary. Preserve from_dict's documented permissive key behavior for direct callers. Avoid jsonschema imports during discovery. Do not enforce a new ID naming convention or normalize supplied values.
4. Run new tests plus existing manifest/schema tests; verify full to_dict/load roundtrips and shipped manifests. Record red/green results.

## Task 2: Fresh, deterministic registry discovery

**Files:** Modify `chisurf/core/plugin/registry.py`; create `test/core/test_plugin_system_robustness.py`.

1. Add a regression for a legitimate plugin underneath a hidden search root; run red, then filter relative path components and run green.
2. Add a duplicate-ID regression proving returned manifests, get_manifest and all_manifests agree; run red, then implement first-path-wins with a warning containing both directories; run green.
3. Add repeated/rescanned legacy snapshot regression, including removal; run red, then build/assign fresh legacy state; run green.
4. Keep dependency ordering and existing emtk selection/build additions unchanged; run registry and dependency resolver unit tests.

## Task 3: emtk-only metadata and installed-module cache refresh

**Files:** Modify `chisurf/plugins/__init__.py`; extend `test/core/test_plugin_system_robustness.py`.

1. Add emtk-only discovery regression, run red, include emtk in GUI capability detection, run green.
2. Add real-import regression: prime a FileFinder cache, install a new module while preserving directory mtime, invalidate plugin cache, then import the new module. Run red; call importlib.invalidate_caches in the public invalidation function; run green. This is cache refresh, not hot reload of existing sys.modules.
3. Add duplicate-ID/module-path discovery regressions across roots, run red, and apply the same first-path-wins policy as registry. Sort/prune directory traversal for stable source order and exclude hidden/template paths relative to roots. Preserve demo/maturity gates and legacy metadata support.

## Task 4: GUI registration audit and confirmed fixes

**Files:** `chisurf/core/plugin/registry.py`, dedicated new regression tests if the read-only audit confirms a defect.

1. Audit register_gui and launch lifetime. If confirmed, test menu registration without loading plugin code, native-only inclusion, error isolation and window retention through close using the real Qt host.
2. Record each failing test before minimal implementation. Keep explicit Qt/emtk mode and preview gates intact.
3. Any GUI-path change requires an offscreen screenshot viewed by the agent and real trigger/close tests. Do not port plugin UIs in this task.

## Task 5: Verification and durable report

**Files:** Update `docs/development/plugin_architecture.md`, `okf/architecture/plugin-system.md`, own `okf/log.md` bullet, board claim. Create `okf/architecture/plugin-system-diagnosis.md` for measurements/results and unresolved findings.

1. Run focused new tests, core plugin/client/dependency/schema tests, metadata/demo/maturity contract checks and selected real Qt/emtk launcher smoke tests. Compare full baseline failures with initial evidence; classify real defects versus stale static checks. Do not hide failures behind skips/allowlists.
2. Re-run real plugin discovery, count manifests/menu records programmatically, check duplicate identities and import-free behavior, and measure warm discovery/validation cost.
3. Review changes independently for spec compliance then code quality. Run ruff on new tests and diff whitespace checks.
4. Record exact commands, results and actionable limits in OKF. Update the board when verified complete. Leave changes uncommitted because files already contain other agents' edits.

## Verified completion — 2026-10-03

Tasks 1–5 are complete within the documented infrastructure scope. Read
`okf/architecture/plugin-system-diagnosis.md` for the exact test commands, results
and remaining declaration/RPC-ownership work. Final core/integration: 927 passed,
2 existing skips, including 80 new robustness cases. Real discovery/load/menu
snapshots each contain 133 manifests; no plugin code or jsonschema was imported.
Real native menu action, readable render and close/destruction were exercised.
Independent spec then code-quality review approved with no blocking findings.

Review-driven collision fixes also cover earlier legacy/unnamed packages and
regular-parent shadowing, using a shared import-free PathFinder resolver while
preserving merged namespace packages. Combined integration failures were traced
to contract-test sys.path pollution and fixed with a subprocess regression.
The metadata guard still reports 282 passed/4 failed; no active plugin manifests,
preview gates, RPC allowlists or unrelated ports were modified. Changes remain
uncommitted in the shared working tree.

## Reference decisions

Python importlib docs require invalidating finder caches after runtime installation. PyPA object-reference semantics support `module:object.attr`; audit existing loader against this before expanding scope. These are reference API facts, not reasons to rewrite discovery around installed distributions.
