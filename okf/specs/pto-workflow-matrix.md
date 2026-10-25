---
type: Spec
title: The .pto-only workflow matrix
description: The user journeys that must be provable in the real UI on a .pto
  container alone, with the filesystem paths preserved — the design seed for
  PRD-154 item 13 and the click-all scenarios that pin each leg.
tags:
- specs
- pto
- workflow
- click-all
---

# The .pto-only workflow matrix (PRD-154 item 13)

Owner directive 2026-10-25: prove ChiSurf works .pto-only in the real UI; the
filesystem flexibility of the old workflow must survive; the path a user takes
— compute decays, smFRET histograms, use outputs for decay or FCS computation,
then analyze — must be visible and battle-tested with the click-all program.

## The container invariants (what "pto-only" must mean)

1. **One substrate.** A `.pto`/`.cs.pto` carries the photon runs, the burst
   searches, every derived table (burst table, sub-ensemble decay, burstwise
   correlation) and the fits — nothing needs a sibling folder on the
   filesystem.
2. **Nothing is forced into it.** Direct-open of a vendor TTTR (PTU/HT3/SPC),
   of a folder of them, and of foreign formats keeps working exactly as
   before; importing then produces the same container.
3. **Readable everywhere.** ndX opens `.cs.pto` projects and `.pto`
   measurement containers and lists their stores (this exists:
   `ndx/io/pto_reader.list_tables`, `loading.py`'s `cs_project` importer);
   pto_inspector lists runs; legacy export writes the old formats OUT of a
   container.

## Workflow matrix

| # | Workflow | Entry (UI today) | Legs | Click-all scenario |
|---|---|---|---|---|
| W1 | Photon stream → burst search → E/S + TCSPC histograms | burst_selection: Files panel (drop or pick a `.pto`; RunPickerMixin lists runs) | run picker → search (schema-driven settings) → Histogram/Scatter panels → GMM populations | `scenario_burst_search_pto` |
| W2 | Selected bursts → sub-ensemble TCSPC decay → fit | burst_selection: "Decay from selected bursts" (`write_decay`) | pool micro times → stored beside the run → offered to the TCSPC fit window → fit + report | `scenario_subensemble_decay_fit` |
| W3 | Burst table → burstwise FCS → correlation fit | burst_fcs_correlator (lists burst tables of a container) | select bursts → correlate → fit window drag → fit | `scenario_burstwise_fcs_fit` |
| W4 | Whole-project analysis handoff | ndX: open `.cs.pto` → store choice | pick any stored table (bursts, decays, sampling stores) → gate/populations → pick back into ChiSurf | `scenario_ndx_project_analysis` |
| W5 | Import → container → full W1–W3 on imported data | burst_selection drop of a vendor TTTR → import to `.pto` | import → same W1–W3 legs | `scenario_import_then_analyze` |
| W6 | Fit results live in the project | any fit while a `.cs.pto` is open | fit lands in the project → save/reopen (graph session travels, PRD-154 item 5) → results survive | `scenario_project_roundtrip` |

## What is verified vs missing (2026-10-25)

Verified at API level: the e2e release scenario walks load `.pto` → burst
selection → MLE → H2MM → sub-ensemble decay → burstwise FCS → picker →
sampling → autosave → reopen → ndX → legacy export (14 steps, green).

Missing, and the reason this item exists:

- The legs above are walked by the click-all program only as plugin open/
  build/draw — not as **user journeys** across windows (W1–W6 above are new
  scenarios for `test/e2e/test_click_all_plugins.py`).
- The UI does not make the journey legible: no "what happens next" affordance
  after a search (the burst table says where results go, but not how to open
  the decay in a fit window or the table in ndX). Each scenario must end with
  the next entry point visible, not a dead end.
- The fit window's data picker must list container stores (sub-ensemble
  decays, correlation curves) beside files.
- ndX's pick-back-into-ChiSurf (population → fit) needs the same journey
  treatment.

## Battle-testing rules (the click-all contract)

- Each scenario runs in the real UI via `emtk.testing.Driver` (offscreen), as
  part of the W7 click-all program — same harness, same bounds, same
  hermetic-subprocess discipline as the existing 142-test file.
- Every scenario is deterministic: seeded demo container (the µs-ALEX demo
  generator writes a `.pto`), no network, no user state.
- A scenario fails when a leg is unreachable (no button/menu that leads
  there), not only when an assert trips — the point is the UX, so each leg
  asserts the affordance exists, then exercises it.
- Filesystem parity check ships with the matrix: W5 runs the same journey on
  the raw vendor files without ever writing a container first (except where
  the operation itself defines one).
