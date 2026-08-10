---
type: PRD
prd: "92"
title: "PRD-92: Spot finding is not lifetime fitting — a region-property MLE fed by a spot finder that persists its regions"
description: sm_image_mle segments, measures, gathers photons and fits inside one 897-line core, and fit_molecules re-runs the segmentation itself, so the regions cannot be inspected, corrected, reused or produced by anything else. Split it — a spot-finder plugin that detects spots and writes region properties into the .pto container, and a region-property MLE that reads them. The seam is the container, not a function call; the load-bearing question is that a region table of scalars cannot say which photons belong to a region; and both halves are batch tools, so the two batch loops that exist today (with different persistence, and a `continue` for every failure) become one Qt-free runner with a run table that has a row per input whatever happened to it.
status: in-progress
phase: "stages 1-3 landed (contract; spot_finder + workflows; rename to region_mle and the fit no longer segments, equivalence proven); batch for the MLE half, docs open"
resource: chisurf/plugins/microscopy/sm_image_mle/
tags: [prd, imaging, roi, mle, spot-detection, pto, provenance, plugins, microscopy]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

Stages 1–3 have landed: the container contract, the `spot_finder` plugin
(core, JSON workflows, batch runner, CLI, RPC — no GUI of its own yet), and the
rename of `sm_image_mle` to `region_mle` with its segmentation removed. **The
coupling this PRD exists to break is broken**: `fit_regions` resolves the
regions it is handed and finds none of its own. What remains is the batch half
for the MLE side, the spot finder's GUI, and docs.

1. ~~**Settle the pixel-membership question first (§3).**~~ **Settled and
   landed (2026-08-10):** option B, the raster/table pair, in
   `chisurf/core/fio/fluorescence/region_container.py`
   (`write_regions` / `read_regions` / `region_table` / `list_region_sets`),
   with `test/fio/test_region_container.py` (12 tests). A region table of
   scalars is **not enough to fit** — the MLE reaches a molecule's photons
   through `prop.coords` → `clsm[0][r][c].tttr_indices`, one pixel at a time —
   so the pixels travel as an `image_data` label raster keyed by the table's
   `label` column. Two things found while landing it:
   `imaging_container.write_image` **had no reader at all** (three plugins were
   writing rasters into containers nothing could read back through the module),
   so `read_image` was added beside it; and the vocabulary is the dictionary's,
   not the caller's — `region_table`, `region_detection` and the `region` grain
   were added to `mmfdb_flr_ext.dic`, and `radians`/`pixels` were already there
   under those spellings (`rad` is not a term).
2. **Then the container contract (§4), before either plugin is written.** The
   burst side learned this the expensive way: a companion format that merges by
   position fails *silently* when a row is missing rather than absent
   ([burst companions](/subsystems/burst-companions.md)). A region table has
   the same shape and needs the same rule — one row per detected region
   including the ones the fit skipped.
3. ~~**The rename and the de-segmentation of the MLE (§5.2).**~~ **Landed
   (2026-08-10)**, and the equivalence is *proven*, not asserted: the baseline
   was captured before the change (`region_mle/test/data/` — the intensity
   image, the labels the old watershed produced, the per-region VV/VH
   histograms and the parameters the estimator returned), because the code that
   produced it is deleted by the change the test exists to check, and the
   simulator is unseeded so it cannot be recaptured. `test_equivalence.py`
   compares against it: the spot finder's standard workflow reproduces the old
   segmentation **pixel for pixel**, and the estimator returns the same
   parameters from the same histograms. The rename is not cosmetic (§5): "Molecule-wise
   MLE" names the *sample* the tool was written for; the tool fits whatever
   regions it is handed, and after the split it will be handed regions from a
   detector it does not know about. Doing the rename first means the split is
   written against the final names.
4. **Batch is a stage of its own, not a loop around the new cores (§6).** Read
   §6's inventory before touching it: there are *two* batch loops today with
   different persistence (the GUI one writes no container), every failure mode
   is a `continue` that shortens the result silently, and the IRF is rebuilt
   once per file from the same measurement. Replacing the loop without fixing
   those reproduces them in two plugins instead of one.
5. **Reuse, do not re-derive, the estimator half (§5.2).** `Fit2x` /
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
* **Otsu's level is set by the whole histogram, and both tails move it.**
  Found twice while writing stage 2's tests, in opposite directions: a single
  900-valued hot pixel beside a 200-valued spot puts the level *above the
  spot*, so the frame's only detection is the defect; and a *large* bright
  patch elsewhere pulls the level up past the dim objects one actually wants.
  Neither fails — both return a plausible number of plausible regions — which
  is why a fixed level is the honest choice whenever the frame holds anything
  much brighter than the objects being counted.
* **A one-valued frame is an ordinary input and `threshold_otsu` raises on it**
  ("no two classes to separate"). A blank tile, a field the sample missed, one
  entry in a batch. Both `spot_finder` and the existing `segment_molecules`
  now return no regions instead — in the old code the exception reached the
  batch loop's `continue` and the file simply left the result set, which is
  precisely the silent-shortening this PRD is about.

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
* **Both stages batch, and batch separately** (§6) — detect over a hundred
  fields, review what was found, then fit — through *one* runner shared by the
  GUI, the CLI and the RPC service, where today there are two loops that persist
  different things.
* No change to the estimator. The 2I\* / `Fit23` path, the VV/VH assembly and
  the IRF preparation stay as they are.

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

Written through the seam the plugin already uses —
`chisurf/core/fio/fluorescence/imaging_container.py::write_imaging_table`, which
takes `artifact_kind` / `operation_type` / `row_grain` and, crucially,
`derived_from` plus `source_row_column` / `target_row_column`. So no new writer
is needed, and the fit table's rows can be linked to the region table's rows by
`label` rather than by position:

```
artifact_kind  = "region_table"     (scalars)  /  "image_data"  (label raster)
operation_type = "region_detection"
row_grain      = "region"
```

These are dictionary terms, added to `mmfdb_flr_ext.dic` rather than invented at
the call site — the container refuses a term the profile does not carry, which
is how the wrong spelling is caught at the write rather than in a reader six
months later. **`region` is not `spot`**, which the enumeration already had: a
spot is a point-like detection with a position and at most a width; a region is
an arbitrary connected set of pixels that owns its own pixel list. Declaring a
table of cell nuclei at `spot` grain is a false statement about its rows, in the
one field a reader consults to decide what may be joined to it — the same shape
of error as calling a file of binned traces a photon stream.

Rules, mirroring [burst companions](/subsystems/burst-companions.md) because the
failure mode is identical:

* **One row per detected region, including regions the fit skipped.** A region
  below `min_photons` gets a sentinel row (NaN parameters), never a missing row.
  Anything that later merges a fit result against this table merges by position
  unless it is given a key — and `write_imaging_table`'s
  `source_row_column="label"` / `target_row_column="label"` is that key, so use
  it and the position rule becomes a belt rather than the only brace.
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

  **A blob detector answers "where and how wide", not "which pixels", and the
  contract needs pixels.** So `log`/`dog` spots are rasterised into discs of
  radius `sqrt(2) * sigma` — the width the detector *measured*, at the scale
  where the spot responded most strongly, rather than one fixed in advance —
  and the sigma travels with the region as a `spot.sigma` column. Overlapping
  discs are arbitrated by distance, so a contested pixel goes to the nearer
  centre: painting discs in detection order instead would give the last one
  written, which is an answer that depends on detection order rather than on
  geometry, and no pixel's photons may be counted for two regions.
* **Persistence**: `write_spots(container, result, settings)` → the artifact pair
  of §4. `read_spots(path)` → the same object, so a saved detection reopens.
* **GUI**: AutoForm over the shared `image` section with the label overlay and
  markers (`autoform-image-3d` already does overlays and click-picking), the
  region table in a `chitable`, and the shared region list for hand-drawn
  additions.
* **CLI** `spot-finder`, **RPC** `spot_finder.detect.run`, per the plugin
  standard.
* **Workflows are JSON documents, and the standard one is single-molecule
  segmentation** (§5.4). A detection is a recipe, and a recipe that exists only
  as a command line cannot be versioned, shared, reviewed or attached to a
  result.
* **`guide.json`** and a `?` help page, both required by the project rules —
  with a `demo.py` that generates a field of known spots so the tour can be
  walked without the user's own file.

## 5.4 Workflows — the run as a document

A detection is a recipe: which detector, at what threshold, over which files,
written under which name. A recipe that exists only as a command line cannot be
versioned, shared, reviewed, or attached to the result it produced — so the same
run can be written down, and `spot-finder run recipe.json` is the same operation
as `spot-finder detect`.

```json
{
  "workflow": "single_molecule",
  "settings": {"min_area": 4},
  "inputs": {"files": ["field_01.ptu"]}
}
```

Four decisions, each of which is the interesting half:

* **The standard workflow is `single_molecule`, and it is the default.** Not a
  neutral one: the shipped document is the watershed pipeline the molecule-wise
  MLE has always segmented with, so a detection made here and fitted downstream
  reproduces what the combined tool did. That is what makes the equivalence test
  in stage 3 a fair comparison rather than a coincidence.
* **The dataclass defaults *are* that document**, and a test asserts it field by
  field. Otherwise `spot-finder detect` and `single_molecule.json` are two
  answers to the same question, and the drift between them is invisible.
* **A document names a base and overrides only what differs.** A user's file is
  short and says what is unusual about their sample rather than restating twelve
  defaults it does not care about.
* **An unknown key is refused — in the document, in the settings, and over
  RPC.** A file carrying `min_size` where the setting is `min_area` must fail
  loudly, because the alternative is the worst outcome available: the run
  succeeds, at the default, and records a parameter that never took effect. The
  same rule makes `--workflow` mean something on the command line: an option the
  user did not type does not override the workflow's value (Click's parameter
  source, not the option's default, decides).

Shipped: `single_molecule` (the standard), `camera_spots` (a LoG scale space,
for widefield spots of unknown width, `min_area` 2 to reject hot pixels), and
`objects` (connected components, no splitting — a watershed can only over-split
an object nothing is touching). `spot-finder workflows` lists them, `show`
prints one to start from, and `detect --save-workflow` turns a tuned run into a
document that reruns identically.

The **cross-plugin** sense of the word is served too: `spot_finder.workflow.prepare`
takes the `workflow_context` the burst tools already pass (`raw_files`,
`channel_settings`) and returns the request it would run, without running it —
so the detector inherits the channels an earlier step settled on instead of
re-deriving a second answer to a question already answered.

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

# 6. Batch — the half that is not a for-loop

Both plugins are batch tools. Neither is a batch tool *by accident*: a field of
molecules is one measurement, an experiment is a hundred of them, and the whole
point of persisting the regions is that the two stages can be batched
**separately** — detect over a hundred fields, look at what was found, then fit.
That is impossible today, because detection is not a thing that can be run on
its own.

What is there now is worth reading before writing the replacement, because it is
not one loop:

* **There are two batch implementations with different behaviour.**
  `api/molecule_mle.py::analyze_request` loops over `request.files` and is what
  the CLI and the RPC service call. `gui/view_model.py::run()` loops over
  `self.files` and is what the GUI calls. They are not the same: the API path
  writes the result into the measurement's container via `write_imaging_table`;
  the GUI path writes `<stem>_analysis/molecule_data.tsv` + `intensity.npy` and
  **never writes the container at all**. So whether a batch leaves provenance
  behind depends on which surface the user ran it from, and nothing says so.
* **Every failure mode is a `continue`.** A file that raised, and a file that
  segmented zero molecules, are both dropped from the result — the joint table
  is simply shorter. The GUI path is worse: it overwrites `status_text` per
  failure, so a batch of a hundred files with ninety failures shows the
  *ninetieth* reason and no count. This is the same silent-shortening family as
  the burst-companion rule, one level up: **a missing row that should have been
  a sentinel row.**
* **The joint table's location depends on the order of the file list.** With no
  `output_dir`, `joint_output.tsv` is written next to `request.files[0]`.
* **The joint table keys measurements by a string path.** `with_source_column`
  puts `source_ptu` first, and `load_analysis` splits a joint TSV back up by
  that column — so the identity of a measurement in a batch is a file path that
  is stale the moment anything is moved.
* **Shared work is repeated per file.** Each iteration does
  `dataclasses.replace(request.settings)` from the original settings, whose
  `irf` is `None`, so `build_irf_vv_vh` **and** `compute_g_factor` re-run for
  every file from the same IRF measurement with the same window. The comment
  explains the copy (do not carry an IRF across files with different windows) —
  correct in the general case, and the window is a *setting*, identical across
  the batch, so N identical IRF builds is the normal case.
* **No parallelism and no cancel.** Files are independent and the loop is
  serial; `manifest.json` declares `long_running: true, cancelable: false`,
  which for a hundred-field batch means the only way to stop is to kill the
  process.

## 6.1 What the split should do about it

* **One batch runner, Qt-free, in the core** — `core/batch.py`, used by the GUI,
  the CLI and the RPC service alike. The GUI's job is a progress bar and a
  cancel button, not a second loop with different persistence. This is also what
  makes batch behaviour headlessly testable, which the view-model loop is not.
* **A batch returns a run table: one row per input, always.** Columns
  `input`, `measurement_uid`, `status` (`ok` / `empty` / `failed` / `skipped`),
  `n_regions`, `n_fitted`, `reason`. A file that failed is a row, a file with
  zero spots is a row saying zero. `len(run_table) == len(inputs)` is an
  invariant, and it is the batch-level restatement of the sentinel-row rule.
  The run table is itself written into… nothing — it is per-batch, not per
  measurement, so it is returned and, when the caller asked for a folder,
  written there.
* **Results go into each measurement's own container**, one file per
  measurement, per the `.pto` rule. A batch does not have an output file; it has
  N outputs, each beside its own data.
* **A cross-measurement table is a derived view, not a format.**
  `read_regions(paths)` / `read_fits(paths)` concatenate N containers into one
  table with a leading `measurement_uid` (the container's own identity) plus
  `label`, and `source` kept as a *convenience* column rather than the key. That
  is what feeds population-level plots, and it is rebuilt from the containers
  rather than being a file that can go stale.
* **The two stages batch independently, over different inputs.** Stage A's
  inputs are measurements; stage B's inputs are *region tables*. So a fit batch
  can mix fields whose spots were found with different detectors or settings —
  legal, useful (a field that needed a lower threshold does not force the whole
  experiment onto it), and recorded, because each fit artifact names the
  detection artifact it consumed via `derived_from`.
* **Shared preparation is computed once per batch.** The IRF VV/VH histogram,
  the background and the G-factor are a function of
  `(irf_file, micro_time_range, micro_time_binning, shifts,
  irf_threshold_fraction)`; build them once per distinct key and reuse. The
  per-file copy stays — the bug it prevents is real — but it copies a *prepared*
  IRF instead of rebuilding one.
* **Parallel over inputs, with cancel and per-file progress.** Files are
  independent; `chisurf/core/fluorescence/mle/parallel.py` already threads the
  fit itself, and the outer loop threads over files (the inner batch fit releases
  the GIL in C++). `cancelable` becomes `true` in both manifests, and progress is
  `(index, n_inputs, current_name)` rather than a status string that the next
  file overwrites.

## 6.2 Batch in the GUIs

Both panels take a `path_list` of inputs (the shared AutoForm section, which is
already how every file list in the tree works) and show the run table as a
`chitable` with the failures visible rather than counted. The spot finder's
batch is "detect over this list and let me look at the run table before I
commit"; the region MLE's batch is "fit everything that was detected". Neither
GUI writes its own persistence path.

# 7. Stages and Definition of Done

* **Stage 1 — the contract. ✅ done (2026-08-10).**
  `chisurf/core/fio/fluorescence/region_container.py` +
  `test/fio/test_region_container.py` (12 tests); the functions are
  `write_regions` / `read_regions` rather than `write_spots` / `read_spots`,
  because the contract is the general one and only the *plugin* is about spots.
  - [x] A detection written and reopened returns identical labels and an
        identical table, including sentinel rows.
  - [x] `lineage()` from the region table reaches the primary data — asserted on
        the primary's uid, not merely on the raster being in the chain.
  - [x] Label gaps cannot reach the file: `write_regions` relabels
        sequentially, so a filtering step that deletes labels cannot leave rows
        that own no pixel.
  - [x] A table whose raster is missing is refused, naming what the container
        does hold; `list_region_sets` lists only complete pairs.
  - [x] The raster comes back integer-valued — a label image is not a picture.
  - [x] Beyond the DoD: the intensity columns are *absent* rather than zero when
        a detection was made on a mask, and an `extra` column of the wrong
        length is refused rather than recycled.
* **Stage 2 — `spot_finder` core + CLI. ✅ done (2026-08-10).**
  `chisurf/plugins/microscopy/spot_finder/` — `core/spots.py` (four detectors on
  the in-tree primitives, no new algorithms), `api/` (settings, request, run
  table, the batch loop), `backend/services.py`, `cli/main.py` (`spot-finder
  detect | list | contract`), `manifest.json`. 35 tests in `test/`.
  - [x] Each detector recovers the planted spots, centroids within 1 px.
  - [x] Labels are contiguous from 1 after every filtering step.
  - [x] `min_area` rejects the hot pixel a threshold admits; `max_area` rejects
        the aggregate that dominates a brightness histogram; `clear_border`
        drops the partly-imaged object.
  - [x] The blob detectors report the **width** they measured, and it separates
        a narrow spot from a broad one.
  - [x] A confined search computes its threshold from the region's own pixels.
  - [x] JSON workflows (§5.4): three shipped documents with `single_molecule`
        as the standard and the default, `run` / `workflows` / `show` /
        `--save-workflow`, `workflow.list` + `workflow.prepare` RPC, and a test
        that the dataclass defaults *are* the standard document field by field.
  - [x] Beyond the DoD: the batch half of §6 landed here rather than waiting —
        one loop behind the CLI and the RPC service, a run table with one row
        per input whatever happened to it, cancel, and a dry run. What remains
        of stage 4 is the *region MLE* half and making both plugins share the
        one runner.
* **Stage 3 — the rename and the de-segmentation of the MLE. ✅ done (2026-08-10).**
  - [x] `region_mle` fits a label image it did not produce — `resolve_labels`
        takes a container, an array, or regions, and **raises** (naming the spot
        finder) when given none, because an empty result would be the same
        silence in a new place.
  - [x] **Equivalence proven against a captured baseline**: the standard
        workflow reproduces the old segmentation pixel for pixel, and the
        estimator reproduces its parameters from the same histograms.
  - [x] No `seg_*` field survives in `RegionMleSettings`; a test asserts it.
  - [x] `region_photon_indices(clsm, labels)` is the named seam, and it walks
        the occupied pixels once instead of re-walking the frame per region.
  - [x] The preview and the fit resolve regions through the *same call*, so
        "what is previewed is what is fitted" is structural rather than a
        promise two code paths make separately.
* **Stage 4 — batch (§6).** One Qt-free runner in the core, replacing both
  existing loops.
  - [ ] `len(run_table) == len(inputs)` on a batch containing a file that
        raises, a file with zero spots and a file that fits — three rows, three
        statuses, nothing dropped.
  - [ ] The GUI, the CLI and the RPC service produce byte-identical container
        artifacts from the same input list (today the GUI writes none).
  - [ ] The IRF is prepared once for a batch of *n* files sharing one IRF
        measurement and one window — asserted by counting `build_irf_vv_vh`
        calls, not by timing.
  - [ ] A detection batch and a fit batch run as two separate invocations over
        the same file set, with the fit consuming what the detection wrote.
  - [ ] A fit batch over region tables produced with *different* detection
        settings succeeds, and each fit artifact's `derived_from` names the
        detection it used.
  - [ ] Cancelling a batch mid-run leaves every already-finished measurement's
        container complete and the run table marking the rest `skipped`.
* **Stage 5 — GUIs.** Both, screenshot-verified headlessly in a realistic state
  per the project rule, with a before/after control inventory against today's
  `sm_image_mle` panel — the migration is a port and the baseline must be
  captured **before** the rename lands.
  - [ ] Every control of the current panel is present in one of the two new
        panels, or listed as a deliberate removal.
* **Stage 6 — docs and tours.** `docs/concepts/spot_detection.md`, a numbered
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
