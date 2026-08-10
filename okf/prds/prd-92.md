---
type: PRD
prd: "92"
title: "PRD-92: Spot finding is not lifetime fitting — a region-property MLE fed by a spot finder that persists its regions"
description: sm_image_mle segments, measures, gathers photons and fits inside one 897-line core, and fit_molecules re-runs the segmentation itself, so the regions cannot be inspected, corrected, reused or produced by anything else. Split it — a spot-finder plugin that detects spots and writes region properties into the .pto container, and a region-property MLE that reads them. The seam is the container, not a function call, and the load-bearing question is that a region table of scalars cannot say which photons belong to a region.
status: draft
phase: "scoped from the existing code; nothing implemented"
resource: chisurf/plugins/microscopy/sm_image_mle/
tags: [prd, imaging, roi, mle, spot-detection, pto, provenance, plugins, microscopy]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

Nothing is implemented. The order below is the intended one, and each item says
what it unblocks.

1. **Settle the pixel-membership question first (§3).** Everything else is
   plumbing that has been done before in this tree; this is the one decision
   that cannot be deferred, because it decides what the spot finder writes.
   A region table of scalars — centroid, area, eccentricity — is what
   `regionprops` gives and what a person wants to look at, and it is **not
   enough to fit**: the MLE reaches a molecule's photons through
   `prop.coords` → `clsm[0][r][c].tttr_indices`, one pixel at a time. Persist
   the wrong thing and the second plugin has to re-segment, which is exactly
   the coupling this PRD exists to remove.
2. **Then the container contract (§4), before either plugin is written.** The
   burst side learned this the expensive way: a companion format that merges by
   position fails *silently* when a row is missing rather than absent
   ([burst companions](/subsystems/burst-companions.md)). A region table has
   the same shape and needs the same rule — one row per detected region
   including the ones the fit skipped.
3. **The rename is not cosmetic and is the cheapest stage (§5).** "Molecule-wise
   MLE" names the *sample* the tool was written for; the tool fits whatever
   regions it is handed, and after the split it will be handed regions from a
   detector it does not know about. Doing the rename first means the split is
   written against the final names.
4. **Reuse, do not re-derive, the estimator half (§6).** `Fit2x` /
   `fit_many` / `assemble_vv_vh` / the IRF preparation / the `min_photons`
   sentinel path are all shared machinery already
   ([MLE lifetime fitting](/subsystems/mle-lifetime-fitting.md)); the region
   MLE keeps them unchanged. A stage that edits `chisurf/core/fluorescence/mle/`
   has gone wrong.

## Traps recorded in advance

* **Label 0 is background and label gaps are regions that own no pixel.**
  Filtering regions by deleting labels leaves a non-contiguous label image, and
  every consumer that reads it as "1 to max" — `regionprops` among them — then
  reports empty regions. `relabel_sequential` exists in
  `chisurf/core/roi/segmentation.py` for exactly this and must be applied
  *before* the table is written, or the file carries the bug
  ([ROI](/subsystems/roi.md)).
* **The analysis region is applied before the threshold, not after.**
  `MoleculeMleSettings.roi` confines the search *ahead of* Otsu, so the region
  sets its own level. A spot finder that thresholds the frame and then crops
  produces different regions from the same settings, and the difference is
  invisible in the region count.
* **`centroid` and `centroid_weighted` are both in the table and are not the
  same point.** The unweighted one is the shape's centre; the intensity-weighted
  one is where the molecule is. A consumer that picks the wrong column gets an
  answer that is wrong by a sub-pixel amount, which no assertion will catch.

# Problem

`chisurf/plugins/microscopy/sm_image_mle/core/molecule_mle.py` is 897 lines
doing four separable jobs:

1. **Segment** — Gaussian smooth, Otsu (or fixed) threshold, clear border,
   distance-transform watershed seeded on local maxima (`segment_molecules`).
2. **Measure** — `regionprops(labels, intensity)`, reduced to a handful of shape
   columns by `_shape_columns` (`area`, `centroid`, `perimeter`, `circularity`,
   `eccentricity`, `solidity`, intensity mean/max).
3. **Gather** — for each region, walk `prop.coords` and collect
   `clsm[0][r][c].tttr_indices`, then build the VV/VH micro-time histogram.
4. **Fit** — `Fit23` through the shared `Fit2x` harness, batched via `fit_many`
   when the model curves are not needed.

Jobs 1–2 are imaging. Jobs 3–4 are spectroscopy. They are welded together in
three ways, and each one costs something concrete:

* **`fit_molecules` re-runs `segment_molecules` internally.** There is a
  `segmentation_preview()` that returns exactly the labels the fit will use —
  and the fit ignores it and segments again. So a user who tuned the
  segmentation, looked at it, and was happy with it cannot then *fit that*: they
  fit a second segmentation that happens to agree because the settings are the
  same. It agrees until a setting is threaded through one path and not the
  other, and then it disagrees without saying so.
* **The regions are not persisted anywhere.** They exist inside a
  `MoleculeMleResult` for the lifetime of the process. A segmentation cannot be
  reviewed later, corrected by hand, compared between parameter sets, shared
  with a colleague, or fed to anything that is not this plugin. The per-molecule
  table that *is* written carries the shape columns, but not the pixels, so it
  cannot be fitted again.
* **No other detector can feed the fit.** The tree has grown real spot
  detection since this plugin was written — `blob_log` / `blob_dog` build a
  scale space and return each spot's *width*, `difference_of_gaussians` and
  `white_tophat` are in `chisurf/core/roi/segmentation.py`, and `img_tracking`
  has an à-trous multiscale detector that is measurably better than a single
  threshold at rejecting hot pixels. None of it is reachable from the MLE,
  because the MLE's segmentation is a private function call with a fixed
  algorithm.

The same fusion also makes the plugin's name wrong. `Imaging:Lifetime:Molecule-wise
MLE` describes the sample (single molecules on a coverslip) rather than the
operation (fit a lifetime per region), and the operation is the general one:
beads, vesicles, cell nuclei, and hand-drawn regions are all regions with
photons in them.

# Goals

* One plugin that **finds spots** and writes what it found, with provenance,
  into the `.pto` container beside the photons.
* One plugin that **fits regions**, reading those regions rather than deriving
  them, and fitting *exactly* the regions it was given.
* A region table that is a **file format**, not an in-memory object: readable by
  the next session, by a different tool, and by a person.
* No change to the estimator. The 2I\* / `Fit23` path, the VV/VH assembly, the
  IRF preparation and the batching stay as they are.

## Non-goals

* Manual region editing in the spot finder beyond what the shared
  `RegionCollection` / `RegionEditor` already provides. The shared ROI GUI is a
  separate surface and this PRD consumes it rather than extending it.
* A new segmentation algorithm. Everything needed is in
  `chisurf/core/roi/segmentation.py` after PRD-86; this PRD *exposes* it.
* Multi-frame / time-resolved spot tracking. That is `img_tracking`, and the
  region table is deliberately shaped so a per-frame table is a later addition
  (§4) rather than a redesign.

# 3. Pixel membership — the decision everything depends on

The MLE needs, for each region, the set of TTTR indices belonging to it. It gets
them today from `prop.coords`, the region's pixel list. A persisted region
therefore has to carry its pixels in some form, and there are three candidates:

| Option | What is stored | Cost | What it loses |
|---|---|---|---|
| **A. Scalars only** | the `regionprops` columns | smallest | everything — the MLE must re-segment, which is the coupling this PRD removes. Rejected. |
| **B. Label raster + scalar table** | an `image_data` artifact holding the `int32` label image, plus one table row per label | one raster per field, compressible, exactly what `regionprops` consumes | nothing for pixel-connected regions; a region cannot overlap another |
| **C. Per-region coordinate column** | run-length or `(r, c)` blob per row | no raster, regions may overlap | a variable-length binary column in a numeric table, which the container's table vocabulary is not shaped for |

**Recommended: B.** It is the shape the rest of the tree already speaks — the
label image is what `regionprops`, `remove_small_objects`, `relabel_sequential`
and `MaskROI` all take, `chisurf/core/fio/pto.py` already names `image_data` as a
primary artifact kind, and the join is a single integer column. C is the honest
answer for overlapping regions and should be revisited only if a detector that
produces them arrives; the analytic-ROI path (`ROI.to_mask`) covers the
hand-drawn overlapping case without touching the raster format.

Consequence to write into the contract: **the table's `label` column is the key
into the raster**, and the two are one artifact pair that must be written and
read together. A table without its raster is a table of measurements, which is
useful to a person and useless to the fit.

# 4. The container contract

Written through the existing generic seam —
`chisurf/core/fio/analysis_path.py::write_tables` already takes
`artifact_kind` / `operation_type` / `row_grain`, so no new writer is needed:

```
artifact_kind  = "region_table"     (scalars)  /  "image_data"  (label raster)
operation_type = "spot_detection"
row_grain      = "region"
```

Rules, mirroring [burst companions](/subsystems/burst-companions.md) because the
failure mode is identical:

* **One row per detected region, including regions the fit skipped.** A region
  below `min_photons` gets a sentinel row (NaN parameters), never a missing row.
  Anything that later merges a fit result against this table merges by position.
* **`label` is first and is the raster key**, contiguous from 1, after
  `relabel_sequential`.
* **Column names are namespaced by origin** — `region.area`,
  `region.centroid_y`, `spot.sigma_x`, `fit.tau` — so a fit table and a
  detection table can sit in the same run without a name collision, and a reader
  can tell which stage produced a column.
* **All-numeric.** The source file name belongs in the artifact's provenance,
  not in a string column (`with_source_column` exists because a *folder* of TSVs
  had nowhere else to put it; a container does).
* **Provenance**: the region table's parent is the `image_data` raster or the
  photon stream it was derived from; the MLE result's parent is the region
  table. That makes a **3-deep chain** — photons → regions → fits — which
  [PRD-88](prd-88.md)'s matrix does not currently cover and should gain as a
  cell.

Frames: the table carries a `frame` column (0 for a projected field). A per-frame
detector fills it; the current projected-intensity detector writes zeros. This
is one column now, and it is what stops a time-resolved detector from needing a
second format later.

# 5. The two plugins

## 5.1 `microscopy/spot_finder` — new

*Display name* `Imaging:Spot Finder`. Detection only.

* **Core** (`core/spots.py`, Qt-free): `SpotFinderSettings` — the segmentation
  half of today's `MoleculeMleSettings` (`seg_sigma`, `seg_threshold`,
  `peak_footprint_size`, `min_area`, `roi`) plus a `method` selecting between
  the watershed pipeline, `blob_log`, `blob_dog` and a plain threshold. Returns
  `SpotFinderResult` (label image, region table, analysis ROI, background rate).
* **Persistence**: `write_spots(container, result, settings)` → the artifact pair
  of §4. `read_spots(path)` → the same object, so a saved detection reopens.
* **GUI**: AutoForm over the shared `image` section with the label overlay and
  markers (`autoform-image-3d` already does overlays and click-picking), the
  region table in a `chitable`, and the shared region list for hand-drawn
  additions.
* **CLI** `spot-finder`, **RPC** `spot_finder.detect.run`, per the plugin
  standard.
* **`guide.json`** and a `?` help page, both required by the project rules —
  with a `demo.py` that generates a field of known spots so the tour can be
  walked without the user's own file.

## 5.2 `microscopy/region_mle` — renamed from `sm_image_mle`

*Display name* `Imaging:Lifetime:Region MLE`. Package, id, CLI (`region-mle`),
RPC namespace, `state_namespace` and entrypoints all renamed. No alias module and
no compatibility shim — the change policy prefers the coherent rename, and the
plugin's own state namespace is the only stateful surface, which a rename simply
resets.

* **Input becomes regions.** `RegionMleSettings` drops every `seg_*` field and
  gains a region source: a container path (read the persisted pair), a label
  image, or a list of ROIs. `fit_molecules` becomes `fit_regions` and **does not
  segment**.
* **The estimator half is untouched** — same `Fit2x`, same `fit_many` batching,
  same IRF/background preparation in `backend/services._build_irf_vv_vh`, same
  `min_photons` sentinel, same VV/VH layout.
* **Photon gathering moves to a named function** — `region_photon_indices(clsm,
  labels)` — because it is the actual seam between the two plugins and is
  currently an inline double loop over `prop.coords`. Written once, it can also
  be made fast: the loop today is per-pixel Python.
* **The GUI keeps the molecule browser** (`image_browser` section, per-region
  decay + fit curve) and loses the segmentation controls, gaining instead a
  region source picker.

## 5.3 What binds them

The **Image Tools** aggregator (`microscopy/imaging_tools`) gains Spot Finder
directly before Region MLE, matching the workflow order the toolbox already
encodes elsewhere (Drift before the per-pixel steps because alignment precedes
measurement). Running Region MLE with no regions available offers to run the
detector — the hand-off is a container path, not a shared object.

# 6. Stages and Definition of Done

* **Stage 1 — the contract.** `write_spots` / `read_spots` + the artifact pair,
  with a round-trip test on a synthetic label field.
  - [ ] A detection written and reopened returns identical labels and an
        identical table, including sentinel rows.
  - [ ] `lineage()` from the region table reaches the primary data.
* **Stage 2 — `spot_finder` core + CLI.** Detection methods on
  `chisurf/core/roi/segmentation.py`, no new algorithms.
  - [ ] On `core/fluorescence/imaging/simulate.py`'s synthetic CLSM field with
        *n* planted molecules, each method recovers *n* regions and their
        centroids to sub-pixel accuracy.
  - [ ] Labels are contiguous from 1 after every filtering step.
* **Stage 3 — the rename and the de-segmentation of the MLE.**
  - [ ] `region_mle` fits a label image it did not produce.
  - [ ] **Equivalence test**: `spot_finder` + `region_mle` on a file produces
        the *same* per-region parameters as today's `sm_image_mle` end-to-end
        run, to the last significant figure. This is the test that says the
        split changed nothing scientific.
  - [ ] No `seg_*` field survives in `RegionMleSettings`.
* **Stage 4 — GUIs.** Both, screenshot-verified headlessly in a realistic state
  per the project rule, with a before/after control inventory against today's
  `sm_image_mle` panel — the migration is a port and the baseline must be
  captured **before** the rename lands.
  - [ ] Every control of the current panel is present in one of the two new
        panels, or listed as a deliberate removal.
* **Stage 5 — docs and tours.** `docs/concepts/spot_detection.md`, a numbered
  guide, `guide.json` + `help.md` for both plugins, catalogue regenerated,
  [imaging](/plugins/imaging.md), [ROI](/subsystems/roi.md) and
  [MLE lifetime fitting](/subsystems/mle-lifetime-fitting.md) updated.

# Related

* [PRD-86](prd-86.md) — the in-tree segmentation core this consumes. The spot
  finder is the first tool whose whole purpose is that module.
* [PRD-88](prd-88.md) — the provenance matrix, which gains the 3-deep
  photons → regions → fits chain.
* [ROI](/subsystems/roi.md) — `regionprops`, the segmentation primitives, and
  the list of consumers this PRD adds to.
* [MLE lifetime fitting](/subsystems/mle-lifetime-fitting.md) — the estimator
  half, deliberately unchanged.
* [burst companions](/subsystems/burst-companions.md) — the merge-by-position
  contract the region table copies.
