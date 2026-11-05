---
type: Architecture
title: Fused burst pipeline (tttrlib BurstPipeline)
description: One native call per measurement from the photon stream to the burst table, the per-burst decays, the strict background and the per-burst fits. Results stay in C++ buffers that Python reads as zero-copy NumPy views. Replaces the Python crossings between ChiSurf's burst stages.
resource: ../tttrlib/modules/spectroscopy/burstpipeline/include/BurstPipeline.h
tags: [architecture, burst, performance, tttrlib, mle, memory]
status: stable
timestamp: '2026-11-05T00:00:00Z'
---

# Where to pick this up

The pipeline landed on 2026-11-05 and is ChiSurf's default (`burst.fused_pipeline`;
`CHISURF_FUSED_BURST_PIPELINE=0` turns it off). Its equivalence on DNA13bp_3 is in "Measured"
below. The open front, in order of measured cost:

1. **The fit is now the cost: `run_batch` 12 s, of which 10.7 s is native DecayFit23.**
   - That is about 3 ms per 1000-channel fit on one core, times 21 808 bursts × 2 fit23
     detectors, on 8 threads.
   - It is tttrlib's model cost, not overhead. Both paths are equal here.
   - The levers are a cheaper objective per evaluation, or fewer bins (fit window cut, binning).
     More threads are not a lever: home is shared.
   - Re-derive: `fused_stats.fit.native_s` in `stages.json` of `fused_pipeline_equivalence run`.
2. **The `run_batch` preamble still copies about 149 MB a file** (`run --count`).
   - The copies come from `ensure_background`, `burst_decay_of` (`tttr[idx]` plus
     `vv_vh_histogram`) and the shift refinement (`build_decay` and `fit` per detector with an
     unfixed shift).
   - `BurstPipeline.decays(...).decay_sum(g)` is the summed burst decay those need. Port
     `burst_decay_of` to it. It is MLE-lane code, so coordinate on the agent board.
3. **The plugin's search stage is 3.7 s, of which the native pass is 0.54 s.** The rest is:
   - the container write: about 203 k calls into tttrlib, the same count with and without the
     fused path;
   - the window pre-flight: `windows_preflight` copies `micro_times`, 24 MB.

   The run read is another 197 k calls. All of this belongs to the hub/selection copy audit.
4. **Not fused; these fall back to the Python path, and `search_config` returns `None` for them:**
   - other registry searches (maxtree, BOCPD, Kalman, …), non-registry filter modes and the
     channel / micro-time pre-filter;
   - a split by state in Burst MLE;
   - the accept test of the strict selection, which stays in Python by design (an NNLS on
     histograms, one call per tightening).
5. **Fits inside `run()` (overlapping the pass) need the background up front.**
   - The background depends on the strict selection, which depends on every burst. So in the
     app's flow the fits are the second call on the CSR, as implemented.
   - The overlap pays off for a replay with a known background (More samples with a recorded
     buffer). It is not wired there yet.
6. **IMP.bff** can take the columns through its numpy `*_array` entry points (one memcpy a
   column). True zero copy needs a view type there (see "IMP.bff").
7. **Not benchmarked with an LTO build.** Both modes ran on the same non-LTO build. The table
   in `plugins/burst.md` "Pipeline wall time" was measured with LTO; compare shares, not seconds.

# Why

This is the burst pipeline's instance of [the compute/display line](compute-display-line.md):
the photons and everything computed from them stay in tttrlib; Python configures, and reads views.


The owner asked: "can't it be pipelined in tttrlib and imp.bff with less memory copy?" His rule is
that the expensive part is *crossing a boundary*: Python to C++, process to process, and any
serialisation. Before this work ChiSurf's burst pipeline crossed into Python between every stage, on
DNA13bp_3.ptu (12 M photons, 21 808 bursts, 3 detectors, RVZMT150):

| Stage (before) | What crosses | Size per crossing |
|---|---|---|
| search: `apply_photon_filters` | `macro_times`, `micro_times`, `routing_channel` out of the TTTR; one N-length bool mask per filter; `tttr[index]` copies the detector subset into a new TTTR for CUSUM | 12 M × (8 + 2 + 1) bytes, plus a subset TTTR |
| search: `find_bursts` / `drop_short_bursts` | the uint8 mask goes back into C++ (`bursts_from_mask`), pairs come out | 12 MB in, 2 × 22 k out |
| summary: `generate_burst_dataframe` | macro/micro/routing copied out again, one N-length mask per detector and per (window, detector) (9 masks), float64 prefix sums over each | 12 M × 9 × (1 + 8) bytes |
| MLE: `select_background` | `macro_times` copied as float64, an N-length burst mask, the strict mask, and for every accept test and tightening step a histogram from fresh masks | 12 M × 8 bytes × ~8 passes |
| MLE: `run_batch` | `routing_channels` and `micro_times // binning` copied out per file; per-chunk `np.repeat` index arrays; dense decays `(n_bursts, 2n)` float64, then `.tolist()` of the whole matrix into the fit | 21 808 × 1000 × 8 B = 174 MB dense, once as a list of Python floats |
| results | one dict per (burst, detector) | 65 k dicts |

# What

`tttrlib.BurstPipeline` (module `spectroscopy/burstpipeline`, which depends on `burst` and `decay`)
takes its whole configuration once, as one JSON document of plain values, and runs on a
`TTTR`:

```python
pipe = tttrlib.BurstPipeline(json.dumps(config))     # detectors, windows, search, selection, decays
res = pipe.run(tttr)                                  # one call, GIL released
res.column_view("n_photons|G|G")                      # zero-copy views; the view keeps res alive
indptr, bins, counts = res.decays("G|G")              # CSR decays of that detector's channels
pipe.fit(res, json.dumps({"fits": [...]}))            # fits on the CSR in place; adds fit|<det>|... columns
sb = tttrlib.StrictBackground(tttr, first, last, json.dumps(strict))
sel = sb.select()                                     # stats + kept-photon histograms, no mask
```

A crossing is a call from Python; a call never runs per burst or per photon. Progress and Stop go
through two `std::atomic` values the caller reads and sets from its own thread (`progress()`,
`cancel()`), never through a callback into Python.

## The pass

One loop over the records, in chunks of `chunk_size` photons (default 1 M):

1. **Classification, once per photon.** Every routing channel the setup uses gets a slot; a
   `(slot, micro-time)` look-up table gives a *combination code* (one byte), and a small table maps
   a code to the detectors and PIE windows it belongs to and to its polarisation role (P for
   `chs[::2]`, S for `chs[1::2]`) in every decay group. Detector gates and windows are half-open
   `[lo, hi)`, as `micro_time_mask` and the window masks of `generate_burst_dataframe` are. The
   codes of the photons still needed (from the first photon of the oldest burst not yet finished)
   are kept in a ring buffer: memory is bounded by the longest stretch between a burst candidate's
   start and the search's look-ahead, not by the file.
2. **The burst search on the detector subset.** The search pulls subset photons through an
   accessor that advances the cursor, so the algorithm text stays the same as
   `TTTR::burst_search_cusum_sprt` and `burst_search_sliding_window`, and only the photons it can
   still reach are buffered (the CUSUM's backward scan never goes before the current burst's
   start). The subset is the union of the detectors (channel ∩ gate), as `_search_detectors` builds
   it, or the whole stream. Any other registered search runs on a subset TTTR built in C++ (one
   copy of the subset, never through Python).
3. **The selection mask as runs.** A search burst `[a, b]` (inclusive, full-stream indices) is cut
   at photons whose gap to their predecessor fails the delta-macro-time filter (`dT_min`/`dT_max`,
   ms, over all channels; the first photon's gap is 0). The pieces are then merged when the gap
   between them is ≤ `max_gap + 1` photons, which is what `fill_small_gaps_in_array` followed by
   `bursts_from_mask(max_gap)` does (the second pass never finds a gap the first left). A run
   shorter than `max(2, min_photons)` is dropped. `invert` and the channel / micro-time pre-filters
   are supported for the "not All" settings.
4. **Per finished burst**: the static features (first/last photon, duration, midpoint macro time,
   photons, rate), the span features of every detector and every (window, detector) stream (first,
   last, duration, midpoint, photons, rate, mean micro time), and the micro-time decay of every
   decay group as one CSR row (parallel bins then perpendicular bins, `bin < n_bins`). Bursts are
   written into the result as they finish, so a fit of finished bursts can run while later chunks
   are read. The confidence column is `TTTR::burst_confidence` on the final pairs.
5. **Summed decays** per decay group (every burst photon), for the floor and the tail start.

Decay groups are keyed by a detector's channel list: R|G and R|R share channels 2, 1 and so share
one CSR. The decays are binned at `micro_time_binning`, which is the MLE's binning, not the
search's: the MLE step calls `decays(tttr, first, last, groups)` again when its binning differs.

## Strict background

`strict_background` is the definition of `chisurf/core/fluorescence/burst/irf_bg.py:
strict_background_mask`, ported as streaming passes over the photons: the flanks are built from the
burst runs; each threshold costs two passes (the fast local-rate windows, then the inside test with
the gap statistics). It returns the kept time, rate, threshold, photon count, iterations,
`rate_scale` and the per-routing-channel micro-time histogram of the kept photons. The mask itself
is never materialised. The accept test (`flat_scatter_background`, an NNLS against the IRF) stays
in ChiSurf: it judges histograms, which are small, so a rejected selection costs one more call with
a tightened threshold (at most `max_tighten` = 8 calls per file).

The quantiles of `_poisson_tail_rate` are taken from a counting histogram of the gaps in
macro-time ticks rather than from the float gaps: the order statistics are the same photons, the
values differ from NumPy's float differences by one rounding (relative 1e-9 at most), and the
histogram has a fixed size (no 12 M float array to partition).

## Fits

`fit` runs a `DecayFitModel` (`make_decay_fit`, so fit23/24/25/26) or the truncated-exponential
tail estimate per decay group, for every burst over the photon floor, on `n_threads` threads. Each
worker densifies one CSR row into its private `DecayFitProblem` (the VV gate, the VH gate rolled by
the shift, cut at the fit window's stop and zeroed before its start, as `decay_rows` and
`Fit2xSettings.to_fitted` do), so the dense `(n_bursts, 2n)` matrix never exists. A per-burst
background (one pattern per burst) and per-burst start values are accepted. The results are
columns: parameters, 2I*, the model's result vector, and the rejection code of
`_mp_worker.reject_reason` (1 too few photons, 2 not converged, 3 not finite, 4 tau under half a
bin, 5 tau longer than the window, 6 gamma at 0.99).

## What stays in ChiSurf

- The configuration: detector setup, windows as applied to the data, MLE settings, IRF processing
  (`process_irf`), background choice (`background_of`), shift refinement. ChiSurf computes plain
  arrays and passes them in.
- The burst-table *layout* (`burst_features.yaml`): tttrlib computes the quantities, ChiSurf names
  the columns. The adapter fills the declared columns from the views.
- The accept test of the strict background.

## Crossings, before and after

Counted by `fused_pipeline_equivalence run --count`, on DNA13bp_3. The table gives calls into
the `_tttrlib` extension from all code in the stage, and the photon bytes copied out of a TTTR.

| Stage | Pipeline calls (fused) | Photon bytes copied out: Python → fused |
|---|---:|---:|
| search + table | 2, plus one per column view | 150.6 MB → 24.1 MB (the rest is the window pre-flight) |
| background outside the bursts | 3 | 287.8 MB → 0 |
| strict background selection | 8 (constructor, `select`, one per tightening, `gap_rate`) | 132.4 MB → 0 |
| `run_batch` | 10 per file (`decays`, `fit`, views) | 185.5 MB → 149.4 MB (the preamble, item 2) |

The total call counts are dominated by code outside the pipeline: about 200 k calls in the
search stage and 197 k when reading the run back, both from the table writer and reader. They
are the same in both modes.

## ChiSurf adapter

`chisurf/core/fluorescence/burst/fused_pipeline.py` builds the configuration from ChiSurf's
settings, calls the pipeline, and returns what the call sites expect. Each entry point returns
`None` for a configuration it does not reproduce, and the call site then runs the Python path.

The call sites, each a few lines:

- **`burst_selection/api/selection.py:analyze_file`**
  - Entry point: `search_and_summarize`.
  - What it replaces: `apply_photon_filters`, `find_bursts`, `drop_short_bursts` and
    `summarize_bursts`.
  - The table is filled from `burst_features.yaml` exactly as `generate_burst_dataframe` fills
    it.
  - `n_selected` comes from `stats()["selected_photons"]`.
- **`burst_mle_analysis/engine.py:select_background`**
  - Entry points: `session_strict_background`, then `session_background_patterns`.
  - These take the session's accept test on histograms.
- **The two outside-burst `extract_mle_irf_background` calls in `engine.py`**
  (`extract_irf_background`, `ensure_background`)
  - Entry point: `session_outside_patterns`.
  - It makes one native pass for the histograms of the photons outside the bursts.
- **`engine.py:run_batch`**, after the `configs` are built
  - Entry point: `fit_session`.
  - Per file it makes one `decays` call and one `fit` call, then assembles the rows
    `_mp_worker.fit_jobs` returns.
  - Stop and progress go through `_poll`: the native call runs on a thread, and the caller's
    thread reads `progress_fits()` and calls `cancel()`.

`irf_bg.extract_mle_irf_background` takes `histograms=` (raw micro-time histograms per routing
channel) instead of a photon mask. The strict and outside-burst patterns therefore go through
the same function, the IRF shaping included.

The fused path is the default since its equivalence was shown (`DEFAULT = True`, setting
`burst.fused_pipeline: true`). `CHISURF_FUSED_BURST_PIPELINE=0`, or the setting set to false,
gives the Python path. A tttrlib without `BurstPipeline` gives it as well.

## IMP.bff

Checked 2026-11-05 (no refactor made). FRET lines are ChiSurf NumPy code
(`chisurf/core/fluorescence/fret/lines.py`, `fret_line.py`), and PDA is tttrlib's (`Pda`), so
neither crosses into IMP.bff today. They read the views directly, with no copy.

Where IMP.bff does take burst-level data (`FitDataset`, `HmmSurrogate`), there are two kinds of
entry point:

- **numpy.i `IN_ARRAY1` entry points.** Examples are `FitDataset.set_values_array`,
  `set_coordinate_array` and `set_mask_array`.
  - They accept a `BurstPipelineResult` view as it is: a contiguous float64 array passes the
    typemap without a NumPy-side copy.
  - The C++ side then copies it once into its own `std::vector`.
  - That is one memcpy per column, not a Python object per value. It is acceptable.
- **`std::vector<T>` by-value entry points.** Examples are `FitDataset.set_coordinate`,
  `HmmSurrogate.extract_features_from_bursts` and `..._from_layout`.
  - SWIG converts the argument element by element from a Python sequence: one Python float per
    value.
  - These are the entry points to avoid for burst columns. Use the `*_array` twin, or add one.

A tttrlib object cannot be handed to IMP.bff. The two are separate SWIG modules, and
`IMP_bff.hmmsurrogate.i` says so and hides the members that would take one. So "read the result
in place" needs one of two things:

- a non-owning view type in IMP.bff: pointer and length, plus a Python owner reference that the
  wrapper keeps;
- or an entry point taking the raw address of the buffer (`__array_interface__["data"][0]`)
  with the wrapper holding the owner.

Both would also serve tttrlib's other buffers. Neither is needed until IMP.bff consumes burst
columns at scale.

# Measured

**How it was measured.**

- Date and machine: 2026-11-05 on `ssh home`, shared, at load 20-40.
- Data: DNA13bp_3.ptu, 12.0 M photons, RVZMT150, CUSUM/SPRT on the detector subset, 21 808
  bursts, 3 detectors.
- Build: the same non-LTO tttrlib build for both modes.
- Runs: three runs per mode, one process each, alternating. The tables give the median.
- Re-derive with `python -m build_tools.dev_utils.fused_pipeline_equivalence run|compare|figure`
  (see its docstring), on home only.
- The recipe is `perf_bench/gui3_after/recipe.json` and the settings are `perf_bench/settings`.
  Both are on home.

| Stage | Python path | Fused | Peak RSS over the stage start |
|---|---:|---:|---:|
| search + table + write the run (plugin) | 6.37 s | 3.70 s | 0.51 → 0.33 GB |
| raw search + table (the engine calls alone) | 2.87 s | 0.92 s | 0.28 → 0.14 GB |
| MLE: background outside the bursts | 2.27 s | 0.64 s | 0.27 → 0.24 GB |
| MLE: strict background selection | 12.53 s | 2.38 s | 0.98 → 0.00 GB |
| MLE: `run_batch` | 12.37 s | 11.95 s | 0.20 → 0.18 GB |
| **total of these stages (with the 0.45 s run read)** | **34.0 s** | **19.1 s** | process peak **0.82 → 0.65 GB** |

- The native pass itself (classification, search, selection, features, CSR decays) takes 0.54 s
  for 12 M photons.
- It holds at most 2.1 M photon codes at once.

Equivalence (`compare`, 79 output columns):

- Bit-identical:
  - the burst table, every column of `burst_features.yaml`;
  - the strict and outside-burst background patterns;
  - every fit parameter, 2I*, r_scatter and r_experimental;
  - every rejection code (`Fit rejected (C)`).
- Within 3e-15 relative: the two tail-fit lifetimes, `Tau (R|G)` and `tau1 (R|G)`. The sum runs
  in a different order.
- The strict selection agrees:
  - Equal: 7 iterations, 15 photons kept, the same warning, and the same seconds kept to the
    last digit.
  - Within 6e-11 relative: the rate and the threshold. The gap quantiles come from a counting
    histogram of tick gaps, not from float gaps.

Synthetic guard, without real data: `test/core/test_fused_burst_pipeline.py`, 6 tests.

- It compares the search and table for both fused algorithms bit for bit.
- It compares the strict selection with and without tightening.
- It compares the background patterns at two binnings, both from the strict selection and from
  the photons outside the bursts.

The figure is tttrlib's `benchmarks/plots/fused_burst_pipeline.png`. The numbers are also in
tttrlib's PERF.md, section "Fused burst pipeline".
