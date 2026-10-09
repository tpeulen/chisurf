---
type: Plan
title: Plugin installation and registration integrity — Implementation Plan
description: Plan for transactional plugin installation, dependency-cycle diagnostics,
  CLI ownership, and atomic RPC registration while preserving concurrent work.
---

# Plugin installation and registration integrity — Implementation Plan

**Goal:** Remove confirmed data-loss/import-identity/registration flaws while preserving concurrent plugin-port and project-lifecycle work.
**Architecture:** Preserve metadata-only discovery. Stage plugin trees outside the discoverable set, validate the exact staged tree, and promote only after successful copying. Keep package names distinct from manifest IDs. Resolve dependency cycles as actual strongly connected components, not all blocked dependants. Preserve explicit CLI aliases and prevent silent command replacement.
**Tech stack:** Python 3.12, pathlib/shutil/zipfile, packaging, Click, pytest; arm64 environment, Qt offscreen.

## Scope and coordination
No commits, staging, resets, stashes, GUI ports or preview-gate changes. Active structure_tools/FRET/FPS and project-storage owners retain their files. Four dependency audit failures reproduced before edits (282 passed); publish exact owned-file debt rather than invent bounds or widen allowlists.

## Task 1 — Transactional plugin installation (parent)
Modify `chisurf/plugins/core/plugin_manager/api/install.py`; create `test/core/test_plugin_install_robustness.py`.
1. RED: inject a copy failure after a partial tree exists; old destination must remain byte-identical; fresh failed install must leave no discoverable tree; never remove an unrelated `.replacing` directory.
2. GREEN: stage within a hidden unique directory on the destination filesystem before any rename; isolated backup in that staging directory; restore on promotion failure or a graceful interrupt after the old-tree move, preserve a failed-restoration backup and cleanup on success/failure.
3. RED/GREEN: package folder differs from manifest ID; preserve importable source package path and prove real entrypoint resolution after install. Top-level ZIP naming must be stable, never a TemporaryDirectory basename; reject ambiguous multi-package archives. Support non-Python distribution wrappers using unambiguous entrypoint package identity, otherwise a valid manifest ID, without renaming already importable packages.
4. RED/GREEN: forged/stale plans, changed manifest, invalid UTF8, traversal/symlink destinations, archive Windows path aliases. Validate staged source and writable-root containment before mutating installed trees. Reject source/destination overlap and symlink escapes.
5. Exercise folder/ZIP install, metadata refresh and uninstall in an isolated user root. No installed user data is touched.

## Task 2 — Accurate cycle diagnostics and degraded load ordering (isolated implementer)
Modify `chisurf/core/plugin/dependencies.py`; create `test/core/test_plugin_dependency_robustness.py`.
1. RED: two cyclic plugins with lexically earlier acyclic dependants; report only the actual SCC and put dependants after their prerequisites.
2. GREEN: condense SCCs and topologically order components with deterministic ties. Cover separate cycles, self cycle, diamond chains, disconnected nodes and long graphs without recursion failure. Diagnostics list component members rather than inventing an arrow path that may contain nonexistent edges.
3. RED/GREEN: duplicates select first declaration consistently with discovery and never corrupt sorting. Do not introduce dependency bounds or edit plugin manifests.

## Task 3 — Consistent CLI registration (parent)
Modify only `PluginRegistry.register_cli` in `chisurf/core/plugin/registry.py`; create `test/core/test_plugin_registration_robustness.py`.
1. RED: `alias=module:command` must register under alias even when Click object has another name. Bare entrypoint defaults to kebab-case plugin ID.
2. GREEN: honor explicit alias; reject collisions without replacing existing commands; contain failures and retain healthy sibling registration. Repeat registration must not override central commands.
3. Run Click CliRunner calls, not only dictionary checks.

## Task 3b — Atomic service-registration boundary (parent)
Modify `chisurf/server/dispatcher.py` and the `register_services` section of `chisurf/core/plugin/registry.py`; extend `test/core/test_plugin_registration_robustness.py`.
1. RED: a registrar adds one RPC then raises; the partial handler must never remain reachable, healthy siblings must register, and pre-existing core methods must remain unchanged.
2. RED/GREEN: a plugin cannot silently replace an existing core/sibling RPC; rollback the whole registrar's method set on collision.
3. Implement an explicit `registration_transaction(owner)` context on the dispatcher: thread-local staged methods, locked all-or-nothing table commit, collision recheck at commit. Preserve intentional direct/core `register` behavior outside transactions, and legacy duck-typed dispatchers without this optional API.
4. Test same-thread visibility, cross-thread invisibility until commit, concurrent collision recheck, nested transaction rejection and cleanup. The transaction protects routing only, not arbitrary side effects in plugin code.

## Task 4 — Independent review and layered verification
Run focused suites immediately after each write. Run original combined plugin union, new robustness, installer UI-model/native plugin-manager tests, dependency/RPC guard and schema checks. Parse JUnit exact totals, compare baseline failures, run scoped Ruff/diff checks. Re-run real import-free discovery/native Menu Switch smoke and inspect PNG. Independent reviewer inspects actual changed files including untracked tests; fix blocking findings and rerun. Update diagnosis/architecture/board with verified results and exact remaining owned-file debt.

## Commands
From `/Users/tpeulen/dev/chisurf`, set:
`TMPDIR=/Users/tpeulen/.hermes/cache/scratch/plugin-system/phase2 QT_QPA_PLATFORM=offscreen PYTHONPATH=modules/chimol:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:.`
Run `/Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest <named suites> -q --tb=short`, storing JUnit under phase2 scratch. Run `ruff check <scoped changed Python files>` and `git diff --check -- <scoped tracked files>`.

## Verified closeout

Implementation and independent two-stage review are complete. The final 29-file affected union passed **1267 tests with 2 existing skips**; the focused installer/dependency/registration/registry/CLI/widget union passed **190 tests**. The **72 phase-2 robustness cases** are contained in those runs, not additional totals. Exact JUnit records, declared totals and unique testcase identities were checked. Scoped Ruff/whitespace/security scans passed. Owned source/test hashes were stable across the final integrated run and closeout.

Both real smokes passed on current source: scratch ZIP install -> metadata-only registry/menu discovery -> actual imported Click command and RPC -> uninstall/rescan; and 133-record checkout discovery -> native Menu Switch launch/render -> close/destruction ownership release, with PNG inspected. No real installed user plugin data was modified.

Review blockers were repaired rather than waived. The final spec/quality verdict passed; a subsequent shared registry-file mtime triggered a fresh passing confirmation of the current CLI/service methods. Source/test bounds, prefix file/directory identity checks, extraction-mode consistency, interrupt rollback and truthful SCC diagnostics are covered by RED -> GREEN cases.

Remaining baseline debt is explicit: **282 passed / 4 failed** dependency/RPC declaration guard tests, and the extra server selection's **189 passed / 2 skipped / 2 startup-timing failures**. The two unchanged HEAD startup/test copies reproduced the same failing function names under the project harness. Active manifests, allowlists, startup/project lifecycle and plugin ports were not changed to conceal these failures. No commits, staging or pushes by this task.

Detailed evidence and limits: `okf/architecture/plugin-system-diagnosis.md`; scratch `phase2/closeout-receipt.json`, `combined-closeout.xml`, `focused-last.xml`, `dependencies-reverified.xml`, independent verdict JSONs and smoke results. RPC transactions protect routing only; no hot reload, plugin sandbox, crash durability, full GUI parity or full-repository acceptance claim.

