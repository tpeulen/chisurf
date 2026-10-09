# Production plugin CLI consistency — Implementation Plan

**Status:** Complete within scoped acceptance; parsing cleanup/hot-reload/alias-order limitations remain in the owning concept.

**Goal:** Give `csc` the same import identity and manifest authority as metadata-only registry discovery, while preserving actual command exit statuses and host context.
**Architecture:** Reuse `PackageResolver` and `load_manifest` in the lazy filesystem scanner, never import plugin packages at discovery time. Keep valid manifests authoritative even when they explicitly omit a CLI. Keep legacy AST fallback only when a manifest is absent/invalid. Forward real Click commands through their context/invocation API; preserve argparse/plain callable compatibility.
**Tech stack:** Python, importlib PathFinder, Click, pytest; existing arm64 interpreter and source dependencies.

## Ownership and baseline
- Claim only `chisurf/core/cli/__init__.py`, new `test/core/test_plugin_cli_robustness.py`, this plan, new `docs/development/plugin_cli_contract.md`, new `okf/architecture/plugin-cli.md`, own board/log hunks. No plugin manifests, GUI ports, project lifecycle, preview gates, staging/commits/pushes.
- Current baseline metadata reader + production CLI declarations + registry registration robustness: 93 passed.
- Existing phase-2 installer/review work is complete; do not reopen superseded findings. Other dirty paths belong to concurrent owners.

## Task 1 — Python import identity (RED → GREEN)
1. Add fixture built-in/user roots by monkeypatching CLI module `__file__` and `Path.home`; plugin and parent initializers raise on import.
2. RED: two different IDs under the same import path, and a user descendant beneath a built-in regular parent, must not advertise commands from the shadowed tree. Include unnamed/legacy first owners.
3. GREEN: invalidate finder caches and use `PackageResolver` before reading metadata. Retain only Python-importable package identities; diagnostics identify both selected and ignored paths.
4. Verify namespace-parent merging and later regular-parent precedence, hidden user roots, and cache refresh after new package installation.

## Task 2 — Manifest authority (RED → GREEN)
1. RED: duplicate manifest IDs select first discovery owner even when command aliases differ or the first manifest has no CLI.
2. RED: invalid version/type containers must not become commands from unchecked raw JSON. Valid no-CLI manifests must suppress stale AST CLI strings.
3. GREEN: consume shared typed `load_manifest`; fall back to AST only for absent/invalid metadata, keeping healthy siblings and source diagnostics.
4. Verify valid display names, explicit aliases, invalid JSON/encoding, module-only legacy plugins, and deterministic order.

## Task 3 — Forwarding semantics (separate RED → GREEN slices)
1. RED: actual Click command exit 7 and usage-error exit 2 survive lazy forwarding without a second generic error. GREEN: stop translating SystemExit into ClickException.
2. RED: inherited context object/default_map and full public command path reach a Click plugin/group; resources close. GREEN: use `make_context`/`invoke` for real Click commands with the lazy proxy's parent, no duplicated command name.
3. Verify help, no-argument help fallback, callback integer results (not exit statuses), argparse exits, sys.argv restoration on failure, duck `.main` compatibility, and missing/non-callable imports.

## Task 4 — Verification and handoff
1. Run new regressions immediately after each code change; then the affected registry/manifest/menu/CLI and previous robustness union, with JUnit under scratch phase3.
2. Run real fresh-process `csc --help` and one actual installed sample command/group with exit-status and import-free assertions in an isolated HOME. Never modify real user plugins.
3. Independent read-only spec then quality review of actual changed source/tests; fail closed on blocking findings. Parse exact totals, run scoped Ruff/security/whitespace checks, preserve source hashes across final verification.
4. Document current guarantees and limitations in the new CLI concept/user contract; append only own board/log hunks. No whole-repository or GUI parity claim.

## Verified closeout

- RED→GREEN repairs complete; new suite 34 cases. Final expanded union 1123 passed / 2 existing skips; focused union 127 passed (overlapping sets, not additive).
- Fresh top-level help imports no plugin package, Qt binding or jsonschema. Real isolated ZIP install → production CLI subprocess help/echo/exit 7/usage 2 → uninstall/fresh missing command passed.
- Independent spec/quality approved, with one documented existing Click eager-parser cleanup limitation. Parent parsed exact JUnit totals/identities and stable owned hashes; scoped Ruff/whitespace/security passed.
- Declaration audit remains 282 passed / 4 failed by the same previous-phase test identities. Active manifests, project lifecycle, GUI ports and allowlists were untouched. No staging, commits or pushes.
- Durable contract/resume: `okf/architecture/plugin-cli.md`, `docs/development/plugin_cli_contract.md`; scratch receipt `phase3/closeout-receipt.json`.

## Command prefix
From `/Users/tpeulen/dev/chisurf`:
`QT_QPA_PLATFORM=offscreen TMPDIR=/Users/tpeulen/.hermes/cache/scratch/plugin-system/phase3 PYTHONPATH=modules/chimol:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:. /Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest <named tests> -q --tb=short`
