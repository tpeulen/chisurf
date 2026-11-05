---
type: Architecture
title: Fused burst pipeline (tttrlib BurstPipeline)
description: One native call per measurement from the photon stream to the burst table, the per-burst decays, the strict background and the per-burst fits. Results stay in C++ buffers that Python reads as zero-copy NumPy views. Replaces the Python crossings between ChiSurf's burst stages.
resource: ../tttrlib/modules/spectroscopy/burstpipeline/include/BurstPipeline.h
tags: [architecture, burst, performance, tttrlib, mle, memory]
status: in-progress
timestamp: '2026-11-05T00:00:00Z'
---

# Where to pick this up

(Filled in at the end of each session; see the bottom of this concept for the measured state.)

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
pipe = tttrlib.BurstPipeline(json.dumps(config))   # detectors, windows, search, selection, decays, fits
res = pipe.run(tttr)                                # one call, GIL released
res.column("n_photons|G|G")                          # zero-copy float64/int64 views, owner kept alive
res.decay_indptr(0), res.decay_bins(0), res.decay_counts(0)   # CSR decays of decay group 0
bg = pipe.strict_background(tttr, res, json.dumps(strict))    # second call, no photon copies
fits = pipe.fit(tttr, res, json.dumps(fit_cfg))              # third call, fits read the CSR in place
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

To be filled with the measured numbers (see "Measured" below).

## ChiSurf adapter

`chisurf/core/fluorescence/burst/fused_pipeline.py`: builds the configuration from the selection
and MLE settings, calls the pipeline, and returns what the existing call sites expect. Behind the
setting `burst.fused_pipeline` (environment `CHISURF_FUSED_BURST_PIPELINE`) until equivalence is
shown on DNA13bp_3.

## IMP.bff

To be filled: whether the FRET-line and PDA code can read the result columns through the buffer
protocol.

# Measured

To be filled.
