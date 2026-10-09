---
type: Architecture
title: Production Plugin CLI
description: Import-free lazy command discovery, manifest ownership and faithful invocation.
resource: chisurf/core/cli/
tags: [plugins, cli, discovery, click, verification]
timestamp: '2026-10-04T00:00:00Z'
---

# Production plugin CLI

## Where to pick this up

1. Production lazy CLI identity/manifest/forwarding hardening is complete within the verified scope below. Do not reopen superseded installer review findings. The previous installation/dependency/RPC scope is recorded in [plugin-system diagnosis](plugin-system-diagnosis.md).
2. `csc` still owns a process-global registration snapshot. If in-process installation/disable/removal must refresh commands, add an explicit ownership-aware refresh that removes only its own proxies and preserves central commands; do not confuse finder-cache invalidation with unloading imported code.
3. Registry registration uses dependency order; production CLI metadata uses root/package order. Distinct valid IDs declaring the same command alias can choose different first owners. Unify this deliberately with metadata-only registration tests before claiming whole-system ownership parity.
4. Click eager parsing callbacks can register cleanup before a later parse failure; current `make_context` does not guarantee that cleanup runs. This existing Click limitation was independently reproduced and is not claimed fixed. Acquire resources during invocation, or explicitly scope a context-before-parse design before promising stronger cleanup.
5. Existing plugin dependency/RPC declaration debt belongs to active plugin/project owners. Re-run `test/test_plugin_dependencies.py`, preserve exact failed identities, and do not widen allowlists.

## Design

`chisurf/core/cli/__init__.py` provides the production `csc` facade. It does not use the eager `PluginRegistry.register_cli`: top-level help must not import heavy plugin modules. Its filesystem scan shares `PackageResolver` and `load_manifest` with registry/menu infrastructure, without importing `chisurf.plugins`. Import precedence is resolved before metadata; valid manifest IDs are claimed before command capability filtering. Manifest authority includes explicit lack of a CLI; AST fallback is retained for absent/invalid manifests.

A real Click command replaces its lazy proxy context using `make_context`/`invoke`. The original root parent supplies context object/defaults and command path; explicit exits remain exceptions rather than being confused with callback integer return values. Plain callable and duck `.main` compatibility paths remain. See [the developer contract](../../docs/development/plugin_cli_contract.md) for names, collisions, diagnostics and limits.

## Regression evidence

Initial metadata reader + CLI declaration + registry registration baseline: **93 passed**. New red runs demonstrated shadowed-package commands, duplicate IDs, unchecked invalid metadata, stale legacy CLI resurrection, rewritten explicit exits and missing context. Each production repair was immediately rerun against the focused regressions.

Final verification: **1123 passed / 2 existing skips** in the expanded core/import/client/menu/launcher/plugin-manager union; **127 passed** in the focused production CLI/metadata/registration union; the new CLI suite contains **34 cases**, included in both unions, not additional totals. JUnit declared totals and unique testcase identities were parsed. The skips are the existing external Chimol source export and optional QuEsT extension. Ruff, whitespace and scoped added-line security scans passed; owned source/test hashes remained stable across final integrated verification.

Independent spec then quality review passed with no security/logic blockers. The reviewer independently exercised 14 actual-source invocation cases and a read-only 133-record scan with unique valid IDs and no plugin imports; filesystem fixture and integrated pytest counts were parent-verified, not independently rerun. Its nonblocking eager-parser cleanup finding is explicitly limited above. The declaration guard remains **282 passed / 4 failed** with exactly the same four failing test identities as the previous phase, although concurrent plugin ports can change individual findings inside them. No manifests/allowlists were altered to hide this debt.

The real smoke installed a ZIP to an isolated HOME, started a fresh production CLI process for each command, verified top-level/plugin help (status 0), actual nested echo (0), explicit exit (7), usage error (2), then uninstalled and confirmed the command disappeared in a new process. The subprocess help regression checks that no plugin package, Qt binding or jsonschema is imported. No real installed user plugin data was changed.

## Reproduce

```bash
QT_QPA_PLATFORM=offscreen \
TMPDIR=/Users/tpeulen/.hermes/cache/scratch/plugin-system/phase3 \
PYTHONPATH="modules/chimol:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
/Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest \
  test/core/test_plugin_cli_robustness.py \
  test/core/test_plugin_cli_registration.py \
  test/core/test_plugin_metadata_reader.py \
  test/core/test_plugin_registration_robustness.py -q --tb=short
```

Run from the ChiSurf checkout. Scratch evidence: `plugin-system/phase3/combined-final.xml`, `focused.xml`, `declarations.xml`, `closeout-receipt.json`, `installed-cli-results.json`, `smoke_installed_cli.py`, `review-result.json`. Scratch can expire; durable tests and this contract are the reproducible record. This is not whole-repository, sandbox, hot-reload or GUI-port acceptance. No staging, commits or pushes by this task.
