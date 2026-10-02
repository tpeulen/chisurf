# Native PSF determination parity checklist

Before edits: use original tool/sections/view specification and pure view-model as the contract.

- Preserve TIFF stack loading, z browsing, colormap/contrast, detected markers and selected-bead picking.
- Preserve every physical/detection/ROI parameter and bound with a meaningful tooltip.
- Preserve detect, fit selected, fit all, bead navigation, FWHM overlay and x/y/z profiles/report.
- Preserve CSV batch export and add native settings-file roundtrip.
- Run expensive load/detection/fit/export actions off the UI thread; apply results on the UI thread.
- Preserve Qt adapters as references, register standalone native factory in manifest.
- Test fresh blocked-Qt construction and populated rendering, synthetic Gaussian fit/detection/export, background delivery and actual pointer picking.
- Genuine Qt reference screenshots are coordinated by the root reference lane.

## Verified implementation

- Standalone manifest factory operates in fresh processes that forbid Qt imports, including populated image rendering.
- Real pointer input tests fitting, file-dialog save and ROI dragging. Worker output reaches the original model only on the UI thread.
- Synthetic TIFF bead/spot data exercises detection, physical Gaussian widths, overlays, profiles, CSV and ROI/state roundtrips.
- Spot demo additionally generates real PTU photon data with Qt imports blocked, reconstructs four known objects, previews without writes and writes/readbacks a four-region measurement container.
- The simulated scanner layout is explicit in its versioned JSON sidecar; missing image reconstruction has an actionable error.
- Native screenshot verdict passes at 900×650 and 1200×800, with original Qt reference captures retained separately.
- Qt adapter construction also passes offscreen in a fresh process.

## Shared-helper extraction plan

Move ImageCanvas, SnapshotJob and RegionControls to canonical chisurf.emtk modules with compatibility reexports at their existing plugin paths. Preserve behavior through existing native image/raster/pointer/job tests before extending brush and tile-label support for CLSM/browser.
