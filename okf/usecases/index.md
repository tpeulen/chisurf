---
type: Reference
title: User Workflows & Use Cases
description: Text descriptions of what a ChiSurf user typically does, discovered and maintained by the headless GUI-tester job.
tags: [usecases, workflows, testing, gui, ux]
timestamp: '2026-07-25T00:00:00Z'
---

# User workflows & use cases

Plain-text descriptions of **what a ChiSurf user actually does**, one workflow per
file, discovered and kept current by the hourly GUI-tester job
(`com.chisurf.gui-tester`, see [scheduled-jobs](/workflows/scheduled-jobs.md)).
Each doc doubles as a **manual test script** (the numbered steps a person or an
agent follows) and a **UX record** (what worked, what confused, what to improve).

The tester drives the real Qt GUI **headlessly** (offscreen), walks a workflow the
way a user would, inspects the result (including screenshots), then writes the
use case here. Concrete, verifiable defects it finds are filed into the
[review findings queue](/reviews/findings.md) (so the fix job acts on them); softer
**UX/UI suggestions** stay here under each workflow.

## Coverage (typical user tasks)

The workflows a first pass should cover — expand as the tester discovers more:

- **Burst analysis** — single-molecule burst selection, BVA, burst MLE, FRET.
- **TCSPC fitting** — load a decay, pick a lifetime/FRET model, set the fit range,
  fit, read χ²ᵣ and parameters.
- **FCS** — correlate, fit diffusion/volume, filtered-FCS.
- **Correlation / TTTR tools** — channel definition, correlator, microtime
  histograms, LUT calibration.
- **Imaging / CLSM** — image representations, pixel selection, phasor, pixel-wise MLE.
- **Calculators & wizards** — FRET lines, kappa², anisotropy, the guided wizards.

## Per-workflow file format

`okf/usecases/<workflow-slug>.md`, one `##` step-list plus observations:

```
---
type: Reference
title: Use case — <workflow>
tags: [usecase, <area>]
---
# Use case: <workflow>
**Goal:** what the user is trying to achieve.
**Data:** the sample data / example used (repo path).
## Steps
1. … (each concrete UI action, in order)
## Expected
- what a correct run produces.
## Observed (last run: <date>)
- what actually happened; screenshots noted.
## UX / UI suggestions
- concrete, actionable improvements (not filed as bugs).
## Bugs filed
- RF-NNN … (cross-ref into /reviews/findings.md)
```
