---
type: Report
title: Native fluorescence lifetime workflow audit
description: Audit of native lifetime-analysis tools, their retained scientific workflows,
  interaction and numerical evidence, visual references, and remaining acceptance
  qualifications.
---

# Native fluorescence lifetime workflow audit

These are native EMTK factories registered in the existing manifests. The original Qt entrypoints remain available as lazy compatibility adapters. Declared native entrypoints alone are not treated as proof of parity.

| Plugin | Preserved workflows | Evidence |
| --- | --- | --- |
| `synthetic_decay` | Lifetime and rotation component tables; VM and VV/VH generation; IRF convolution; seeded shot noise; CSV/NPY/JSON export; live dataset and calibrated fit registration | Native and legacy numerical/action tests; populated `test/renders/native-emtk.png` |
| `irf_estimator` | File/live dataset inputs; time calibration; channel range; background; SG/RL controls; cancellable response estimation; result curves; corrected paired export and live transfer | Native and legacy tests; populated `test/renders/native-emtk.png` |
| `tr_anisotropy` | Six original wizard stages; four independent or two stacked files; reader settings; draggable IRF background region; corrected IRF export; G/mixing corrections; editable lifetime/rotation spectra; local links and actual VV/VH/global fit registration | 23 native and existing tests passed; all six `test/renders/native-step-*.png`; real parameter links and shared global references tested |
| `maxent_decay` | Lifetime/FRET mode; file/live-fit/dataset inputs; donor spectra; priors; fit region; lifetime/distance grids; periodic convolution; fixed/optimized nuisance controls; actual MEM solver; actual 16-point L-curve and corner selection; actual Q-MCMC sampling; isolated cancellable jobs; original five export artifacts; advanced JSON preferences and legacy settings import | Native numerical, worker, cancellation and hard-Qt-blocked draw tests; existing solver/backend tests; populated lifetime and FRET PNGs |
| `lltf` | Original CLI fitting process and flags; fixed/selected lifetime count; probability threshold; YAML editing/loading/saving; streaming output; cancellation; actual result JSON; component/quality results; decay/IRF/fit and weighted residual plots; result export | Actual packaged example fit completed; native command/options, cancellation, configuration and hard-Qt-blocked draw tests; all native tabs and editor PNGs |
| `lifetime_analysis` | Five original child tools; lazy real factories; instance reuse; name/purpose search; descriptions and maturity notices; child mouse/key event routing; retained locale; selected panel preference; child docking layouts; help and gated real-control tours | Fresh subprocess blocks Qt imports and draws all five real children, checks identity, search, state and German locale; five native child PNGs |

All newly exposed interactive controls include tooltips. File and settings dialogs disable background controls. Native settings preserve declared preferences through `chisurf.emtk.state`; computed arrays and transient process identifiers are not stored as user preferences.

The combined MaxEnt, LLTF, anisotropy, hub and shared native-helper run passed 146 tests on 2026-09-27. A later focused run verifies subsequent display-only region/autoscale corrections. Native draw regressions install a hard import blocker for `qtpy`, PyQt and PySide in a fresh subprocess, rather than relying only on source import searches.

Visual references are the genuine Qt captures in `okf/plugins/emtk-references/fluorescence_decay__*.png` and their metadata. Native screenshots use the real EMTK PIL painter at 1440×1000. Toolkit styling differs deliberately; workflow order, controls, data plots, exports and side-by-side diagnostics are assessed against the Qt references. Nested-child Y-axis rotation was reported to the shared painter owner for correction before the lifetime-hub visual verdict is closed.

Scientific defects found during migration were corrected rather than emulated: synthetic metadata identifiers are preserved; paired IRF export retains calibration; polarized model topology and parameters are configured explicitly; nuisance fix controls now affect the real MEM solver; and the L-curve backend explicitly imports its math dependency to avoid test-order-dependent failures.
