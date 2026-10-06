---
type: Subsystem
title: Retiring scipy from the runtime dependencies
description: Why scipy is leaving the shipped package, the five routes a call can take out of it, what already ships in tttrlib/bff, and the shrinking allow-list that tracks it.
resource: test/scipy_import_allowlist.txt
tags: [core, dependencies, performance, scipy, wasm, seam]
timestamp: '2026-10-05T00:00:00Z'
---

# Where to pick this up

**Route 3 (bff) status, 2026-10-06 (T-20261005-BFFNUM).** This route struck 5 + 6 files (69 -> 64, then minimize -6).
1. **Landed:** `bff.nnls` / `bff.bvls` (imp.bff `b0882780d`,
   `include/LinearLeastSquares.h`; incremental thin QR, parity with scipy 1.18 to
   round-off on 300 problems incl. rank-deficient and cond~1e8; 1-2x scipy speed).
   chisurf shim `chisurf/core/math/numerics.py` serves `nnls`, `lsq_linear`
   (BVLS, scipy result fields), and every nnls/lsq_linear caller is routed
   (inversion, decay, decay_fit, general, titration, fcs_filter_calculator,
   audifier lifetime_analysis, img_pixel_phasor). Test: `test/core/test_numerics_shim.py`.
2. **Landed:** `FitResidualFunction` + `FitMinimizer::set_residual_function`
   (imp.bff `9d862174e`; the `directorout` typemap reads the residual ndarray
   through its buffer).
   The chisurf shim's `least_squares` / `curve_fit` already use it (parity with
   scipy: x 1e-4 rel, pcov 2%); **no call site is routed to them yet** -- that is
   the next step (~25 files: roi/picking, ics precision/calibration, pch,
   frap, tracking, irf_bg, saturation, titration, flc_2d, psf, ndxplorer
   curve_fit, decay_fit). Measure: 1000-point exponential fit 5.0 ms vs scipy
   1.5 ms -- callback overhead per evaluation, not iteration count (29 vs ~28).
3. **Known difference:** with a parameter pinned at its bound, the relative ftol
   stop fires while free parameters are still ~1e-5 off (MINPACK + leastsqbound
   transform, as chisurf's own fitter always behaved; scipy's trf lands exactly).
4. **Landed 2026-10-06 (T-20261006-BFFOPT): bounded scalar `minimize`.**
   imp.bff `e64ba81b5`: `bff.minimize_lbfgsb` runs SciPy's own C translation
   of L-BFGS-B 3.0 (`src/internal/Lbfgsb.cpp`, BSD, BLAS/LAPACK subset
   in-file) driven as `_lbfgsb_py` drives it; `bff.minimize_nelder_mead` is
   `_minimize_neldermead` step for step. The shim's `minimize` adds scipy's
   argument forms (bounds pairs with None / `Bounds`, `tol`, jac bool or
   callable) and its fixed-variable removal (only when differencing -- scipy
   has made `jac=True` a callable by then). All seven callers routed
   (burst background, gopich_szabo, irf_estimation, flc_2d minimize_q /
   global_mem / mem_1d / mem_2d); six left the allow-list. Parity: Nelder-Mead
   bit-identical to scipy (x, simplex, nit, nfev); L-BFGS-B identical counts
   and x to 1e-10 with a gradient or active bounds -- unbounded with a
   difference gradient scipy's BLAS dot-product order drifts the path an ulp
   and both land equally close. A/B over the callers' own suites (every call
   run through both): gopich_szabo identical; background / irf 1e-6 in x, bff
   equal-or-lower f, fewer evaluations, faster (7 vs 22 ms, 26 vs 44 ms).
   **Trap -- do not read a flc_2d global/2D-MEM difference as a defect:**
   those callers stop at `maxiter` far from convergence, and scipy itself
   moves 440 -> 568 in f when x0 is nudged by one ulp (recorded in
   known-issues). Tests: imp.bff `test/numerics/test_minimize.py` (21),
   chisurf `test/core/test_numerics_minimize.py` (9).
   **Pending (route 3):** `leastsq`/`_minpack` (leastsqbound) and `odeint`
   (reaction/continuous) -- T-20261006-BFFOPT; special functions +
   distributions, expm, pinvh -- the special-functions lane. **Boost.Math is
   already a header-only bff dependency** (SpecialFunctions.cpp uses it).
5. Trap: imp.bff builds share `cmake-build-arm64` with other agents -- wrap
   every ninja in `until mkdir /tmp/imp-bff-build.lock ...; rmdir` and re-run
   `cmake $B` after adding a header/.i (the build tree symlinks them at configure).


**Route 5 (legacy-io) superseded and landed 2026-10-06** (tttrlib `efc9d9c41`,
T-20261006-MATIO): the owner's "scipy leaves" overrides the planned
`chisurf[legacy-io]` extra. MAT-files are curve I/O, so they went to tttrlib:
module `io_mat` (`modules/io/mat/`, own inflate/deflate -- no zlib dependency)
and `tttrlib.matfile.loadmat` / `savemat` / `whosmat`, identical to scipy.io
1.18 under every loader option (tttrlib `test/python/misc/test_matfile_parity.py`,
82 tests; real MATLAB + Octave fixtures in tttrlib `test/data/matfile/`).
china.py, ries_mat.py (`MatStruct` replaces `mat_struct`) and burst_ebfret/io.py
are routed and A/B-identical to their HEAD scipy versions (china on both
fixtures, Ries on a nested `g` struct, ebfret load/save session + SMD both
directions); allow-list 51 -> 48. Left from route 5: nothing. Trap: scipy keeps
a big-endian file's byte order in the dtype (`>f8`, also under `mat_dtype`),
and `squeeze_me` turns every 0-d non-record result into a Python scalar
(strings included) -- the module reproduces both; don't "fix" them.

**Route 4 (tttrlib) landed 2026-10-05** (tttrlib `fb2ad5fe7`, T-20261005-TTTRIMG):
`tttrlib.ndimage` (scipy.ndimage's names, signatures and dtype rules over the
`NdImage.h` ports), `tttrlib.linear_sum_assignment`, `tttrlib.linkage` /
`fcluster` / `inconsistent`, `tttrlib.ConvexHull2D`, `tttrlib.pdist`, and
`KDTree.query` / `.query_ball_point` / `.query_pairs`. Bit-identical to scipy
1.18.0 in tttrlib's `test/python/misc/test_ndimage_parity.py` (74 tests, exact
equality incl. dtype). Every route-4 call site in chisurf and ndxplorer is
routed; 13 allow-list lines struck (64 -> 51). Left from route 4: nothing.
Traps for whoever continues:
- **FMA contraction is part of identity.** `NdImage.cpp` pins
  `#pragma STDC FP_CONTRACT ON` because scipy's wheels are built with
  clang's default; with it off 162 of 582 cases were 1-8 ulp out. Do not
  copy Cluster.cpp's OFF pragma over it.
- **The arm64 env has a stale scikit-build editable redirect.** To test a
  staged tttrlib build, drop `ScikitBuildRedirectingFinder` from
  `sys.meta_path` before importing, or `PYTHONPATH` is silently ignored.
- `modules/ndxplorer/ndxplorer/utils/mask_helpers.py` sat under the tttrlib
  heading but only uses `scipy.stats.norm.cdf` -- it is route 2 (local erf).

The remaining work is issued as board tickets, not prose here. Each ticket
names its interface and its parity-test obligation so it can be picked up
without re-deriving anything. The list that tracks progress is
`test/scipy_import_allowlist.txt` (79 files at the start); the guard is
`test/test_scipy_seam.py`. Both directions are enforced: no new scipy, and
stale entries must be struck.

## Why scipy is going

1. **WASM is the objective.** chisurf is moving to the browser on the
   tttrlib/PRD-041 route (Pyodide + WebGPU, emtk hosts). scipy is a ~30 MB
   wheel of which chisurf's runtime uses ~2% of the surface; every runtime
   scipy call is payload a page downloads for nothing, and none of it is
   browser-critical once the calls are routed. tttrlib and IMP.bff compile to
   wasm32 and carry their kernels with them.
2. **Import cost, measured.** `scipy.stats` costs ~0.9 s at import (the reason
   `irf_estimation` is already lazy-served from
   `chisurf.core.fluorescence.tcspc`). Retiring the dep removes the class of
   problem, not one instance.
3. **Ownership.** The calls divide cleanly along existing seams: heavy
   numerics already have C++ homes (IMP.bff optimizers, tttrlib image
   kernels), the rest is small scalar math.

The inventory was taken twice (module-scope scan, then a lazy/local-scope
pass) on 2026-10-05: **79 runtime files, ~90 import sites**. Tests keep
scipy as the independent oracle for every parity test this retirement
writes.

## The five routes (decided 2026-10-05, owner: tpeulen)

### 1. numpy — delete and rename (~8 files)
`integrate.trapezoid`→`np.trapezoid` (numpy 2.4 pinned in pixi; verified),
`stats.norm.rvs`→`np.random.normal`, `linalg.eig`→`np.linalg.eig`,
`interpolate.interp1d`→`np.interp`, `spatial.distance.cdist`→broadcasting,
`stats.rankdata`→argsort (~10 lines). `gui/misc_helpers.warmup_imports`
preloads scipy.linalg/scipy.stats — those two lines are deleted with it.

### 2. local — reimplement in chisurf, correctness-first (~17 files)
A new `chisurf/core/math/special.py` (scalar/vectorized stdlib-based): erf,
erfc (`math.erf`/`math.erfc` + ufunc-ify), gammaln-on-integers via a
`math.lgamma`-seeded table (the `_LOG_FACTORIAL` pattern in
`mfd/histogram.py` is already this), `poisson.logpmf`, axis-wise `logsumexp`
(`core/ml/_gaussian.py` already has the scalar one), digamma/trigamma
(asymptotic series), `gammaincc` (olga_greedy already carries its own series;
scipy settles the error), fresnel+i0e (deer kernel), `beta.ppf`/`binom`/`j0`,
`stats.f/chi2.ppf/isf/cdf` (statistics.py CIs — incomplete beta + inverse;
low-frequency, precision-critical), `linalg.pinvh` (eigh-based ~10 lines),
`expm` (small rate matrices, eig or Padé), `odeint`→RK45 (~60 lines),
`savgol_filter` (lstsq coefficients ~40 lines), `lsq_linear`→bff or local,
UPGMA stays with clustering (route 4). Every entry gets a parity test
against scipy before its allowlist line is struck.

### 3. bff — performance-relevant numerics into IMP.bff C++ (~34 files)
The owner's call: what needs speed goes to bff. The anchor is the existing
`FitMinimizer` (MINPACK-equivalent LM in `src/FitMinimizer.cpp`, exposed in
`IMP_bff.core.i`, in the standalone wheel via `IMP_bff_standalone.i`).
- **`least_squares`/`curve_fit`/`minimize`(L-BFGS-B)**: one general
  `bff_fit(...)`/scipy-shaped shim over `FitMinimizer` (+ a small L-BFGS-B in
  C++ where a scalar objective is genuinely needed). This kills the largest
  cluster (~30 sites) with one wrapper. Reference oracle: the frozen
  `imp.bff/test/minimizer/reference_leastsqbound.py`.
- **nnls** (6 sites): Lawson–Hanson in C++ (~80 lines), exposed beside the
  minimizer.
- **Hot special functions**: digamma/polygamma/gammaln vectorized in C++
  (`std::lgamma`/`std::erfc` already used in MCMCSampler/FitStatistics) for
  the ebfret VB hot loops; the cold copies go local (route 2).
- **ODE** (`reaction/continuous.py`): if the local RK45 measures slow on real
  kinetics, it moves to bff; otherwise it stays local — decided by
  measurement, not default.
- chisurf keeps a **thin Python shim layer** so call sites read
  scipy-shaped; bff is never imported directly outside the shim.
- **WASM:** imp.bff standalone builds with scikit-build-core under
  `PYODIDE=1` exactly as tttrlib's PRD-041 does — same emsdk 4.0.9 / Pyodide
  0.28 pins. Anything routed here is browser-ready when it lands.

### 4. tttrlib — image, spatial, clustering (~15 files)
The stiff image work, in the photon library where
`richardson_lucy_2d/3d`, `wiener_deconvolve_2d`, `hdbscan`, `kmeans`,
`KDTree`, `kalman_filter`, `watershed`, `marching_squares` already ship
(verified in installed 0.27.0) and the C++ `rank_filters::median_filter`
(also min/max/midpoint shapes, striped OpenMP path, tested) and a fast
gaussian (`test_image_kernels.cpp`: integral/resize/fast_gaussian/bicubic/
histogram_moments) exist in-tree.
- **Filters**: expose `rank_filters` + fast-gaussian through mod_kernels
  (median/min/max/uniform/gaussian); ndimage `correlate` beside them.
- **Clustering/assignment**: `cKDTree`→tttrlib `KDTree`; `linkage/fcluster`
  (UPGMA) as a new kernel next to hdbscan; `linear_sum_assignment` next to
  kmeans (Jonker–Volgenant ~150 lines C++).
- **Correlating/labeling**: `scipy.ndimage.label`, `find_objects`-style
  labeling for roi/segmentation, spot_finder.
- Also covers ndxplorer's mask_helpers and (in chisurf) imaging/restoration
  callers of ndimage.
- **WASM:** everything here lands in the PRD-041 wasm wheel automatically.
  **The rank-filter/gaussian/UPGMA/JV work is the `pyodide-build` branch's
  natural follow-up content** — new kernels go to the fork (`tpeulen/tttrlib`,
  board pin 2026-09-16), not origin.

### 5. legacy-io — optional extra (~3 files)
`scipy.io` MAT readers/writers (china.py, ries_mat.py, ebfret io) stay scipy,
behind a lazy import that raises a clear error naming the
`chisurf[legacy-io]` extra. Not worth reimplementing a binary format.

## What already ships (do not re-implement)

- tttrlib 0.27.0 python surface (verified live): `hdbscan*` (7 functions),
  `KDTree`, `kmeans*` (4), `kalman_filter`, `marching_squares`, `watershed`,
  `richardson_lucy_2d/3d`, `richardson_lucy_events_2d`,
  `wiener_deconvolve_2d`.
- tttrlib dev-tree C++ (tested, unexposed): `rank_filters::median_filter`
  (square 3×3/5×5 shapes, min/max/midpoint stats, striped path ≥128 rows),
  fast gaussian, integral image, bicubic resize, histogram moments.
- IMP.bff: `FitMinimizer` (LM with chisurf's bounds transform), the graph
  objective/director path chisurf's minimizer.py already drives; the frozen
  `reference_leastsqbound.py` as the 1:1 port oracle.
- numpy 2.x: `trapezoid`, plus everything in route 1.

## Sequencing (order matters)

1. **Seam first** (landed 2026-10-05): allowlist + guard test, red/green proven.
2. **Route 1 sweep** — DONE 2026-10-05: 8 files routed to numpy (deer
   trapezoid trio, rand/brownian, hmm eig, forster interp1d, pixelwise
   spearman/rankdata, geometry cdist, warmup scipy preloads removed). Parity
   vs scipy verified (spearman 200 trials with ties, worst 1.1e-16;
   trapezoid, interp fill-0, cdist, hmm stationary all exact). Allowlist
   77→69. Pre-existing failures attributed, not this change:
   test_services ordering (SNAPPY lane), acceptor_density save/reload (fails
   at HEAD d6d2b2fe5 in an isolated worktree).
3. **bff shim** (`least_squares`/`curve_fit`/`minimize` over FitMinimizer +
   nnls + vectorized digamma/gammaln) — one PRD-sized effort, unblocks ~34
   files' worth of optimizer calls.
4. **tttrlib exposure** -- DONE 2026-10-05 (tttrlib `fb2ad5fe7`): not an exposure of
   the existing 2-D kernels (their semantics differ from scipy's), but scipy's
   own ndimage/lsap/hierarchy C ported line for line, N-D, bit-identical; plus
   the k-d tree queries and a 2-D hull. All route-4 call sites routed.
5. **Local special.py** — scalar, well-tested; parity tests against scipy.
6. **legacy-io extra** + strike remaining; scipy leaves the three manifests.

Routes 3 and 4 are the two PRD-sized efforts; 1, 2, 5 are sessions. When the
list empties, scipy joins `RETIRED` in `test/test_no_retired_dependency_imports.py`
and the manifests are edited (pyproject `dependencies`, pixi `[dependencies]`,
rattler-recipe `run:`), keeping scipy under `[test]`-equivalent extras.

## Traps

- **lltf's `leastsqbound.py` is a near-duplicate** of the core one (differs:
  no `OptimizationCancelled`, module docstring). Route 3 consolidates both
  onto the core module; do not port them separately.
- **`models.yaml` and `curve_equations.yaml` embed scipy calls in YAML**
  (`ncx2`, `root_scalar`) — text files, not importable; the seam regex scans
  `.py` only, so these were inventoried manually and belong to route 2/local
  (ncx2 = Marcum Q). The YAML seam needs its own guard when routed.
- **`misc_helpers.warmup_imports`** preloads scipy deliberately — delete
  those two lines as part of route 1, or first-use latency quietly keeps
  paying scipy's import.
- **`_minpack`/`_minpack_py` private-API import** in leastsqbound — the bff
  shim must reproduce `full_output` semantics (ier, cov_x) not just x, or
  fitter.py's covariance path breaks silently.
- **The seam excludes chimol** (WebGPU port owns its kernels) and does not
  scan `modules/quest`/`imp-tricks` (they guard their own), same as numba.
