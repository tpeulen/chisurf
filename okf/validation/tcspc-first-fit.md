---
type: Validation
title: TCSPC first-fit GUI responsiveness
description: Measured lazy GUI initialization and sample-preserving Qt drawing; scoped implementation verified, end-to-end Main pairing still pending.
resource: chisurf/gui/widgets/fitting/fit_subwindow.py
tags: [tcspc, performance, gui, metadata, qt]
timestamp: '2026-10-04T00:00:00Z'
---

# TCSPC first-fit GUI responsiveness

## Where to pick this up

1. The scoped GUI/metadata/emtk implementation is independently reviewed and test-green. Finish repeated **successful-action** Main before/after measurements; do not interpret these isolated fit-window timings as an Add-button result.
2. Earlier `paired-final` and `paired-accepted` Main data are invalid: Add fit published a real native window, then its history capture failed. Checking a window and 4096 channels did not prove success. The latest guarded Main smoke exits 0 on the current shared tree; its source hashes are recorded, but the cause of the changed behavior is not established and this does not retroactively validate earlier data.
3. Keep history/undo/redo and scientific validation enabled. Assert completed action/checkpoint, error/status absence, real native model, source identities and scientific parity before timing. Preserve independent project/session/main/macros changes outside this performance commit.
4. Optional further coverage: vertical/diagonal/fractional-width/transformed Qt stroke cross-sections. Current real-Qt horizontal cross-section pins effective legacy thickness; joins are not claimed pixel-identical.

## Implemented scope

- Demand-create the existing Code back face once; opening/closing/reopening and saved-definition navigation retain the editor and controls.
- Resolve existing plot exports and optional AutoForm section factories lazily, while preserving custom registrations and public imports.
- Demand-load the complete mmCIF key/description catalog; share compact metadata models instead of one Qt item per key. Preserve list-valued `ALL_METADATA_KEYS`, star imports, completion, custom keys, descriptions/tooltips and popup delegate lifetime. Inline sizing and uniform popup rows avoid scanning the entire catalog repeatedly.
- Batch every contiguous finite undashed plot run through emtk's optional painter polyline seam. Keep dashed/scalar fallback, nonfinite breaks, clipping, transforms, pen/brush state and open/closed paths. No decimation, resampling, model, precision or numerical dependency changes.
- Qt's legacy triangle primitive adds a one-pixel same-colour outline. The native pen includes that effective width; a real red/green pixel cross-section test and re-captured measured-data plots prevent thinner traces.

## Accepted measurement scope

CPU-only Apple ARM64, Python 3.12, PyQt5 offscreen, native `DescriptionModel_tcspc_polarized`, actual IBH `Decay_577D.txt` and `Prompt.txt`, 4096 channels. Three alternating fresh-process baseline/candidate pairs, with the second window in each process measuring warm GUI use. Input loading and initial scientific-package imports precede the timed window pipeline.

| Isolated fit-window pipeline | Baseline median | Candidate median | Speedup |
|---|---:|---:|---:|
| Cold | 1756.73 ms | 929.61 ms | 1.89x |
| Warm | 561.29 ms | 271.55 ms | 2.07x |
| Cold window construction component | 320.56 ms | 16.91 ms | component only |
| Cold initial plotting/painting component | 489.07 ms | 195.35 ms | component only |

Individual runs, loaded source hashes, exact model-output SHA-256, parameter values, fit ranges, tab inventory, the latest Main smoke and parsed independent reviews are preserved in [the evidence JSON](tcspc-first-fit.json). The paired numerical signatures match exactly. Stage medians need not sum to total medians. These measurements are not cross-platform or end-to-end application-startup claims.

## Verification

- Parent GUI/editor selection: 139 passed, 1 skipped, one delayed-update thread warning in `fit_actions.update_fit` (`IndexError` after fit-list teardown). The warning was also observed with original GUI modules; do not describe this as pristine full-system acceptance.
- Native fitting regression selection: 26 passed.
- emtk non-host suite: 2177 passed, 4 skipped. Command: `QT_QPA_PLATFORM=offscreen /Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest tests/ -q --ignore=tests/test_qt_host.py --ignore=tests/test_tk_host.py --ignore=tests/test_wgpu_host.py`.
- Fresh commit-time GUI contracts: **29 passed**. `QT_QPA_PLATFORM=offscreen IMP_BFF_GPU=off PYTHONPATH='modules/chimol:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:.' /Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest test/gui/test_fit_first_use.py test/gui/test_metadata_editor_first_use.py test/gui/test_metadata_editor.py -q`.
- Fresh commit-time emtk plot/painter selection: **105 passed**; new-test and scoped ChiSurf Ruff checks passed.
- Repository-wide PRD/plotting guardrails: 5 passed, 2 PRD failures in separately owned burst files/macros. Comparing original task-owned modules and allowlist entries reproduces the exact same failures; no new task-scope guard violation. Do not weaken the allowlist or include unrelated fixes.
- Original scoped implementation, subsequent metadata changes and final Qt stroke correction each have a parsed read-only independent review with no blocking security/logic findings. Reviews did not independently rerun tests; the parent ran verification.
- Real baseline/candidate native windows and editors inspected, then re-captured after stroke-width correction. Main tabs and Code open/reopen were driven in the isolated smoke process. No numerical result or full Main latency claim is inferred from a screenshot alone.

## Reproduction artifacts

The original probes are under `/Users/tpeulen/.hermes/cache/scratch/tcspc-first-fit/`: `profile_tcspc.py`, `main_tcspc.py`, `paired_tcspc.py`, `isolated-startup/sitecustomize.py` and archived original GUI/emtk source. Run the paired driver with `--direct-only` for the accepted isolated scope. Scratch may expire; the complete measured records, review verdicts and verbatim probe sources are durable in the evidence JSON. The embedded probes retain their original scratch paths and must be re-materialized with matching baseline files before reuse. Before rerunning Main, strengthen checkpoint-success assertions and keep current domain/history hashes fixed across pairs.

Primary implementation references checked: [Python module lazy exports](https://peps.python.org/pep-0562/), [Qt polyline/painter state](https://doc.qt.io/qt-6/qpainter.html), [Qt QObject/GUI-thread rules](https://doc.qt.io/qt-6/threads-qobject.html). Runtime verification uses actual PyQt5, not an assumed Qt6-only API.
