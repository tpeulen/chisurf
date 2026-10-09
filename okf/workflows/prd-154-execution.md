---
type: Playbook
title: PRD154 completion prompt
description: Reusable execution prompt for finite release batches, proportionate verification and durable handoff.
tags: [process, release, execution]
timestamp: '2026-10-09T00:00:00Z'
---

# PRD154 completion prompt

Use the following prompt in the main execution thread after its current frozen
batch lands. The authoritative policy is [PRD154 A0](../prds/prd-154.md#a0-completion-policy--2026-10-09-user-amendment).
This prompt does not mark any work complete or authorize discarding shared edits.

```text
Continue PRD154 to verified completion. Read CLAUDE.md, the PRD's resume and A0,
then the existing current-job record. Read only the selected workstream's Part B
and Part E design. Preserve prior accepted work; do not restart the programme or
repeat unchanged checks. A0 overrides conflicting older execution instructions.

First land any already-frozen batch. Next close W0a's missing guard prerequisite
without doing the full W0 cleanup. Then follow the recorded workstream order.

Choose one finite batch with exact ownership and a short acceptance checklist.
For tooltip/i18n/annotation metadata, sweep a plugin family or coherent file
group, rather than publishing one control at a time. Fix shared renderer/guard
mechanisms once in their owning repo. W6g coordinates family owners; it must not
absorb all plugin/core/game repairs or prevent the handoff to W6f.

Implement the selected approach once evidence supports it. Stop speculative
re-planning and repeated inventories. Fix blocking defects; assign other findings
to their real workstream in OKF and return to the batch. Use bounded parallel
owners on disjoint files when useful, with one integrator for shared files.

Preserve scientific correctness and functionality: real inputs, independent
numeric references, controls/options, units, row alignment and provenance.
Run targeted regression files during implementation. Freeze the source, generate
catalogue/locales once, then run applicable guards once. After a failure rerun
only affected checks. Handle committed-HEAD guards as A0 specifies; no bypasses.

GUI changes: one realistic before capture, inspect final default and narrow,
max four captures unless a specific failure requires another. Contact sheets for
multiple panels. No recapture for metadata, formatting, annotations, fixtures or
unchanged GUI; verify those with appropriate checks.

Keep one concise current-job record at meaningful milestones. Publish code,
applicable docs, one final evidence archive and OKF tracking together in focused
plain local commits. No separate receipt/status commit just to say a commit
happened. Never add -A, stash, reset --hard, restore, checkout --, clean or push.
Stage only owned hunks; keep .zed tasks ignored on disk.

Report acceptance criteria closed and actual blockers. If an hour closes no
criterion, diagnose the concrete blocker and take a bounded implementation step.
Once a batch passes, commit and move to the next owned batch. Do not stop at a
plan, a source-only claim, or a passing debt baseline. Keep aggregate gates open
until their owners actually close them; complete PRD154 only with Part D evidence.
```

Model selection is separate from this execution contract. A practical starting
point is Astra at medium reasoning for difficult programme/root-cause decisions,
Sol 6.1 at medium for bounded implementation, and Luna for simple inventories.
Use the available model selected at launch; do not change runtime/configuration
mid-batch to satisfy this recommendation. Judge it by acceptance criteria closed
per elapsed hour and regression quality, not token volume alone.
