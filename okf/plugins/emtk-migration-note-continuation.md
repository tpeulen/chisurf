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

Closed 2026-10-20: the migration is finished. Every plugin opens its emtk
window; the preview gate (`emtk_preview.json`, `emtk_readiness`) and the
per-port evidence tree (`REPORT.md`, captures, inventories) were removed. The
queue below is history. At the 2026-10-07 fold the manifests declared native
factories for `burst_h2mm`,
`burst_mle_analysis`, `hydropro`, `mfd_prepare`, `burst_ebfret`, `alex_suite`,
`fret_docking`, `fps_json_editor`, `burst_analysis`, `burst_selection`, `acq`,
`mmfdb_admin`, `batch_analysis`, `wizards` and `traj_tools`; `code_editor`
(29 missing Qt controls at its first review) and `quenching_estimator` were
the last two ports accepted.

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
