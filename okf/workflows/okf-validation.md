---
type: Playbook
title: Knowledge bundle validation
description: Exact validation and incremental debt ownership for the knowledge bundle.
tags: [okf, validation]
---

# Knowledge bundle validation

## Where to pick this up

1. Open: W0b owns every existing finding in `test/okf_bundle_baseline.json`.
   Remove the defect and its exact record together; W0b is complete only when
   the validator reports zero findings and the baseline is empty.
2. Measure: run the commands below. The lint command inspects the working tree;
   the production guard reads committed source and the companion board HEAD.
   Coordinate board commits with its owner; a missing provider fails explicitly.
3. Blocked: aggregate release acceptance remains open while baseline debt exists.
   A passing incremental guard proves only that no new or stale findings exist.

## Commands and ownership

```sh
pixi run -e test python -m build_tools.okf.okf_lint --root okf --json
pixi run -e test python -m build_tools.okf.okf_lint --root okf --revision HEAD --json
pixi run -e test python -m build_tools.okf.baseline
pixi run -e test python -m pytest test/test_okf_bundle.py test/test_okf_baseline.py -q
pixi run -e docs docs-check-frontmatter
```

The validator discovers tracked and nonignored untracked Markdown. Its rules
cover frontmatter, links, wikilinks, PRD status/index agreement, known-issue
structure, board structure, log chronology, terminology and actionable resume
sections. Fenced and inline code is masked before prose checks. Bundle-root links
start with `/`; ordinary links resolve relative to the page. Filesystem and
repository-root paths are diagnosed rather than silently reinterpreted.

`--only FM,LINK` selects rules; `--fix` applies supported mechanical repairs.
Run fixes only on explicitly owned content. The validator reads a symlinked board
but refuses to mutate its external target; repair and commit it in its owning
repository. W0a does not run broad fixes against the live bundle.

The production guard reads one committed snapshot for both findings and source
context; link targets resolve in that Git tree, including pinned module trees.
The shared board is read from its owning repository HEAD, whose hash is reported.
A missing provider fails explicitly. `--revision` is read-only and cannot be used
with `--fix`. Dirty and untracked content remains visible to normal working-tree
lint and cannot leak into the committed baseline.

The baseline records rule, path, message, source line, owner and acceptance for
**each** existing finding. Comparison uses exact source context and occurrence
counts; line numbers are diagnostic only, so clean insertions do not invalidate
unrelated allowances. New defects and removed-but-still-allowed defects both
fail. The check never creates or expands a baseline automatically. New findings
must be fixed; cleanup removes allowances. The initial W0a snapshot is the only
bootstrap, and is published with its validator and evidence.

See [completion policy](../prds/prd-154.md#a0-completion-policy--2026-10-09-user-amendment)
and [change tracking](change-tracking.md) for batch publication and shared-tree
ownership. This mechanism does not waive the release's zero-debt requirement.

## Existing documentation gate debt

The W0a read-only docs check on 2026-10-09 found four pages without headers:
`docs/development/autoform_matrix_contract.md`, `docs/guides/87_channel_definition.md`,
`docs/guides/88_structure_tools.md`, and `docs/guides/97_settings_hub.md`.
W0b owns these existing metadata repairs; two paths contain foreign work. This
keeps the docs release gate open and is not a validator implementation failure.

## Initial W0a verification

The corrected committed-source baseline contains 2,420 findings: FM222, LINK41,
WIKI11, PRD26, KI217, BOARD126, LOG117, NAMES958 and PICKUP702. The first live-tree
snapshot was unsuitable for publication because it included foreign untracked
and modified pages; it has been replaced, not retained as extra allowances.
Fixture coverage proves dirty/untracked isolation, detection of new committed
debt, provider failure, typed YAML preservation, encoded filenames, log content
conservation and one-time board moves. Resume inspection stops at the next
heading, so later design sections are not misclassified as pickup work.
[Acceptance](../validation/release-readiness-w0a/acceptance.json) binds the single
[source archive](../validation/release-readiness-w0a/source-evidence.zip) to file hashes.
