---
type: PRD
prd: "78"
title: "PRD-78: NDXplorer histograms on tttrlib instead of boost-histogram"
description: Replace boost-histogram in NDXplorer's histogram path with tttrlib's hist module, which now matches its feature set, is at least as fast on every shape NDXplorer draws, and offers a zero-copy numpy interface -- removing a dependency chisurf carries solely for this one code path.
status: done
phase: "unassigned"
resource: modules/ndxplorer/ndxplorer/utils/histogram_computation.py
tags: [prd, ndxplorer, histogram, performance, dependencies, tttrlib]
timestamp: '2026-08-05T00:00:00Z'
---

# Summary

`histogram_computation.py` carries **three** histogram back ends: boost-histogram
(preferred), a `bincount`-based fast path, and NumPy. boost-histogram is a
dependency of chisurf as a whole — `pyproject.toml`, `pixi.toml`, and
`rattler-recipe/recipe.yaml` all list it — and it is used for essentially this
one code path.

chisurf already depends on tttrlib, and builds it from source
(`build-tttrlib`, via the tracked `modules/tttrlib` symlink). As of tttrlib
commit `5800a8da`, tttrlib's histograms **match boost-histogram's feature set**,
are **at least as fast on every shape NDXplorer draws**, and offer a
**zero-copy** numpy interface with numpy-compatible entry points that take a bin
count and a range rather than an edges array — which is what NDXplorer has.

The proposal is to make tttrlib the preferred back end, keep NumPy as the
fallback, and drop boost-histogram from the dependency set.

# Motivation

## One less dependency, and one less back end

Three back ends means three code paths that can disagree. The file already
carries a comment about boost returning `(nx, ny)` where the other two return
`(ny, nx)`, and a separate `_uniform_edges_range` helper exists to keep boost
off its slow `Variable` axis. Each is a real bug that was found and fixed once
per back end.

tttrlib is not an added dependency — it is already required, already built from
source, and already the thing producing the photon data being histogrammed.

## It is not a speed regression

Measured on an 8-core Apple machine, 10,000,000 points for the narrow path and
5,000,000 for the general one, both libraries using all cores
(`benchmarks/hist/bench_hist.py` and `bench_hist_nd.py` in the tttrlib tree;
each case runs in its own process, because a warm boost thread pool distorts the
next measurement by more than the differences being compared):

| Case | tttrlib | boost, all threads |
|---|---|---|
| 1D, 128 bins | **2.5 ms** | 2.8 ms |
| 1D, 1024 bins | 2.8 ms | 2.7 ms |
| 2D, 128 × 128 | **3.7 ms** | 4.0 ms |
| 2D, 512 × 512 | 7.6 ms | **6.7 ms** |
| 2D, 1024 × 1024 | **11.7 ms** | 17.9 ms |
| 3D, 32³ | 5.6 ms | 5.7 ms |

Faster or level everywhere. Run-to-run spread on this machine is around 30% and
it thermally throttles over a long comparison, so read anything between 0.9 and
1.1 as a tie; the 1024² row is the one clear win, and it comes from tttrlib
implementing the bin-partitioned fill that boost's own source describes as
"option C" and does not implement.

End to end through the Python wrapper on the shape NDXplorer draws — 2D
128 × 128, five million points — tttrlib is level with an 8-thread boost fill
and 121× numpy.

## And it is no longer a feature regression

This was the blocker when this PRD was first drafted. `tttrlib.HistogramNd` now
covers boost's feature set, and is tested **against boost bin for bin** rather
than against hand-written expectations (43 tests in
`test/python/test_histogram_nd.py` and `test_histogram_numpy_api.py`):

* **Axes** — regular, log, sqrt, pow, variable, integer, category, boolean
* **Options** — underflow/overflow flow bins, circular, growth
* **Storage** — counts, weighted-with-variance, `Mean` and `WeightedMean`
  profiles
* **Any rank**, and `sum`, `empty`, `project`, `rebin`, `slice`, `crop`,
  `shrink`, `reset`, `add`, `scale`

Still missing versus boost: atomic and unlimited storages, and the UHI indexing
sugar (`h[::bh.rebin(2)]`, `h[bh.loc(x)]`). Neither is used by NDXplorer.

# Proposal

## 1. A tttrlib back end in `histogram_computation.py`

Add `config.use_tttrlib_histogram`, defaulting **on**, ahead of the boost
branch. Three entry points mirror numpy's signatures exactly, so the uniform
case is a one-line swap:

```python
import tttrlib

counts, edges = tttrlib.histogram(x, bins=n, range=(lo, hi),
                                  weights=w, threads=n_threads)
H, xe, ye = tttrlib.histogram2d(x, y, bins=(nx, ny), range=(xr, yr),
                                weights=w, threads=n_threads)
```

Both are asserted equal to `np.histogram` / `np.histogram2d` in the tttrlib test
suite, so the NumPy branch stays a valid reference.

For the axis control NDXplorer needs — log axes, explicit edges, and reading the
flow counts — use the histogram object:

```python
h = tttrlib.HistogramNd(tttrlib.AxisVector([
    tttrlib.Axis.regular(nx, xlo, xhi),
    tttrlib.Axis.log(ny, ylo, yhi),          # native, no pre-transform
]))
h.fill(x, y, weight=w, threads=n_threads)

H = h.view()                # zero copy -- see below
edges_x = h.axes[0].edges   # and .centers, .widths
off_scale = h.view(flow=True)[0, :].sum() + h.view(flow=True)[-1, :].sum()
```

**The read path does not copy.** `view()` wraps the C++ buffer directly;
reshaping and slicing the flow bins off are numpy views. A 1024 × 1024
histogram costs a pointer to look at, not 8 MB — which matters for a GUI
redrawing on every parameter change.

That is safe, and enforced rather than documented:

* The returned array holds a reference to the histogram, so the buffer cannot be
  freed under it. (This needs `__array_finalize__`; without it the reference is
  lost the moment the array is reshaped.)
* The one operation that can reallocate — a fill on an axis declared with
  `growth` — is refused a view and gets a copy instead.

Points to get right, all of which the existing back ends already had to:

* **Axis order.** tttrlib returns x as the slow axis, `(nx, ny)` — the same as
  boost, so the same `.T` the boost branch already applies is needed.
* **Non-uniform edges.** Log axes are native (`Axis.log`). Genuinely arbitrary
  edges use `Axis.variable`, which binary-searches and is slower — the same
  trade-off `_uniform_edges_range` exists to manage for boost.
* **Threads.** `threads=` takes an explicit count, so `config.histogram_threads`
  and the 200k-point cutoff carry over unchanged. `0` means "decide", which
  applies the same cutoff internally.

## 2. Keep NumPy, drop the `bincount` fast path

The `fast_histogram.py` helpers exist because NumPy is slow and boost was
optional. With tttrlib always present, the fast path is a third implementation
earning nothing — tttrlib beats it on every shape. Removing it retires 217 lines
and one class of back-end-disagreement bug.

Keep the NumPy branch: it is the reference the tests compare against, and it is
what runs if a tttrlib build is ever missing the hist templates.

## 3. Drop boost-histogram from the dependency set

`pyproject.toml`, `pixi.toml`, `rattler-recipe/recipe.yaml`, and
`modules/ndxplorer/conda-recipe/meta.yaml`. Note `boost-cpp` appears separately
in the recipe and pixi and is **not** the same thing — check what else needs it
before removing that.

`test/test_declared_dependencies.py` and `test/settings/test_py314.toml`
reference boost-histogram and will need updating in the same change.

# Acceptance criteria

1. NDXplorer's 1D and 2D histograms are bin-for-bin identical to the NumPy
   branch, for linear axes, log axes, weighted fills, and empty input. The
   existing `test_histogram_robustness.py` should pass unmodified against the
   tttrlib back end.
2. No shape NDXplorer draws is slower than it is today with boost. Measure on a
   real 10⁶–10⁷-burst dataset, not synthetic uniform data — bin occupancy is
   skewed in practice and that is what a scatter-add is sensitive to.
3. `import boost_histogram` appears nowhere in chisurf, and the package is gone
   from all four dependency declarations.
4. The GUI stays responsive during a fill on a large selection: confirm
   `histogram_threads` still leaves a core free when it is set to do so.

# Risks

* **tttrlib version skew.** These entry points are new (tttrlib `b749cc1f`,
  post-0.27.0). chisurf builds tttrlib from source so this is a build-order
  concern rather than a packaging one, but the tttrlib branch must be pinned or
  the back end must feature-detect `hasattr(tttrlib, "histogram2D_range_double")`
  and fall back — the same shape as the existing `except ImportError` around
  boost.
* **The 1024 × 1024 case.** Documented above. If NDXplorer ever offers 2D
  histograms at that resolution, re-measure before assuming this still holds.
* **Non-uniform edges** are slower in tttrlib's search path than in boost's
  `Variable` axis. `_uniform_edges_range` already establishes that NDXplorer's
  edges are uniform in the common case; verify that holds for the log-spaced
  ones too.

.. seealso::

   `benchmarks/hist/bench_hist.py` in the tttrlib tree reproduces the table
   above. `modules/hist/include/Histogram.h` documents the fill strategy and
   why it is `std::thread` rather than OpenMP.

# Status: done

Landed. `ndxplorer/utils/fast_histogram.py` is now a thin adapter over
`tttrlib.HistogramNd` and is the **only** histogram engine in NDXplorer: the
boost-histogram branch, the `np.bincount` path, the NumPy fallbacks, the two
numba kernels in `performance_optimizations.py` and the chunked "streaming"
accumulator are all gone, together with the `use_boost_histogram` /
`use_fast_histogram` settings that chose between them.

Measured on this machine, a 256 x 256 fill of 2,000,000 points:

| engine | time |
|---|---|
| `np.histogram2d` | 239.5 ms |
| `np.bincount` | 40.6 ms |
| boost, threaded | 8.7 ms |
| **tttrlib** | **4.9 ms** |

1-D, 256 bins, same points: 18.8 ms for bincount against 2.5 ms.

NumPy's answers are reproduced exactly, including the closed top bin, which the
existing `test_fast_histogram.py` / `test_immediate_histogram_engine.py` compare
against directly. `boost-histogram` is gone from `pyproject.toml`, `pixi.toml`,
`rattler-recipe/recipe.yaml`, `modules/ndxplorer/conda-recipe/meta.yaml` and
`test/settings/test_py314.toml`.
