# Phasor-FLIM native migration evidence

Native factory: `chisurf.plugins.microscopy.img_pixel_phasor.gui.app:make_app`.

## Implemented and verified

- Shared Qt-free estimator/view-model; genuine Leica_SP5 g, s and photon maps exactly equal to the Qt view-model. All detector windows and reference IRFs retained in signatures, worker parameters and outputs.
- Background snapshot delivery; progress and cooperative cancellation discard uncommitted results. Ctrl/Cmd+Enter runs, Escape cancels.
- Intensity, selected pixels, g, s, phasor density/scatter, g/s movies, photon frames and density movies. Loop/stop/FPS/frame controls. Histogram s orientation tested against explicit vertical UV; scatter movies use their selected frame.
- Named ellipse, rectangle and polygon cursors: enabled/inverted/combined/renamed/duplicated/removed, numeric geometry edits, plot drag handles and JSON import/export; gated image uses the shared scientific region masks.
- Detector setup import; standalone channel, microtime-range and per-detector reference IRF editing; thresholds and frequency; existing colormap/gamma/level controls.
- HDF5/PTO persistence reload exact scientific columns on real Leica data. Native ndX source and pipeline advance/state restoration exercised. MMFDB source picker and provenance bindings use the shared authenticated implementation.
- Help, guided tour and explicit tooltips; tooltip registration tested across every populated view. All six existing ChiSurf locale catalogs installed and rendered.
- Hard Qt-import blocking passes factory and all nine populated views at 1200×800 and 800×600, plus native ndX.
- Full plugin suite: 61 passed. Scoped Ruff and diff whitespace check clean.

## Reference artifacts

- Genuine populated Qt tool: `okf/plugins/emtk-references/img_pixel_phasor_populated.png` with class/source metadata alongside.
- Native populated phasor plot: `okf/plugins/emtk-native/img_pixel_phasor_populated.png`.
- Native g map: `okf/plugins/emtk-native/img_pixel_phasor_g.png`.
- Visual verdict after fixing density orientation: 92/pass, `.omx/state/img_pixel_phasor/ralph-progress.json`.
- Screenshots display the first256×256 genuine computed Leica pixels; computation/persistence tests use full data. Raw Leica data includes an uncalibrated cloud outside the universal semicircle. The reference acquisition has incomplete frame markers and tttrlib salvages one frame; this is recorded rather than replacing the source with synthetic output.

## Explicit remaining limitations

- Cancellation is cooperative; tttrlib may finish its active detector operation before the next checkpoint. Cancelled snapshots do not replace displayed maps.
- MMFDB authenticated online downloads/provenance registration were not exercised against a live database in this lane; shared wiring is present. Actual pointer-driven cursor drag and delayed tooltip appearance were not independently automated; geometry/numerical masks and tooltip registration/rendering are tested.
- Six existing catalogs are used, with English fallback for new strings absent from those catalogs; help prose is English. This is locale support, not a claim of fully translated new prose.
- Qt capture succeeds but existing pyqtgraph teardown produces deleted-QComboBox warnings after capture; the native app does not load Qt.
