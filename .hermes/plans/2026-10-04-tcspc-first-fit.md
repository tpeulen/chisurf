# TCSPC first-fit responsiveness implementation plan

## Landing status (2026-10-04)

Scoped implementation, tests and independent reviews are complete. Local landing includes durable evidence and user/OKF documentation. Accepted isolated-native medians: cold 1756.73 → 929.61 ms; warm 561.29 → 271.55 ms. Latest guarded Main smoke passed, but repeated successful-action Main pairing remains open; earlier failed Main datasets stay rejected. The authoritative resume point is `okf/validation/tcspc-first-fit.md`. No history/scientific validation was bypassed, and unrelated work remains outside these commits.

**Goal:** Remove measured avoidable first-use imports and redraw overhead from creating a TCSPC fit, while keeping every scientific sample, model result, editor control and code-view capability.

**Architecture:** Load optional GUI feature implementations only when used; do not move Qt object creation off the GUI thread. Use emtk's existing optional `polyline` painter seam to batch solid traces, retaining the exact scalar fallback and dashed/gapped-series behavior. No scientific calculation or numerical precision changes.

**Stack:** Python 3.12, QtPy/PyQt5, source emtk, native IMP.bff; arm64 interpreter. No new packages.

## Measured baseline and hypotheses

Fresh native measured-data harness: `/Users/tpeulen/.hermes/cache/scratch/tcspc-first-fit/profile_tcspc.py`.
Data: actual IBH `Decay_577D.txt`/`Prompt.txt` (4096 rows), not synthetic benchmark arrays. Profiled first creation 2533 ms; unprofiled initial observation 1697 ms, warm 537 ms. Components: cold editor import/build 697 ms, hidden-code/plot window build 326 ms, initial plot/paint 497 ms; warm paint 391 ms. CPU model initialization 28–50 ms. Timings are provisional until repeated source-aligned pairs.

Ranked hypotheses, with predictions:
1. Eager optional section/plot imports account for cold-only latency. Removing unused imports should reduce new modules and cold construction without changing declared sections/plot classes.
2. FitSubWindow constructs a hidden CodeEditor, importing notebook/LSP/agent machinery even if Code is never clicked. Demand creation should remove this cost; Code navigation must still work once clicked.
3. Solid plot traces issue two independent triangle paths per segment. Batched paths should cut both cold and warm paint cost without dropping/decimating points or bridging NaN/Inf gaps.
4. Native TCSPC initialization is not the primary delay (28–50 ms), so numerical/backend changes are out of scope.

## Task 1: Reproduction and immutable source baseline
- Preserve baseline source/hashes and screenshots before changing production files (completed).
- Run cold/warm fresh-process probe with and without cProfile (completed).
- Run real `Main.onAddFit` through a smoke-mode isolated main window as an additional acceptance lane, with private runtime settings and no foreign RPC server adoption. Establish baseline before GUI implementation.

## Task 2: Demand-created Code editor (Codex scope)
Files: `chisurf/gui/widgets/fitting/fit_subwindow.py`, new `test/gui/test_fit_first_use.py`.
1. Add a fresh-subprocess RED contract: creating a native fit window does not create/import the hidden editor; the Code button still produces the existing back-face toolbar and editor on demand.
2. Run RED on original implementation.
3. Build the existing back-face contents once on Code access. Preserve any callers of `show_code_view`, `load_code_file`, external-definition navigation, function selection and Save/Apply. Code closes/reopens without duplicate editor/signals. Clean PRD references in this touched file by pointing to maintained GUI concept.
4. Run GREEN and existing code-view/fit-subwindow tests. Do not edit the concurrently dirty code_editor plugin itself.

## Task 3: Lazy built-in plot imports (Codex scope)
Files: `chisurf/gui/plots/__init__.py`, relevant test in `test/gui/test_fit_first_use.py`.
1. RED fresh-process contract: asking for LinePlot must not import FitInfo/metadata editor, residual-image/MFD/sampling plots or other unused plot implementations.
2. Map existing public exports and submodules to lazy module attributes with importlib, preserve from-imports and package submodule behavior; cache resolved attributes. No recursive `from . import same_name` implementation.
3. GREEN full registry-key resolution and existing model-plot surface tests. Public export classes and names remain unchanged.

## Task 4: Optional AutoForm section imports (Codex, only if proven needed)
Files: `chisurf/gui/autoform/sections/{__init__,registry}.py` and any minimal builtin registration changes; clean fitting package lazy exports if profiling demonstrates load through star imports.
1. RED contract for a minimal TCSPC editor not importing unrelated TTTR/photon-filter, state graph, code/editor or imaging section modules.
2. Replace eager registration import sweep with demand registration keyed by the shipped section/plot definitions. Built-in lookup must still return the exact factory, custom registrations take precedence, unknown keys retain prior behavior, and errors cannot silently skip required controls.
3. GREEN existing AutoForm, state-scheme/graph, custom-section and model-editor tests. Preserve Qt-free scientific layer.

## Task 5: Batched solid plot strokes (parent/emtk scope)
Files: `/Users/tpeulen/dev/emtk/emtk/widgets/plot.py`, `/Users/tpeulen/dev/emtk/emtk/qt_painter.py`, new `tests/test_plot_polyline.py`.
1. RED: native-polyline-capable painter receives one whole contiguous finite path, separated at nonfinite samples; no per-segment triangle calls. Existing painters with seven primitive methods still receive equivalent fallback triangles.
2. RED: QtPainter native polyline renders open and closed paths with width/colour, clipping and prior pen/brush state preserved; no fill across the path.
3. GREEN via `emtk.painter.polyline`; keep dash path phase, singleton behavior, axes/log mapping and clipping unchanged. Use QPainter/QPolygonF, FlatCap and explicit join style, do not resample/decimate data.
4. Run focused painter/implot suites and full non-host emtk tests; render actual TCSPC before/after and inspect.

### Task 5a: Preserve Qt stroke appearance after batching
The before/after capture exposed thinner native traces. The legacy Qt triangle primitive adds a one-pixel same-colour edge; the direct QPen must include that effective width. RED: compare the opaque cross-section with `emtk.painter.line` using the real Qt painter. GREEN: include the legacy edge width; retain all vertices, clipping and open paths. Re-run emtk, review the small follow-up, and regenerate native timing/capture evidence. Pixel-identical joins are not promised, but nominal/effective stroke thickness must not shrink.

## Task 5b: Measured metadata/Info first-use costs (parent, clean source)
Files: `chisurf/gui/widgets/metadata_editor.py`, new `test/gui/test_metadata_editor_first_use.py`.
Main-path cProfile shows full mmCIF dictionary loading during eager plot-class resolution; first Info visit additionally materializes thousands of QStandardItems in each metadata editor. This is GUI catalog work, not scientific computation.
1. RED: importing the metadata widget and displaying empty tables never parse the dictionary; explicit ALL_METADATA_KEYS imports still provide a real complete list.
2. RED: per-editor completers retain full catalog, descriptions and custom keys without allocating one QStandardItem per dictionary key.
3. GREEN: cache dictionary values on demand, expose the historical constant lazily, and use a string-list-backed role model. Keep all keys, tooltip and editing semantics; no reduced catalog.
4. Run existing metadata editor tests, fresh contracts and real Main/Info screenshots; remeasure before accepting.
5. The measured scientific-history capture/encode/decode/fingerprint cost is owned by the concurrent project/history lane. Do not drop history or overwrite that lane; record exact profile and coordinate the remaining work.

## Task 6: GUI responsiveness feedback (conditional, measured)
Prefer reduced synchronous cost over unnecessary worker/scheduler complexity. If Add fit still exceeds perceptible latency, show existing status/busy feedback and yield before scheduled creation via clean `fit_helpers.py`, preserve multi-fit order and errors and make state updates exactly once. Add real event-loop callback/order/re-entry regressions. Do not use fake progress or success before completion.

## Task 7: Verification, documentation and ownership
- Repeated sequential cold/warm source-aligned native measurements, baseline vs candidate loaded from isolated source copies, original emtk modules isolated if changed. Record imports, phases, model-output hashes, parameter values, fit range, every tab and control inventory. Include real main Add fit lane and Code on first use.
- Inspect real fit/editor/code-view screenshots. Run TCSPC fit/convergence, classic editor, AutoForm registry and project-UI persistence regressions; do not suppress existing issues or hide failed imports.
- Independent Codex read-only review after implementation; fix findings and rerun tests.
- Update task-owned OKF concept/evidence and user docs, short owned log hunk, board claim/resume point. Follow current repository rules; selective local commits only, no push. Existing dirty sources are not our baseline and cannot be restored/staged wholesale.

## Primary references checked
- PEP 562: module __getattr__/__dir__ lazy imports, caching and recursion caveats: https://peps.python.org/pep-0562/.
- Qt QPainter drawPolyline and painter state: https://doc.qt.io/qt-6/qpainter.html. Runtime is PyQt5; exercise the actual runtime rather than assuming Qt6-only API.
- Qt threads/QObjects: QWidget creation and rendering stay on the main thread: https://doc.qt.io/qt-6/threads-qobject.html.
