---
type: Reference
title: Where numba was
description: Every function that carried a numba decorator when numba was removed from chisurf, with what replaced it and what it now costs.
resource: chisurf/
tags: [numba, performance, kernels, retirement]
timestamp: '2026-08-11T00:00:00Z'
---

# Where numba was

numba was removed from `chisurf/` in `f1290e84b` — 47 decorators, 11 imports,
every `prange`, across 13 files. This is the list of what carried a decorator,
so the slow paths can be found without reading the diff.

**Results did not change.** The kernels were plain Python loops with a decorator
on top; dropping the decorator leaves the same arithmetic at interpreter speed.
Two files got a real replacement instead (marked below).

`[parallel]` marks kernels that were `parallel=True` with `prange` — those lost
thread-level parallelism as well as compilation, so they are the furthest from
their old speed.

## Still plain Python loops — these are the slow paths

| File | Functions |
|---|---|
| `core/ml/cluster/_hdbscan.py` | `_single_linkage`, `_bfs_nodes`, `_condense`, `_label_points` (the pre-MST half — `_core_distances_bruteforce`, `_edge_less`, `_prim_mst` — was **deleted** on 2026-08-31; `tttrlib.core_distances` / `tttrlib.mutual_reachability_mst` are now required) |
| `core/ml/cluster/_kmeans.py` | `_squared_distances`, `_kmeanspp_seed`, `_kmeans_lloyd` |
| `core/roi/segmentation.py` | `_flood`, `_grow` |
| `core/fluorescence/burst/kalman.py` | `_inv2x2`, `_kalman_filter_loop` |
| `core/structure/av/functions.py` | `density2points`, `assign_diffusion_to_grid_1`, `assign_diffusion_to_grid_2`, `iterate_cpu`, `reduce_decay_cpu`, `create_fret_rate_map`, `create_quenching_map`, `random_distances`, `split_av_acv` |
| `core/structure/av/static.py` | `make_grid_axis`, `find_atom_clashes`, `define_starting_positions`, `distance_lookup`, `calc_linker_distance` |
| `core/structure/av/dynamic.py` | `_quenching_rate_per_frame` **[parallel]** |
| `core/structure/potential/potentials.py` | `centroid2`, `internal_potential`, `lj_calpha`, `gb`, `go` |
| `core/structure/protein.py` | `atom_dist`, `internal_to_cartesian` |
| `plugins/burst/burst_h2mm/core/h2mm.py` | `_matmul_norm`, `_rho_base`, `_pair_compose`, `_pair_pow`, `_build_caches` **[parallel]**, `_estep` **[parallel]**, `_viterbi_burst`, `_viterbi_all` **[parallel]** |
| `plugins/burst/burst_h2mm/core/surrogate.py` | `_feature_kernel` |

**The two that were only fallbacks are gone.** `h2mm.py` and `gopich_szabo.py`
used to prefer compiled backends (`tttrlib.HMM`, `tttrlib.GopichSzabo`) and keep
a Python loop behind them; both in-tree copies have since been deleted and the
compiled engines are required. **The rest are on the hot path** — HDBSCAN's
post-MST half, the AV grid, the dye-diffusion maps, the ProteinMC potentials and
the ROI watershed.

## Replaced rather than de-decorated

| File | Functions | What now |
|---|---|---|
| `core/fio/trajectory/dcd.py` | `_gather_frames` **[parallel]** | strided-view copy (`as_strided`); identical bytes, ~2.5–9.4× slower than numba |
| `plugins/fcs/flc_2d/core.py` | `_ceil_div_pos`, `_ceil_div_signed`, `_log_bin_int`, `create_2d_fdc_numba_int` **[parallel]**, `_fdc_scan_log_kernel` **[parallel]** | delegates to `tttrlib.fdc_scan_axis` / `fdc_scan_two_axes`; verified bit-for-bit on 13 fixture cases |

Two more left earlier in the same programme and are already compiled:
`core/math/hmm.py` (PRD-035 lattice) and
`core/fluorescence/burst/gopich_szabo.py` (`tttrlib.GopichSzabo`).

## Where the replacements are specified

Not "missing" — written down, with interfaces and test cases:

- **Board tickets `T-20260811-14` … `-20`** (`okf/agent-board.md`) — one per
  group, each carrying the interface and the tests that decide it.
- **tttrlib PRD-037 Part B** — the kernels themselves: HDBSCAN post-MST,
  k-means, Kalman, watershed + marching squares, DCD de-interleave.
- **ChiSurf PRD-100** — the AV / potentials group, which has **no upstream
  target at all** today (`IMP.bff` exposes only `AVNetworkRestraint`).

## Two measurements worth not repeating

- `av/dynamic.py`'s `_quenching_rate_per_frame` is a masked row-sum. Both NumPy
  spellings are **2.9–16.2× slower** and not bit-exact: `(collided != 0) @ k`
  upcasts a `uint8 (100000, 500)` mask into a 400 MB `float64` temporary, which
  is the materialisation the loop existed to avoid.
- `dcd.py`'s `_gather_frames` as a NumPy fancy-index gather is **7.4–21.5×**
  slower; as the strided view now in place, **2.5–9.4×**. A parallel gather
  *with* a transpose is the shape NumPy expresses worst.

## Parity fixtures already recorded

Recorded from the numba kernels **before** they were deleted, so a compiled
replacement can be checked against what the code actually did:
`test/data/numba_parity/` — `maxent_tcspc.npz`, `hmm_lattice.npz`,
`gopich_szabo.npz`, `flc_2d_fdc.npz`, `atoms_in_reach.npz`.
