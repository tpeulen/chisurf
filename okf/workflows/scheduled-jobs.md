---
type: Playbook
title: Scheduled Maintenance Jobs
description: Durable macOS LaunchAgents that wake Claude Code headlessly to keep translations, docs, and the roadmap moving.
resource: build_tools/jobs/
tags: [process, automation, i18n, docs, prds, launchd]
timestamp: '2026-07-25T00:00:00Z'
---

# Scheduled maintenance jobs

`build_tools/jobs/` holds **OS-level scheduled jobs that drive Claude Code
headlessly** for upkeep that needs judgement (translating new UI strings,
reconciling docs with the source, advancing the roadmap). Unlike an in-session
cron, these are **macOS LaunchAgents** — they survive restarts and sessions and
run until removed. They exist because the work is recurring and open-ended, not
something a deterministic script can do alone.

## How it works

Each LaunchAgent runs `build_tools/jobs/claude_job.sh <name> <prompt-file>`, which
sets a launchd-safe `PATH`, `cd`s to the repo, and runs
`claude -p "$(cat <prompt>)" --dangerously-skip-permissions`, logging to
`build_tools/jobs/logs/<name>-YYYYMMDD.log`. The **task prompts in
`build_tools/jobs/prompts/` are the safety boundary** — each one scopes the job to
a narrow set of files and forbids push / history rewrites (`--dangerously-skip-permissions`
is needed only because an unattended run has no TTY to approve tool calls). A
`mkdir` lock (stock macOS has no `flock`) makes a long run skip the next tick
instead of overlapping. Credentials come from the machine's `~/.claude` login; if
it expires the run fails and is logged.

The prompts read at runtime, so editing a prompt changes the next run's behaviour
**without reloading** the agent; only plist changes (schedule, paths) need a
`launchctl unload && load`.

## The jobs

| Label | Cadence | What it does |
|-------|---------|--------------|
| `com.chisurf.translate-ui` | daily 03:17 | `i18n-extract` → translate untranslated `de`/`fr` (glossary-consistent, skipping identifiers/symbols/units) → recompile `.qm` → commit the catalogues. Pairs with [PRD-63](/prds/prd-63.md) / [i18n](/subsystems/i18n.md). |
| `com.chisurf.build-docs` | daily 03:47 | detect where `docs/` **and** `okf/` drifted from the source, update them to match the code (with `okf/log.md` tracking), then the warning-free Sphinx rebuild. |
| `com.chisurf.improve-prds` | every 30 min | pick ONE small roadmap item (`okf/prds/` + [assessment backlog](/specs/assessment.md)), implement it, run the **mandatory test + lint gate**, and commit **only if green** — else a knowledge-only update or a no-op. |
| `com.chisurf.review-code` | every 30 min (:00/:30) | critically review a focused code slice and append verified findings to [`okf/reviews/findings.md`](/reviews/findings.md) (OPEN). **Reviews only — never edits source.** |
| `com.chisurf.fix-issues` | every 30 min (:15/:45) | fix ONE OPEN finding from the queue behind the **test + lint gate**, flip it FIXED, and commit only if green. |

| `com.chisurf.gui-tester` | hourly (:07) | *drive the real Qt GUI headlessly* (offscreen) through one typical user workflow, record the use case in [`okf/usecases/`](/usecases/index.md), file concrete defects into the [findings queue](/reviews/findings.md), and note UX/UI suggestions. **Tests only — never edits source.** |

The middle pair forms a **review → fix pipeline**: `review-code` *produces*
findings into the queue at :00/:30, `fix-issues` *consumes* them one at a time
15 min later at :15/:45. The queue file `okf/reviews/findings.md` is the hand-off,
keeping the two decoupled and distinct from the human-curated
[cleanup backlog](/specs/assessment.md). The **`gui-tester`** feeds the same queue
from a different angle — instead of reading source it *uses* the software, so bugs
that only show up in a live workflow (bad defaults, dead controls, broken layout,
wrong results on real data) also reach the fixer, while its durable output is the
growing set of use-case / manual-test docs under [`okf/usecases/`](/usecases/index.md).

## Rules the jobs inherit

All three obey [change tracking](change-tracking.md) and the shared-working-tree
rules in `CLAUDE.md`: commit **locally only, never push**, only the files they own,
**by explicit pathspec**; no `git add -A` / `reset` / `rebase` / `stash` /
`--force`; no commit trailers. The self-improvement job additionally **never
commits unverified code** — tests and lint must pass first, or it reverts its own
edits and does a documentation-only update.

## Operating them

Install, verify, run-now, reschedule, and uninstall are documented in
`build_tools/jobs/README.md`. Logs live under `build_tools/jobs/logs/` (gitignored).
The self-improvement job is the aggressive one — autonomous, test-gated code
changes every 30 minutes; watch its log on first activation, and prefer running it
when other agent instances are quiet to avoid shared-tree collisions.
