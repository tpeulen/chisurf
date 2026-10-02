# Mean micro-time EMTK port

Native entrypoint: `chisurf.plugins.microscopy.img_pixel_micro_time.gui.app:make_app`.
The Qt entrypoint remains available for reference/legacy compatibility; native construction does not import it.

Implemented and exercised:

- TTTR open dialog, dropped source, authenticated MMFDB dataset picker, supplied MMFDB registration binding.
- Detector windows supplied by Imaging Setup and standalone editable named channels/micro-time gates; all windows computed together.
- Minimum photon threshold, snapshot background execution/progress/errors, result-discard cancellation, deferred pipeline context.
- Intensity, mean-time (ns), detector-window selection, per-frame mean-time movie, colormap/gamma/levels/frame/FPS controls.
- Imaging HDF5 append/create, source back-reference, legacy `mean_micro_time` PTO artifact identity and nanosecond column units.
- Native ndX per-pixel table handoff, pipeline Next hook, state restoration, native help/guide.
- Tooltips on all authored interactive controls; existing six ChiSurf locale catalogs installed. Untranslated new source strings use catalog fallback.

Evidence:

- `test/test_native.py`: four passing tests, including direct tttrlib equality for Leica SP5 and Leica SP8, high-count threshold discrimination, movie equality, HDF5/PTO round-trip, async dropped-source delivery, standalone setup validation, state, cancellation, Next, and populated Qt-blocked UI rendering in all six supported locales.
- Native factory checker: pass, zero Qt modules, 1200×800 and 800×600.
- Genuine historical Qt screenshot: `okf/plugins/emtk-references/microscopy__img_pixel_micro_time.png`; provenance in adjacent JSON (revision bf58e5f795cbe18a71ccb93401f566f469195a49).
- Populated EMTK screenshot: `okf/plugins/emtk-native/img_pixel_micro_time.png`, Leica SP8 routing channel 1, actual 512×512 map.
- Scoped Ruff: pass.

Limits still requiring integration evidence:

- Live MMFDB authentication/download/upload and main native imaging-pipeline transitions have not been exercised against a running service/host.
- Cancellation discards publication when the detached worker completes; it does not forcibly terminate TTTR library computation already executing.
- Existing catalog coverage varies; new plugin-specific sentences can fall back to English.
- Qt reference is initial state; a populated Qt-to-native pixel-level visual comparison remains outstanding.
