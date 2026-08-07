---
type: PRD
prd: "86"
title: "PRD-86: An in-tree segmentation core — Otsu, border-clearing, peak-finding, watershed — closing scikit-image out of ChiSurf's imaging path"
description: chisurf.core.roi already reimplements skimage.measure.regionprops property-for-property, so the "what is this region" half of imaging is dependency-free. The "which pixels are a region" half is not — molecule MLE's actual segmentation pipeline (Gaussian smooth, Otsu threshold, border-clearing, watershed) and colocalization's optional object-splitter both still import scikit-image. This PRD ports the four missing pieces into a new chisurf.core.roi.segmentation module, alongside props.py, tested for parity the same way regionprops already is, so scikit-image can move from a hard dependency to gone.
status: planned
phase: "scoped; not started"
resource: chisurf/core/roi/
tags: [prd, imaging, roi, segmentation, dependencies, microscopy]
timestamp: '2026-08-07T00:00:00Z'
---

# Summary

`chisurf.core.roi.props` already answers "what is this region?" without
scikit-image — `regionprops`/`regionprops_table` mirror
`skimage.measure.regionprops` property-for-property, numbers matched under
test, and both real consumers (`objects.py`, `molecule_mle.py`) already read
one shared property set instead of re-deriving it. What that port did **not**
touch is the other half: **"which pixels are a region"** — turning a raw
intensity image into the label image `regionprops` consumes in the first
place. That half still leans on scikit-image directly, and in one file it is
not optional:

- **`chisurf/plugins/microscopy/sm_image_mle/core/molecule_mle.py`**
  (`segment_molecules`, line 346) is the plugin's actual segmentation step —
  Gaussian-smooth, Otsu-threshold (or a fixed level), clear border-touching
  objects, split touching molecules by a distance-transform watershed seeded
  on local maxima. `from skimage import filters`, `from skimage.feature import
  peak_local_max`, `from skimage.segmentation import clear_border, watershed`
  are imported unconditionally, function-scoped, **no fallback** — the plugin
  cannot segment a single molecule without scikit-image installed.
- **`chisurf/core/fluorescence/imaging/colocalization/objects.py`**
  (`_watershed_split`, line 180) uses the same `peak_local_max`/`watershed`
  pair to split touching objects, but **already** wraps the import in
  `try/except ImportError` and falls back to plain `scipy.ndimage.label`
  (no splitting) when scikit-image is absent — proof this can degrade
  gracefully, and the shape the new module's callers should converge on.

Four algorithms are the actual gap, not the whole of scikit-image: Gaussian
smoothing needs **no port at all** (`scipy.ndimage.gaussian_filter` already
does it, and `objects.py`'s own thresholding path already calls it directly);
Otsu thresholding and border-clearing are small, well-known algorithms; local
maxima and marker-controlled watershed are the real centre of this PRD — real
algorithms, not a page of code, but each a single well-documented classical
method with an in-tree precedent for exactly this kind of port
(`chisurf/plugins/chimol/chimol/geometry/marching_cubes.py`, a self-contained
294-line reimplementation of `skimage.measure.marching_cubes` built for
the same reason: narrowing a codepath's dependencies to what it actually
needs).

# Status

Planned. Scope identified against the two real call sites and the existing
`roi`/`props.py` precedent; no code written yet. This PRD is preliminary —
written to size and scope the work, not to lock every design choice (see
*Design decisions / open questions*).

# Motivation

- **The dependency is declared harder than it is used.** `scikit-image` sits
  in `pyproject.toml`'s main `dependencies` list (not the `full` extra, unlike
  `hdbscan`/`latexify-py`/`notebook`), justified by a comment claiming
  module-scope imports "by the CLSM and single-molecule image tools." Neither
  claim is current: the CLSM plugin's only use was a `skimage.io.imsave` call
  that duplicated the retired `imageio` dependency and has since been removed
  (fixed directly, no port needed — see *Relationships*); every remaining
  import in the tree is function-scoped, not module-scope. The dependency is
  real, but it is exactly two functions deep in two files, not "the imaging
  stack."
- **One of the two real users already shows the target shape.**
  `objects.py::_watershed_split` is the existence proof that this feature
  degrades rather than crashes: `try: from skimage... except ImportError: ...
  return connected components instead`. `molecule_mle.py::segment_molecules`
  has no such fallback and cannot function without the dependency — after this
  PRD, both should call the same in-tree implementation and neither needs the
  `try/except` at all.
- **The regionprops port is the direct precedent, not a hypothetical one.**
  `chisurf/core/roi/props.py` (1273 lines) mirrors `skimage.measure.regionprops`
  signature-for-signature and number-for-number, tested against skimage's own
  output where installed and against closed-form geometry where it is not
  (`test/core/test_regionprops.py`). That is the exact test *shape* this PRD
  reuses for the four new functions — not a new testing philosophy to invent.
- **Dependency-closure impact not yet measured.** Unlike PRD-82's `pdb2pqr`
  finding (a `conda create --dry-run` comparison), scikit-image's own closure
  cost has not been measured for this PRD — it should be, before committing to
  the full port, so the size of the win is known rather than assumed. It is
  used widely enough in the scientific Python ecosystem that it may already
  arrive transitively regardless (unlike `pdb2pqr`, which pinned `pandas` and
  pulled in an HTTP stack no other declared dependency needed); if so, the
  motivation here is architectural (one fewer hard dependency for two small
  algorithms, in-tree numerics under ChiSurf's own test suite) rather than a
  closure-size win, and should be stated as such rather than oversold.

# Scope

## What is actually missing, function by function

| skimage call (current) | Used in | Port needed? | Why |
| --- | --- | --- | --- |
| `filters.gaussian(x, sigma=s)` | `molecule_mle.py:389` | **No** — swap to `scipy.ndimage.gaussian_filter(x, sigma=s)` | Direct equivalent; `objects.py` already calls `ndimage.gaussian_filter` directly for its own thresholding path (line 130) — zero new code, one changed import. |
| `filters.threshold_otsu(x)` | `molecule_mle.py:401` | **Yes — small** | Histogram-based, maximize between-class variance; classical, ~20–30 lines, no ambiguity in the reference algorithm. |
| `segmentation.clear_border(binary)` | `molecule_mle.py:402` | **Yes — small** | Label the binary image, zero any label touching a border row/column; ~15–20 lines on top of `scipy.ndimage.label`, which is already a dependency. |
| `feature.peak_local_max(dist, footprint=..., labels=..., min_distance=..., exclude_border=...)` | `molecule_mle.py:410`, `objects.py:191` | **Yes — moderate** | Local-maxima detection: a maximum-filter equality test for footprint-based candidates, then (when `min_distance` rather than `footprint` drives the call) greedy non-max suppression by distance. Both call shapes in this tree must be covered — `objects.py` passes `min_distance`+`labels`+`exclude_border`, `molecule_mle.py` passes `footprint`+`labels`. |
| `segmentation.watershed(-dist, markers, mask=binary)` | `molecule_mle.py:412`, `objects.py:198` | **Yes — the centrepiece** | Marker-controlled watershed by priority-flood (Vincent–Soille immersion): grow labelled regions outward from `markers` along the `-distance` surface, bounded by `mask`. The real algorithmic work in this PRD; both call sites use it identically (negated distance transform, boolean mask, integer markers), so one implementation covers both. |

## Where it lives

New module **`chisurf/core/roi/segmentation.py`**, a sibling of `props.py`,
`builders.py`, `collection.py`, `io.py` — the natural next stage in the chain
the `roi` subsystem already documents (geometry → mask → **segmentation** →
properties), not a new top-level package. `chisurf/core/roi/roi.py` already
has the other end of this bridge (`labels_to_rois`/`rois_to_labels`, line
1074/1126: label image ↔ list of regions); this PRD supplies what produces
the label image in the first place, for the two callers that still need
scikit-image to get one.

Proposed surface, matching the call shapes actually used (not the full
`skimage` signatures):

```python
def threshold_otsu(image: np.ndarray, *, mask: np.ndarray | None = None) -> float: ...
def clear_border(binary: np.ndarray) -> np.ndarray: ...
def peak_local_max(
    image: np.ndarray, *,
    min_distance: int = 1,
    footprint: np.ndarray | None = None,
    labels: np.ndarray | None = None,
    exclude_border: bool | int = True,
) -> np.ndarray:  # (N, ndim) coordinates, matching skimage's return shape
    ...
def watershed(image: np.ndarray, markers: np.ndarray, *, mask: np.ndarray | None = None) -> np.ndarray: ...
```

## Migration

1. Implement and parity-test the four functions (see *Acceptance*).
2. `objects.py::_watershed_split` drops its `try/except ImportError` entirely
   — the in-tree functions are always available, matching how `props.py`
   already made `regionprops` unconditional for the same two files.
3. `molecule_mle.py::segment_molecules` switches its four imports to
   `chisurf.core.roi.segmentation` and `scipy.ndimage.gaussian_filter`.
4. Once no import of `skimage` remains anywhere in `chisurf/` (verify with the
   same repo-wide grep this investigation used), move `scikit-image` out of
   `pyproject.toml`'s main `dependencies` — dropped outright if nothing else
   needs it, or into the `full` extra if a case for keeping it optional
   surfaces during implementation — and add it to `RETIRED` in
   `test/test_no_retired_dependency_imports.py` so a regression is caught the
   same way `imageio`/`tifffile` already are.
5. Regenerate `pixi.lock` (`pixi lock`) once the dependency is actually
   removed, mirroring the `pdb2pqr` removal's second commit.

# Reuse

- **`chisurf/core/roi/props.py`** — the direct precedent for both the parity
  contract (same signature, same numbers, tested against the real
  implementation) and the module's internal style; read before writing the
  new functions, not alongside them.
- **`test/core/test_regionprops.py`** — the exact test *shape* to copy:
  `skimage_measure = pytest.importorskip("skimage.measure", reason=...)`,
  then assert the in-tree function's output against skimage's for the same
  synthetic input. Four new parity test files (or one shared module) follow
  the same pattern for `threshold_otsu`/`clear_border`/`peak_local_max`/
  `watershed`.
- **`chisurf/plugins/chimol/chimol/geometry/marching_cubes.py`** — the
  precedent for the *engineering* shape of an in-tree port of a scikit-image
  algorithm: NumPy core, optional numba acceleration, output convention
  documented against the original so downstream code "keeps working
  unchanged." Watershed's numba-or-not decision should follow this file's
  reasoning rather than reopening it.
- **`scipy.ndimage`** — already a hard dependency; `label`,
  `distance_transform_edt`, `gaussian_filter`, `maximum_filter` are the
  primitives the new functions are built from, not new dependencies.
- **`okf/subsystems/roi.md`** — the owning subsystem doc; update its
  "Measuring a region" / consumer sections once this lands, the same way it
  already documents `props.py` superseding per-consumer `regionprops`/
  `scipy.ndimage` reductions.
- A scikit-image source checkout under `junk/` (none exists yet) is the
  reference to read during implementation, per
  [reference-checkouts](../workflows/reference-checkouts.md) — specifically
  `skimage/filters/thresholding.py` (Otsu), `skimage/segmentation/
  _clear_border.py`, `skimage/feature/peak.py`, and `skimage/segmentation/
  _watershed.py` — annotated with `CHISURF-REVIEWED`/`CHISURF-TAKEN`/
  `CHISURF-SKIPPED` headers as it is mined, exactly as other reference
  implementations in that folder already are.

# Design decisions / open questions

- **How exact does watershed parity need to be?** Classical watershed has
  tie-breaking ambiguity between equal-priority pixels; skimage's compiled
  implementation resolves ties by insertion order into its priority queue.
  Neither real consumer inspects label *identity* (both feed the output
  straight into `regionprops`/`labels_to_rois`, which care about region
  *shape and count*, not which integer a given blob is assigned) — so exact
  label-for-label parity is probably not the right bar. The parity tests
  should assert on **region masks** (via `regionprops` or a mask-equality
  check up to label permutation), not on raw label arrays, and this should be
  decided before writing the watershed kernel, not after finding a mismatch.
- **Module location.** `chisurf/core/roi/segmentation.py` (proposed above) vs.
  a new top-level `chisurf/core/imaging/` package. The `roi` subsystem doc
  already frames segmentation as the missing link in its own
  geometry→mask→properties chain and already owns the label-image bridge
  (`labels_to_rois`), which argues for keeping it there; a case for a
  separate package would be if segmentation is expected to grow well beyond
  these four functions (e.g. a broader "basic image processing" home), which
  is not currently in view.
- **numba now or later.** `marching_cubes.py` accelerates its per-cell kernel
  with an optional numba path and a NumPy fallback. Both real consumers here
  segment single frames sized for interactive analysis (a CLSM field, a
  single-molecule frame), not stacks — profile watershed's plain-NumPy cost
  on a representative image before deciding whether numba is warranted, per
  the general "don't add abstractions beyond what the task requires" rule;
  this PRD does not assume the answer.
- **Hard cutover vs. a transition period.** Whether to keep `scikit-image`
  importable-but-unused for one release (in case an external plugin outside
  this tree imports it through ChiSurf) or cut over the moment parity tests
  pass. Given both real usages are internal (`chisurf/plugins/...`,
  `chisurf/core/...`), a hard cutover in the same change that lands the port
  is the default position; state a reason here if that changes.
- **Does `peak_local_max`'s `exclude_border` need its full generality?**
  skimage's version accepts a bool or a per-axis tuple; both call sites in
  this tree pass a single bool (`False` in `objects.py`, the default `True`
  in `molecule_mle.py` via omission). Scope the port to what is called with
  unless a third caller with different needs appears.

# Acceptance

- Headless, mirroring `test/core/test_regionprops.py`'s pattern exactly:
  `pytest.importorskip("skimage...")`-guarded parity tests for each of the
  four functions, on synthetic images (a few Gaussian blobs, at least one pair
  close enough to require splitting) — asserting agreement with skimage's
  same-named function to the precision decided under *watershed parity*
  above.
- `objects.py::_watershed_split` and `molecule_mle.py::segment_molecules`
  produce region counts, areas and centroids (via `regionprops`) matching
  their current scikit-image-backed behaviour on the existing plugin test
  fixtures, with scikit-image **uninstalled** in that test run (or monkeypatch
  `sys.modules["skimage"]` to `None` to prove the code path no longer reaches
  for it).
- `objects.py`'s `try/except ImportError` around the watershed import is
  gone; the module imports `chisurf.core.roi.segmentation` unconditionally.
- A repo-wide grep for `skimage` under `chisurf/` (module-level or
  function-scoped) returns nothing outside test files that explicitly
  `importorskip` it for parity checking.
- `pyproject.toml` no longer declares `scikit-image` (or it is moved to the
  `full` extra with a stated reason — see open questions), `pixi.toml` matches,
  `pixi.lock` is regenerated (`pixi lock --check` passes), and
  `test/test_declared_dependencies.py` / `test/test_no_retired_dependency_imports.py`
  are updated accordingly.

# Non-goals

- Reimplementing any other part of scikit-image. This PRD is scoped to the
  four functions actually called in this tree, not a general-purpose
  image-processing library.
- Changing `molecule_mle.py`'s or `objects.py`'s segmentation *parameters* or
  *behaviour* beyond what porting requires — this is a dependency port, not a
  segmentation-quality improvement.
- Revisiting `regionprops`/`regionprops_table` (`props.py`) — already done,
  already tested, out of scope here except as the precedent to follow.
- The CLSM plugin's `skimage.io.imsave` usage — already fixed directly (no
  port needed; see *Relationships*), unrelated to the segmentation gap this
  PRD closes.
- Adding scikit-image-equivalent functions nobody in this tree calls (e.g.
  other `skimage.segmentation`/`skimage.feature` algorithms), even if they
  would be natural extensions of this module later.

# Relationships

- Direct sibling of the completed `regionprops` port
  ([roi](/subsystems/roi.md), `chisurf/core/roi/props.py`) — this PRD is the
  other half of the same "stop depending on scikit-image for standard image
  analysis" effort, deliberately scoped and tested the same way.
- Same *pattern* as [PRD-80](prd-80.md) (retire mdtraj) and the `pdb2pqr`
  removal recorded in `okf/log.md` (2026-08-07): shell out to nothing, own the
  numerics, prove parity, then drop the dependency — but explicitly **not**
  the same *size*: `pdb2pqr` needed one geometrically-determined atom
  position; this PRD's centrepiece (watershed) is a real classical algorithm,
  closer in effort to the `marching_cubes.py` port than to the `pdb2pqr` fix.
  State this difference plainly so the port is not underscoped by analogy.
- Precedent engineering shape from
  `chisurf/plugins/chimol/chimol/geometry/marching_cubes.py` (self-contained
  `skimage.measure.marching_cubes` reimplementation, NumPy + optional numba).
- Fixed in the same investigation that scoped this PRD, no port required:
  `chisurf/plugins/microscopy/clsm/api/clsm.py`'s `import skimage as ski;
  ski.io.imsave(...)` — routed the retired `imageio` dependency around the
  existing guard (`test_no_module_imports_skimage_io`) via an aliased import;
  replaced with `chisurf.core.fio.image.imwrite` for TIFF and Pillow for
  preview formats.
