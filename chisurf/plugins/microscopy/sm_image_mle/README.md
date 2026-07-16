# Molecule-wise MLE

Segments single molecules from confocal (CLSM) TTTR imaging data and fits a
single fluorescence lifetime + anisotropy per molecule by Poisson maximum
likelihood (tttrlib `Fit23`, the Maus-2001 `2I*` estimator).

## Architecture

The plugin follows the client-server / Qt-free-core standard:

- **`core/molecule_mle.py`** — the single Qt-free computational core.
  `segment_molecules` (watershed segmentation), `build_irf_vv_vh` /
  `compute_g_factor` (IRF preparation), and `fit_molecules` /
  `fit_molecules_from_files` build a per-molecule VV/VH histogram and fit it
  through the shared `chisurf.core.fluorescence.mle.Fit2x` harness. Returns a
  `MoleculeMleResult` (per-molecule `DataFrame`, label + intensity images,
  centroids) — no Qt, no plotting, no subprocess.
- **`api/`** — transport dataclasses (`MoleculeMleSettings`/`Request`/`Result`)
  and `analyze_request`, which runs the core in-process over a batch of files,
  writing `<stem>_analysis/molecule_data.tsv` per file and a merged
  `joint_output.tsv`.
- **`backend/services.py`** — ZMQ/JSON-RPC service registration
  (`sm_image_mle.analyze.run`, `sm_image_mle.contract.describe`).
- **`gui/`** — an AutoForm view (`molecule_mle.view.json`) over the Qt-free
  `MoleculeMleViewModel`; `SmImageMleTool` hosts it and runs the analysis on a
  background thread.
- **`cli/`** — `sm-image-mle analyze | contract | serve`.

## GUI usage

1. Launch from **Imaging → Molecule-wise MLE**.
2. Drag CLSM imaging file(s) and an IRF file into the two lists.
3. Set the detector channels (even = parallel, odd = perpendicular), the
   micro-time fit window, and the segmentation / Fit23 options.
4. Press **▶ Run**. The segmentation image (with molecule-centroid markers) and
   the per-molecule fit table populate when the run finishes; TSVs are written
   next to each file.

## Testing

`test/test_molecule_mle_core.py` drives the core end-to-end against a *simulated*
CLSM image built with tttrlib's photon simulator (`SimEngine`/`SimScanner`):
immobile fluorophores of known lifetime are raster-scanned, segmented, and
fitted, and the recovered lifetimes must track the ground truth. It skips
cleanly when tttrlib (or its simulator) is unavailable.
