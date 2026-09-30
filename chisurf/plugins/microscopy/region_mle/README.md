# Region MLE

Segments single molecules from confocal (CLSM) TTTR imaging data and fits a
single fluorescence lifetime + anisotropy per molecule by Poisson maximum
likelihood (tttrlib `Fit23`, the Maus-2001 `2I*` estimator).

## Architecture

The plugin follows the client-server / Qt-free-core standard:

- **`core/region_mle.py`** — the single Qt-free computational core.
  `segment_molecules` (watershed segmentation), `build_irf_vv_vh` /
  `compute_g_factor` (IRF preparation), and `fit_regions` /
  `fit_regions_from_files` build a per-molecule VV/VH histogram and fit it
  through the shared `chisurf.core.fluorescence.mle.Fit2x` harness. Returns a
  `RegionMleResult` (per-molecule `DataFrame`, label + intensity images,
  centroids) — no Qt, no plotting, no subprocess.
- **`api/`** — transport dataclasses (`RegionMleSettings`/`Request`/`Result`)
  and `analyze_request`, which runs the core in-process over a batch of files,
  writing `<stem>_analysis/molecule_data.tsv` per file and a merged
  `joint_output.tsv`.
- **`backend/services.py`** — ZMQ/JSON-RPC service registration
  (`region_mle.analyze.run`, `region_mle.contract.describe`).
- **`gui/`** — the Qt-free `RegionMleViewModel` (`view_model.py`) behind two
  front ends. The native emtk app (`app.py`, `entrypoints.emtk`) draws
  `region_mle_emtk.view.json` over `RegionMleModel` (`model.py`: the
  view-model plus window state) and runs the analysis on a
  `chisurf.emtk.jobs.SnapshotJob`; its `custom` sections (file lists, region
  editor, region image, decay plot) are drawn by callbacks in `app.py`. The Qt
  `RegionMleTool` (`tool.py`, AutoForm over `region_mle.view.json`) stays as
  the legacy fallback.
- **`cli/`** — `region-mle analyze | contract | serve`.

## GUI usage

1. Launch from **Imaging → Region MLE**.
2. Drag CLSM imaging file(s) and an IRF file into the two lists.
3. Set the detector channels (even = parallel, odd = perpendicular), the
   micro-time fit window, and the segmentation / Fit23 options.
4. Press **Run**. The region image (analysis region, region outlines and
   numbers, the selected region's marker) and the decay plot populate when the
   run finishes; TSVs are written next to each file.

## Testing

`test/test_region_mle_core.py` drives the core end-to-end against a *simulated*
CLSM image built with tttrlib's photon simulator (`SimEngine`/`SimScanner`):
immobile fluorophores of known lifetime are raster-scanned, segmented, and
fitted, and the recovered lifetimes must track the ground truth. It skips
cleanly when tttrlib (or its simulator) is unavailable.
