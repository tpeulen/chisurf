# CLSM native parity plan

- Preserve acquisition presets/header markers, routing channels, TTTR/HDF5 source loading, multiple CLSM objects and representations.
- Preserve intensity/mean microtime/weighted images, frame sum/mean/single reduction and calibration in ns.
- Preserve select/erase Gaussian brush with live decay, clear/save selections, region composition/edit/load/save and decay datasets/exports.
- Run reconstruction/statistics on snapshots, preserve UI event delivery and shared setup/pipeline context.
- Native fields/tooltips and file/MMFDB pickers must render with strict Qt import blockers; test synthetic and real photons, brush pointer input and photon conservation.
- Reference Qt adapters remain available, native manifest factory independently resolves.

## Evidence

- Pure manifest factory and populated draw verified under hard Qt import blockers at 900×650 and 1200×800.
- Real simulated PTU scanner reconstruction, physical header timing, unique authoritative microtime-bin tag and intensity/decay photon conservation tested.
- Native pointer painting tested; browser rating/note persistence, raw-copy bytes, TIFF and valid OOXML PNG report export tested.
- Combined CLSM/browser legacy tests plus PSF/Spot canonical helper regression: 51 passing tests.
- Genuine archived Qt references: `okf/plugins/emtk-references/`; native PIL captures: `/private/tmp/chisurf-native-imaging/`. Native docking intentionally changes presentation.
- Browser Next needs the native host coordinator; errors explicitly when standalone. DOCX uses standard OOXML without adding python-docx dependency.
