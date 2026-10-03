# Native Spot Finder parity checklist

Before edits: use original tool/view specification and pure view-model as the contract.

- Preserve file list, workflow recipes and every detector setting with constraints/tooltips.
- Preserve analysis ROI composition and editing; detected/picked regions remain read-only result overlays.
- Preserve preview without writes, batch detect/write, run table including failures and CSV/TSV export.
- Preserve demo, region browser/filter/info, Gaussian click picking, add/clear picks.
- Preserve shared setup/pipeline/calibration adapters, add native settings-file roundtrip.
- Run expensive actions on snapshot workers; publish complete results on the UI thread.
- Preserve Qt adapters, register native factory and require fresh blocked-Qt populated rendering.
- Test synthetic TIFF data, recipe reset, ROI restrictions, picking and export/data persistence.
- Genuine Qt reference screenshots are coordinated by the root reference lane.

## Verified implementation

- Standalone manifest factory operates in fresh processes that forbid Qt imports, including populated image rendering.
- Real pointer input tests fitting, file-dialog save and ROI dragging. Worker output reaches the original model only on the UI thread.
- Synthetic TIFF bead/spot data exercises detection, physical Gaussian widths, overlays, profiles, CSV and ROI/state roundtrips.
- Spot demo additionally generates real PTU photon data with Qt imports blocked, reconstructs four known objects, previews without writes and writes/readbacks a four-region measurement container.
- The simulated scanner layout is explicit in its versioned JSON sidecar; missing image reconstruction has an actionable error.
- Native screenshot verdict passes at 900×650 and 1200×800, with original Qt reference captures retained separately.
- Qt adapter construction also passes offscreen in a fresh process.
