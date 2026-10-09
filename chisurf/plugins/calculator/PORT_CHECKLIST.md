# Calculator EMTK parity checklist

Before edits: compare original Qt handlers and view specifications against current EMTK apps.

- Preserve forward and inverse FRET computations, both distributions, and read-only HomoFRET rate.
- Preserve κ² model selection, recomputation, statistics, distribution and CSV export.
- Preserve all phasor overlays and reference table.
- Preserve RICS sweep, progress, table and CSV export.
- Extract numerical models from Qt adapters and supply Qt-free app factories.
- Restore numeric bounds from Qt view specs; document every actionable control including collapsible headers.
- Test pure factories in a fresh process forbidding Qt imports, numerical behavior and widget edits.
- Qt screenshot references remain coordinated by the parent task.

## Remaining calculator ports
- PSF: preserve optics, polarization, sampling, all display controls, native 3-D and slices, async compute, NPY/TIFF export.
- FCS saturation: reuse full kinetics/caches, editable arbitrary N-state matrices, brightness, units, plots/fit/residual/sweep, scheme JSON and session settings.
- Hub: lazy native factory resolution for every original registry entry, no Qt fallback.
- Confocal FCS and FRET-line: inspect original numerical handlers and match all inputs and outputs.

## Evidence and remaining integration boundaries

- Native factories exist for FRET/HomoFRET, κ², phasor, RICS precision, PSF, FCS saturation, calculator hub; confocal FCS and FRET line are registered outside this family.
- Numeric domains restored from Qt view specs, including clipping inverse FRET E=0/1 outputs to finite plot state.
- Every native control has a tooltip. Canonical Help/Guide uses Qt-free modules; tours notify actual edits/actions and have native targets.
- PSF retains every numerical/display field, threaded computation, exact NPY/TIFF exports, 3-D visualization and added orthogonal slices. The volume preview samples up to 6,000 voxels; exports and slices retain the complete volume.
- Saturation retains the original numerical/cache/session methods in a pure model, all schemes/rates/brightness/units/optics, fit/residual/profile/power-sweep plots and scheme/session files. Ground-state dark excitation stays read-only; zero power is available for the guided baseline. Restoring display rate units also restores the physics unit.
- FRET line uses live BFF model ports (value/bounds/fixed), independent donor/distance/lifetime component counts, scalar settings, reference spectra from live fits/registered models, Global View registration, mixture/sweep collection and CSV export.
- FRET-line Push to ndX uses an explicit native overlay callback. Discovery of legacy Qt Overlay widgets is intentionally absent from the native path; the native host must provide that callback.
- Hub constructs native children lazily, keeps their state, forwards local input and closes registered child models through its close hook.
- Scientific regression suites and fresh processes forbidding Qt imports validate construction and rendering at 900×620 and 1200×800. Real desktop interaction/export-dialog acceptance is a separate visual/host QA surface coordinated by the parent task.
- Historical Qt tool implementations remain as compatibility/reference adapters. Native manifests route independently through gui.app:make_app.

## Visual follow-up plan
- Separate FRET live editor from mixture/sweep/actions; retain live model ports and all existing behavior tests.
- Expose saturation brightness/optics fixed-state and bounds controls via compact parameter details.
- Fix shared spec field labels and honor collapsed optional panels.
