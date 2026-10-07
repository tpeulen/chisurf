---
type: Plugin Concept
title: Native migration root-note continuation
description: Source-verified live fronts preserved from historical root queue and task notes without taking ownership of the existing untracked inventory.
tags: [plugins, emtk, migration, validation]
timestamp: '2026-10-07T00:00:00Z'
---

# Where to pick this up

Use the source-verified continuation below with
[the existing inventory](emtk-migration-inventory.md). Its original foreign
untracked content is preserved for the W0 ownership pass; this focused record
commits only the new root-note fold.

## Root-note queue disposition — verified 2026-10-07

This continuation record folds `AGY_BRIEF.md` and `CODEX_TASK.md` from
2026-10-03; it does not replace the historical inventory above or claim that a
factory declaration is acceptance. Workstream order and ownership now come
from [the release programme](../prds/prd-154.md), and acceptance from
[the documentation standard](documentation-standard.md).

The old four-item preview snapshot is superseded: the live
[preview file](../../chisurf/core/plugin/emtk_preview.json) contains only
`code_editor`. The previously described missing-port queue has moved: the
current manifests declare native factories for `burst_h2mm`,
`burst_mle_analysis`, `hydropro`, `mfd_prepare`, `burst_ebfret`, `alex_suite`,
`fret_docking`, `fps_json_editor`, `burst_analysis`, `burst_selection`, `acq`,
`mmfdb_admin`, `batch_analysis`, `wizards` and `traj_tools`. Reports exist under
`emtk-ports/<id>/REPORT.md` for these except `burst_selection`; declaration,
report existence and removal from the preview list are three different facts.

1. Re-audit `code_editor` against its current [report](emtk-ports/code_editor/REPORT.md)
   and real controls before changing its gate entry. The old rejection recorded
   29 missing Qt controls and editor input gaps; that is historical evidence to
   compare against, not a current measurement or permission to ungate it.
2. `quenching_estimator` remains Qt-only in its
   [manifest](../../chisurf/plugins/quenching_estimator/manifest.json), despite
   [an existing report](emtk-ports/quenching_estimator/REPORT.md). Its factory can
   construct while its layout and external-viewer imports remain broken; see
   [the current programme evidence](../validation/release-readiness-w7.md).
3. For already declared factories, fill any missing populated screenshots,
   click coverage, control inventory or tour evidence before assuming a port is
   accepted. Re-derive the queue from manifests plus the preview file and reports;
   do not reuse the old 123/109 totals or the dead-session priority list.

The `fret_docking` owner is
[the modelling/fret plugin](../../chisurf/plugins/modelling/fret/manifest.json),
not the obsolete `modelling/fret/fret_docking` path. The old brief's prohibition
on touching sibling emtk or posting a shared-board claim was specific to that
session's sandbox/supervision and is superseded by current repository rules.
Historical commit ids remain provenance in the original notes, not unverified
instructions to repeat their implementation.

The historical strict-xfail worklist named tour-card buttons over a data table,
Ctrl+A in table filters/cell editors, and Enter on an emptied text field. Treat
these as scenarios to re-check against current emtk input/guide tests, not as
newly established defects; the old table-resize/reorder/multiselect, image-export
and docking-overflow gap list is likewise a capability audit before acceptance.
