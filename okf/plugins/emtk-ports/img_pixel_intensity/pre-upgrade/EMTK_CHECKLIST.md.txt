# Per-pixel intensity native parity plan

- Reuse the actual scientific IntensityViewModel and per-detector window, polarization, count-rate and background computations.
- Native TTTR/MMFDB input, Run/progress/dedup, imaging HDF5 with source reference, container persistence, native ndX table and Next pipeline actions.
- Preserve intensity/count-rate images, detector-window selectors, colormap/levels/gamma, raw frames/movie controls and saved settings.
- Snapshot compute/results delivery; defer pipeline/setup changes during jobs. Tooltips for every actionable control, help and guided tour.
- Hard-Qt-blocked factory/populated rendering, numerical polar/rate tests, real scanner samples, HDF5/source/container readback and input/state regressions.

## Verified

- Native manifest factory `gui.app:make_app` constructs/renders with strict Qt blockers, including actual Leica SP5 computation and native ndX table rendering.
- Exact scientific polarization counts, background-corrected rates, total-photon columns, unchanged-input dedup and snapshot delivery tested.
- Real Leica SP5 counts match independent tttrlib u32 pixel counters; real standard HDF5/source-reference and PTO artifact roundtrips match every pixel.
- Source/pipeline update during active compute is queued and cannot be overwritten by a worker snapshot. State/frame/gamma, native Next callbacks and standalone host message tested.
- Own tests5 passed; broader shared per-pixel/core/artifact tests37 passed; Ruff/scoped diff checks clean. No new dependencies.
- Genuine original Qt screenshot `okf/plugins/emtk-references/microscopy__img_pixel_intensity.png`; native maps/movie900/1200captures under `/private/tmp/chisurf-native-imaging/`. Visual verdict93 saved in `.omx/state/img_pixel_intensity/`.
- Native Next needs a supplied host coordinator, like the Qt embedded tool. Explicit MMFDB binding retains original ACL/registration service contracts; live external MMFDB accounts are not part of the local tests.
