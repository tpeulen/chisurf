---
type: Reference
title: Project Instructions (CLAUDE.md)
description: Agent-facing guidance for working in the ChiSurf repository.
resource: CLAUDE.md
tags: [reference, agents, conventions]
timestamp: '2026-07-05T00:00:00Z'
---

# Reference

`CLAUDE.md` at the repo root is the agent-facing guidance file. It covers the
[pixi environment/build](/workflows/build-and-env.md), common commands,
the [hybrid architecture](/architecture/index.md), the
[MMFDB store](/architecture/mmfdb.md), and the roadmap/PRD process. It also
points at this OKF bundle.

**`CLAUDE.md` is gitignored**, so it is not a durable record: it is per-checkout
and an agent editing it changes nothing another checkout will ever see. Every
rule stated there must therefore have its authority in a *tracked* OKF concept,
with `CLAUDE.md` acting as the short pointer. The working-practice rules and the
concepts that own them:

| Rule in `CLAUDE.md` | Owned by |
| --- | --- |
| Mark done when done | [specs/assessment](/specs/assessment.md), the PRD concepts |
| Track every edit in OKF, then commit | [change tracking](/workflows/change-tracking.md) |
| **Finish by leaving a resume point** | [change tracking](/workflows/change-tracking.md#leave-a-resume-point-in-okf) |
| Never implement a GUI blind | [testing](/workflows/testing.md) |
| Docs are part of the change | [change tracking](/workflows/change-tracking.md) |
| Fix breakage the moment you find it | [known issues](/references/known-issues.md) |
| Shared working tree — never destroy uncommitted work | [change tracking](/workflows/change-tracking.md) |

If a rule is added to `CLAUDE.md` without a row here and a home in a tracked
concept, it is lost the next time the file is regenerated.
