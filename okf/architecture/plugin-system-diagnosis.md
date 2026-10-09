---
type: Architecture Diagnosis
title: Plugin System Hardening — Verified Findings
description: Reproductions, runtime guarantees, verification scope and remaining plugin metadata debt.
resource: chisurf/core/plugin/
tags: [plugins, discovery, manifest, verification]
timestamp: '2026-10-03T00:00:00Z'
---

# Plugin system diagnosis and hardening

## Where to pick this up

1. Measure: Re-run `test/test_plugin_dependencies.py` to distinguish the recorded four dependency/namespace failures from current results; retain exact identities and coordinate declaration edits with active plugin/project owners.
2. Open: Reconcile hard and optional cross-plugin imports with source, then check resolver cycles; the recorded stale declarations are `ndxplorer.optional_requires['mmfdb_admin']`, `traj_energy.requires['traj_energy_calculator']`, and `tttr_time_windows.optional_requires['intensity_trace']`.
3. Open: Resolve ownership of `mmfdb_admin` declarations for `project_browser.list`, `project_browser.save`, and `project_browser.restore`; the sibling namespace must not be silently claimed or allowlisted.
4. Measure: Preserve the recorded external-viewer source-tree and optional-extension qualifications when interpreting integration results; the exact checkpoint and parent settings/identity follow-ups are retained below.

## Recorded history and follow-up details

The infrastructure fixes below have passing regression and integration checks. The whole plugin system is **not** declared clean: the dependency/namespace metadata guard still fails four tests in the shared checkout. Re-run `test/test_plugin_dependencies.py` and repair declarations with the owners of the active plugin ports/project-storage work; do not expand its allowlist. In particular:

1. Reconcile hard and optional cross-plugin edges with current source. The failing check reports new top-level imports into toolkit-free GUI models and lazy references missing from manifests. Check the resolver for cycles after changing an edge's classification; bulk declaration changes are not a safe substitute for analyzing imports.
2. Remove declarations that are no longer true: the current snapshot identifies `ndxplorer.optional_requires['mmfdb_admin']`, `traj_energy.requires['traj_energy_calculator']`, and `tttr_time_windows.optional_requires['intensity_trace']`.
3. Resolve RPC ownership of `mmfdb_admin`'s newly added `project_browser.list`, `project_browser.save`, and `project_browser.restore`. `project_browser` is a sibling plugin ID. These three names produce the fourth failing guard; the first three guard failures were already in the recorded baseline.
4. Existing Chimol source-tree and optional QuEsT skips are not new exemptions. The integration run resolves the real Chimol entrypoint; its static source check deliberately cannot inspect a sibling checkout. QuEsT needs its optional extension.

The existing settings, identity and plugin-manager follow-ups remain in [the parent concept](plugin-system.md). No plugin UIs were ported or accepted in this task, no preview gate/allowlist was widened, and no commits or pushes were made.

## Confirmed defects and fixes

| Boundary | Reproduction | Repair |
|---|---|---|
| Manifest loading | JSON arrays/scalars, unhashable IDs, invalid entrypoint/dependency/RPC containers, explicit null collections/flags, invalid Unicode/read failures could crash discovery or construct unusable metadata. | Validate consumed types and existing semantic rules before `from_dict`; return `None` with the source path in the diagnostic. Preserve direct `from_dict`'s key-permissiveness. Do not import jsonschema on the startup path. |
| Hidden search roots | Filtering absolute path parts rejected legitimate plugins beneath `~/.chisurf/plugins`. | Evaluate exclusions relative to each configured root. Hidden/template descendants remain excluded. |
| Conflicting IDs | Returned manifests and the registered dictionary selected different copies. | Keep the first ID in configured discovery order, warn with selected and ignored directories, and keep returned records/lookups/registration consistent. |
| Import identity | Distinct IDs at the same module path, legacy/manifest mixtures, unnamed packages, and descendants under a shadowed regular parent could advertise code Python would not import. | Both scanners use a shared `PackageResolver` with `PathFinder.find_spec`, without executing package loaders. It checks parent search locations, respects namespace merging and a regular package taking precedence over namespace portions, and suppresses shadowed metadata. |
| Repeated scans | Deleted legacy plugins remained in `_legacy_plugins`. | Build and replace fresh manifest/legacy snapshots together. |
| Installation caches | Python's FileFinder missed newly installed packages when directory mtime was unchanged. | Refresh import finders for fresh scans and public cache invalidation. This is **not** a reload of already imported modules. |
| Native-only discovery | An `entrypoints.emtk`-only tool was classified as CLI-only. | GUI capability includes `gui`, `emtk`, or `script`, preserving explicit CLI-only/menu/demo metadata. |
| GUI registration | Eager Qt resolution prevented native-only actions and could hide a valid native alternative. | Create actions without loading plugin code; select/resolve the active Qt/emtk factory only on trigger, retaining the injected loader. Keep preview/explicit-host selection rules. |
| GUI lifetime/error isolation | Registry-launched windows lacked strong ownership; failed show/cleanup could escape a callback. | Retain windows until Qt destruction, use delete-on-close, preserve a refused close, release on explicit destruction, and contain factory/show/cleanup errors. Native ControlHost instances carry the native-host marker. |
| Static export checks | Legitimate module `__getattr__` exports and literal module forwarding appeared unbound in the AST test. Native factories were not included in that guard. | Resolve the guarded/literal lazy forwarding in the import-free source check, including real forwarded bindings; reject missing exports. Include native entrypoints. Real import tests remain an independent check. |
| Test collection | The contract-test module prepended `/Users/tpeulen/dev` to `sys.path`, making the editable emtk installation an empty namespace package (`__file__` was `None`; `Texture` could not import). | Remove only that global path mutation and its unused import. A subprocess regression preloads the same production dependencies and proves contract collection leaves import paths unchanged. The previously failing combined test order now passes. |

New regression suites: `test/core/test_plugin_system_robustness.py` and `test/core/test_plugin_manifest_robustness.py` — **80 cases passed**. Fixture plugin and parent initializers raise if executed, so import-free discovery is non-vacuously tested. The nested collision tests cover regular-first, namespace-first and merged namespace parents in both scanners.

## Verification snapshot — October 3, 2026

| Run | Result |
|---|---|
| Affected core manifest/registry/metadata/entrypoint/CLI/preview tests | **577 passed, 1 existing skip** |
| Combined real imports, clients, menu/launcher, contracts, demo/maturity/UI-path checks | **350 passed, 1 optional-dependency skip** |
| Cross-plugin dependency and RPC-ownership guard | **282 passed, 4 failed** — unresolved metadata debt described above |
| New robustness tests | **80 passed** (included in the core run, not an extra total) |
| Ruff on new helper/new tests and modified entrypoint/manifest tests | **Passed** |
| Scoped `git diff --check` | **Passed** |
| Independent spec and code-quality review | **Approved** — separate spec then quality verdict; no blocking logic/security findings |

JUnit testcase records were parsed and checked against declared suite totals. The core and integration testcase sets do not overlap: together they report **927 passed, 2 existing skips**. A final single-process rerun of the same testcase union also returned **927 passed, 2 skipped in 37.11 s**; its XML was checked for exact union equality and absence of failures. Do not add the 80 robustness cases again.

The skips are `test_manifest_entrypoint_resolves[chimol:gui]` (the real target lives in the external Chimol source tree) and `test_plugin_entrypoints_import[quenching_estimator]` (optional QuEsT extension). No new skips or dependency allowlist entries were introduced to conceal failures.

### Real discovery and GUI smoke

A fresh process on the live checkout reported:

- **133** shipped, non-template manifest files; **133** load successfully.
- **133** registry manifests and **133** menu records; IDs/module paths are unique.
- Discovery added **no plugin submodules** to `sys.modules` and did not import `jsonschema`.
- Native-only IDs: `about`, `bid_to_analysis`, `menu_switch`, `tttr_header_edit`, `tttr_splitter`.
- The real `menu_switch` action opened `MenuSwitchApp` in a marked native ControlHost, rendered a readable offscreen window, and released registry ownership after close/destruction. The PNG was viewed, not merely generated.
- Observed medians on this loaded host: registry discovery **317.30 ms**, cold menu discovery **216.15 ms**, cached menu access **0.00079 ms**. These are snapshot observations, not a cross-machine performance guarantee.

Evidence was produced under `/Users/tpeulen/.hermes/cache/scratch/plugin-system/`: `core-final.xml`, `integration-final.xml`, `combined-final.xml`, `dependencies-final.xml`, `smoke_plugin_system.py`, `smoke-results.json`, and `native-menu-launch.png`. Scratch files may expire; the commands below reproduce the durable checks. The screenshot is launch/lifetime evidence, **not** acceptance of every control or every plugin port.

## Reproduce

From `/Users/tpeulen/dev/chisurf`:

```bash
export QT_QPA_PLATFORM=offscreen
export TMPDIR=/Users/tpeulen/.hermes/cache/scratch/plugin-system
export PYTHONPATH="modules/chimol:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:."
PY=/Users/tpeulen/mambaforge/envs/arm64/bin/python

"$PY" -m pytest \
  test/core/test_plugin_manifest.py \
  test/core/test_plugin_manifest_robustness.py \
  test/core/test_plugin_registry.py \
  test/core/test_plugin_system_robustness.py \
  test/core/test_plugin_metadata_reader.py \
  test/core/test_plugin_entrypoint_resolution.py \
  test/core/test_plugin_cli_registration.py \
  test/core/test_emtk_preview_gate.py -q --tb=short

"$PY" -m pytest \
  test/core/test_plugin_client.py \
  test/core/test_plugin_client_integration.py \
  test/core/test_plugin_menu_opens.py \
  test/plugins/test_plugin_contracts.py \
  test/plugins/test_plugin_menu_metadata.py \
  test/plugins/test_plugin_ui_paths_contract.py \
  test/plugins/test_plugin_demo_gating.py \
  test/plugins/test_plugin_maturity_metadata.py \
  test/plugins/test_plugin_menu_tabs.py \
  test/gui/test_toolbar_plugin_names.py \
  test/gui/test_plugin_launcher.py \
  test/plugins/test_all_plugins.py -q --tb=short

"$PY" -m pytest test/test_plugin_dependencies.py -q --tb=short

ruff check chisurf/core/plugin/discovery.py \
  test/core/test_plugin_system_robustness.py \
  test/core/test_plugin_manifest_robustness.py \
  test/core/test_plugin_entrypoint_resolution.py \
  test/core/test_plugin_manifest.py
```

## Phase 2 — installation and registration integrity (October 3, 2026)

This follow-on changes the installer, dependency resolver, registry CLI/service
seams and dispatcher routing-table transaction. It does not port plugin UIs or
edit active plugin manifests, RPC allowlists, IMP builds or project lifecycle code.

| Boundary | Reproduction | Repair |
|---|---|---|
| Installation failure | Copying part of a plugin could destroy the old tree or leave a discoverable partial new tree. An interrupt after the old-tree move could escape the restoration guard and delete its backup. | Copy into unique hidden same-filesystem staging, validate the staged manifest, then promote; guard both moves and restore after promotion failure or graceful interruption. If restoration fails, retain and report its backup path. |
| Install identity | Naming an importable package after a different manifest ID broke absolute entrypoints; flat ZIP names could depend on temporary extraction directories. | Preserve real package names and stable flat ZIP stems. For non-Python distribution wrappers, use one unambiguous declared entrypoint package, otherwise a valid manifest ID; reject ambiguous packages. |
| Install/uninstall authority | Mutable/stale plans, symlinks and path aliases could reach or remove the wrong tree. | Revalidate source, overwrite confirmation and direct user-root destination; reject source/destination overlap and symlinks. Uninstall only direct non-symlink user-plugin directories and explain that built-in plugins must be disabled. |
| ZIP portability | Full member checks missed prefix aliases and file/directory conflicts; source links bypassed the ZIP branch; directory mode bits could disguise a path the extractor treats as a file. | Check normalized file and directory identities together in both member orders, classify directories by actual extraction semantics, and reject source links before branching. Reviewer-driven case/Unicode/order regressions and parent mode-bit regression were verified RED then GREEN; ordinary explicit directory entries remain supported. |
| Cycle diagnostics/order | Acyclic dependants of a cycle were labeled cyclic and could be emitted ahead of their prerequisites. | Identify real SCCs with iterative traversal, condense the graph and preserve deterministic prerequisite-before-dependant ordering. Keep first dependency declaration for duplicate IDs and retain all records during sorting. Diagnostics list SCC members without inventing a directed path through sorted members. |
| CLI naming/ownership | Click object's implementation name overrode the manifest alias; later commands silently replaced existing owners. | Manifest alias/kebab-case ID controls the public command. First owner wins, collision losers are not loaded, errors leave healthy siblings available. |
| Partial RPC registration | A registrar could add handlers and then fail, or replace a core/sibling route. | Thread-local staged routes and locked all-or-nothing commit. Recheck concurrent collisions, poison caught collisions, preserve read-your-writes and committed-only visibility across threads. Legacy duck dispatchers and explicit direct/core replacement remain supported. Only routing is transactional. |

### Phase 2 verification

| Run | Verified result |
|---|---|
| Expanded plugin/core/import/client/menu/launcher/native-manager/schema union | **1267 passed, 2 existing skips** in 72.91 s; owned source/test hashes unchanged during and after run |
| Focused installer/dependency/CLI/RPC/registry/Qt-widget union | **190 passed** in 6.17 s |
| New phase-2 robustness suites | **72 passed**: installation 47, dependency 9, registration 16; included in both unions, not extra totals |
| Dependency/RPC declaration guard | **282 passed, 4 failed**; exact failing testcase identities match the pre-change baseline |
| Additional dispatcher/protocol/RPC/app/client/transport/session/startup selection | **189 passed, 2 skipped, 2 failed**; startup timing failures also reproduce using isolated unchanged HEAD helper/test copies with the existing project harness |
| Scoped Ruff, whitespace checks and added-line security scan | **Passed**; no secret/shell/eval/pickle/SQL-injection-pattern matches in scoped additions |
| Independent final spec/quality re-review | **Passed** after two bounded fix cycles. A later shared registry-file mtime triggered an additional passing scoped confirmation of its CLI/services methods. Actual-source in-memory probes supplemented parent filesystem/runtime tests; no full-repository acceptance claim |

The new server-run failures are
`test_terminate_and_collect_stderr_does_not_block_live_process` (child has not
emitted stderr within the test's 0.2 s sleep) and
`test_terminate_and_collect_stderr_is_bounded` (child does not finish within its
1 s wait). Both `chisurf/server/startup.py` and `test/server/test_startup.py` are
byte-identical to HEAD. Both failures reproduce when their HEAD copies run with
`-p test.conftest`; this is a pre-existing interpreter-startup/harness timing
problem, not evidence that the modified routing dispatcher broke startup. Those
helpers/tests were not changed or masked. The two additional server skips have
no available fit parameters; they are not new exemptions.

JUnit records were parsed, declared counts matched and duplicate testcase
identities checked. The focused and expanded runs overlap; **do not sum them**.
The expanded union's skips remain the external Chimol source check and optional
QuEsT import noted in Phase 1. The metadata guard's four failing identities are:

- `test_every_hard_edge_is_declared_in_requires`
- `test_every_optional_edge_is_declared_in_optional_requires`
- `test_no_stale_declarations`
- `test_no_plugin_declares_rpc_methods_in_another_plugins_namespace`

The remaining RPC declaration failure still names
`mmfdb_admin:project_browser.list`, `.restore` and `.save`. No allowlist or active
plugin manifest was edited to manufacture a green result.

### Phase 2 real execution and limits

A fresh isolated distribution ZIP install inferred `integrity_smoke` from its
entrypoints while preserving the different ID `public_smoke_id`. Both real
registry/menu scans discovered it without importing it; the actual installed
Click command executed under its manifest alias with exit 0, and its actual
registered RPC returned the requested message. Uninstall and both rescans removed
the metadata. All filesystem changes were in scratch, not the real user plugins.

The real checkout again produced **133 valid manifests**, **133 registry
manifests**, **133 menu records**, no plugin-module imports or `jsonschema` during
discovery. The native Menu Switch rendered a readable window and released registry
ownership after close/destruction; its PNG was viewed. This is launch/lifetime
verification, not full control parity or acceptance of a plugin UI migration.

Evidence is under `/Users/tpeulen/.hermes/cache/scratch/plugin-system/phase2/`:
`combined-closeout.xml`, `focused-last.xml`, `dependencies-reverified.xml`,
`server-reverified.xml`, `startup-head-project.xml`, `verification-summary.json`,
`closeout-receipt.json`, `reverify2-result.json`,
`registry-scope-confirmation-result.json`,
`smoke_installed_plugin.py`, `installed-smoke-results.json`, `smoke-results.json`,
`native-menu-launch.png`, and review task/result artifacts. Scratch may expire.
Reproduce the focused boundary checks with the environment in the command section
above and:

```bash
"$PY" -m pytest \
  test/core/test_plugin_install_robustness.py \
  test/core/test_plugin_dependency_robustness.py \
  test/core/test_plugin_registration_robustness.py \
  test/core/test_plugin_registry.py \
  test/core/test_plugin_cli_registration.py \
  chisurf/plugins/core/plugin_manager/test/test_widgets.py -q --tb=short

"$PY" -m pytest chisurf/plugins/core/plugin_manager/test \
  test/test_manifest_schemas.py test/server/test_rpc_method_names.py -q --tb=short

"$PY" -m pytest test/test_plugin_dependencies.py -q --tb=short
```

This repair provides neither hot reload nor a security sandbox for arbitrary
plugin code, crash durability, hostile concurrent-filesystem protection or
full-repository acceptance. RPC rollback is limited to routing-table registration,
not side effects a registrar performs elsewhere. The temporary IMP.bff generated
wrapper/native mismatch encountered mid-run recovered before these passing runs;
this task did not modify or rebuild IMP.

## Compatibility limits

- This work keeps dependency ordering, legacy fallback, demo/maturity metadata, explicit host modes and the native preview gate.
- Import identity is computed from standard filesystem package search locations without executing `__init__.py`; discovery does not evaluate arbitrary runtime mutations of package `__path__`.
- Cache invalidation does not remove entries from `sys.modules`, migrate plugin state or hot-reload live windows. Restart after replacing already imported plugin code.
- Lightweight startup validation checks consumed field shapes and existing semantic rules. It is not a substitute for validating every RPC payload against its full declared schema.
- No blanket full-repository test pass, scientific output parity, GUI port acceptance, or security sandbox claim is made.
