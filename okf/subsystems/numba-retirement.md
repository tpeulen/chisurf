---
type: Subsystem
title: Retiring numba from the shipped package
description: Why numba is leaving chisurf/, the five routes a kernel can take out of it, the measurements that decide which, and the shrinking allow-list that tracks it.
resource: test/numba_import_allowlist.txt
tags: [core, dependencies, performance, numba, seam]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

1. **The tracker is `test/numba_import_allowlist.txt`** and it only shrinks.
   Every entry carries its route. **34 of the original 59 files remain** — 18 ported by this work, 7 struck by the ChiMOL WebGPU port, which shrinks the same list;
   `test/test_numba_seam.py` fails both on a new importer and on a stale entry,
   so the list cannot drift from the tree.
2. **Route `tttrlib`: next is `plugins/fluorescence_decay/maxent_decay/core/solver.py`**
   (3 kernels) — the strongest remaining candidate, already checked. Its own
   docstrings call them "Numba port of … from `fsconv2.c`", which is the same C
   source the photon library compiles, and the signatures line up exactly:

   | local | tttrlib |
   | --- | --- |
   | `_fconv_single_shot(lampsh, dt, amps, taus, stop)` | `tcspc_fconv_single_shot(lampsh, dt, amps, taus, stop)` |
   | `_fconv_periodic(lampsh, dt, amps, taus, start, stop, period)` | `tcspc_fconv_periodic(lampsh, dt, amps, taus, start, stop, period)` |
   | `_shift_lamp(lamp, ts_channels) -> lampsh` | `shift_lamp(lamp, lampsh, ts, out_value)` (out-parameter form) |

   **Still diff the maths before switching** — that rule was earned three times
   over (see below), and `_fconv_periodic` has a `while lampsh[lamp_start] == 0`
   scan for the first non-zero IRF channel that the C version may or may not
   share. Call sites: `solver.py:387, 392, 402, 432, 434, 488, 498, 508`.

   Done already: `tcspc/convolve.py` (deleting its numba twin *fixed* a bug) and
   the LLTF copies, which are now re-exports.
   Verified present in tttrlib 0.27.0 — do not re-derive: `fconv`,
   `fconv_per_cs`, `sconv`, `fconv_ref`, `shift_lamp`, `rescale_w_bg`,
   `rescale_w`, `add_pile_up_to_model`, `histogram1D_double`,
   `histogram1D_int`, `decode_records`, `GopichSzabo`, `HMM`/`HmmModel`/
   `HmmVB`, `maxent_invert`, `solve_tcspc_mem_lifetime`, `OptsCluster`.
3. **A `tttrlib` route is a hypothesis, not a verdict — diff the maths first.**
   Two files routed to `tttrlib` turned out to be route `numpy`, because
   ChiSurf's version is *deliberately better than the C one* and delegating
   would have been a silent regression:
   `tcspc/corrections.py::add_pile_up_to_model` caps the detection probability
   below one, bails out when Coates' correction is undefined instead of
   returning NaN, and uses the analytic limit in empty channels where the C
   version divides by a substituted 1.0 and so **zeroes the model** there;
   `tcspc/tcspc.py::rescale_w_bg` guards on a finite weight (an empty channel
   can carry an infinite one), omits the C version's `1e-12` floor, and does
   not rescale the model as a side effect. Both bodies were already pure NumPy
   under the decorator. So: read both implementations before delegating, and
   when they differ, work out *which* is right rather than assuming the
   compiled one is.
4. **`_hdbscan.py` splits — measured, so do not re-derive.** The compiled
   kernel covers only the first two stages (`core_distances`,
   `mutual_reachability_mst`); `single_linkage`, `condense_tree` and
   `label_points` are **not** in the photon library. Timed on the *compiled*
   path, those four remaining kernels are **43% of a run** — n=20,000:
   MST 22.4 ms, single-linkage 3.9 ms, condense+label 13.0 ms; n=100,000:
   117.6 / 25.4 / 65.1 ms. So three kernels
   (`_core_distances_bruteforce`, `_edge_less`, `_prim_mst`) go by making the
   compiled path **required**, and the other four are route `tttr-c`: union-find
   with path halving, a BFS over the dendrogram and a dynamic compaction, none
   of which NumPy expresses and all of which are hot. `plugins/burst/burst_h2mm/` already has
   `h2mm_tttrlib.py` and `surrogate_tttrlib.py`, so the eight-kernel `h2mm.py`
   may be mostly covered. `core/math/hmm.py` is listed under `tttrlib` for the
   same reason, but **measure before delegating** — it is the hmmlearn
   replacement and is 1.1–18× faster per E-step, so a regression there is a
   visible loss.
5. **`gopich_szabo.py` has a red test that is not the port's fault.**
   `test_no_exchange_reduces_to_a_static_mixture` returns `-inf` where
   `-3.665` is expected — `-inf` is the numba kernel's own numerical-failure
   sentinel. Check whether `tttrlib.GopichSzabo` gives the expected value
   *before* debugging the kernel that is about to be deleted. Recorded in
   [known-issues](../references/known-issues.md) with four unrelated
   `mfd_burst_roundtrip` failures, so the retirement's test runs are not read
   as having caused them.
6. **ChiMOL's 11 files are not this work's.** They are allow-listed under a
   `chimol` route and belong to the WebGPU port claimed on the agent board.

## Why it is going

Not for footprint. Measured with `conda create --dry-run` against a
chisurf-shaped closure, numba costs **2 packages** (itself and `llvmlite`,
138 → 140). The reasons are behavioural:

* **It stalls the GUI thread.** Opening a fit window once cost **229.5 ms**
  JIT-compiling a three-line Durbin-Watson statistic; a ~340 ms
  first-evaluation compile is why `per`-mode convolution was already routed to
  the photon library. `test/math/test_durbin_watson.py` still guards the first.
* **Its thread pool latches.** `NUMBA_NUM_THREADS` cannot be set once a
  `parallel=True` kernel has run, which is why `pytest test/fio` fails as a
  directory and passes file-by-file, and why `parallel=True` is banned outright
  in `chisurf.core.ml`.
* **`fastmath` changes answers quietly.** One kernel's `fastmath=True` folded
  away its own `isfinite` guard, so which bin a NaN landed in depended on
  whether numba was installed.
* **It cannot run in Pyodide**, which blocks the browser target.

**The honest scope claim is "`chisurf/` imports numba nowhere", not "the
dependency is gone".** `modules/quest` (20 kernels) and `modules/imp-tricks`
(188) still declare it and `build-extensions` installs both, so it stays in the
solved environment until those follow. Say it that way, as the pandas
retirement did.

## The measurement that sets the routing

Profiled via `test/benchmarks/benchmark_fit_hot_path.py`; table in
[benchmarks](../../docs/development/benchmarks.md).

A 1024-channel two-component `LifetimeModel` fit calls **no numba kernel at
all** — `Convolve.convolve` is 40% of it and already routes to
`tttrlib.fconv_per_cs`, and `Parameter.value` (27,340 reads) costs more than the
convolution's own body. In a `GaussianModel` fit every numba kernel together is
**~4%**, while numba's own dispatcher type-resolution
(`numba/core/types/abstract.py:__hash__`, 1470 calls) profiles *above* them.

So on `2 * n_components`-element arrays the JIT dispatch costs more than the
arithmetic it dispatches to, and plain NumPy is the **faster** answer rather
than the compromise. That is what route `numpy` means, and why it is the
largest bucket.

## The five routes

| Route | When | Where it goes |
| --- | --- | --- |
| `numpy` | Elementwise, dead, or small enough that dispatch dominates | Delete the decorator |
| `tttrlib` | A compiled equivalent already ships | Delegate; write no new code |
| `imp` | Molecular modelling that already migrated to imp-tricks | Delete the copy, import `IMP.bff` / `IMP.cgmol` |
| `tttr-c` | Genuinely serial and genuinely hot, no equivalent yet | New kernel in tttrlib's `modules/math` |
| `wgsl` | Large uniform 3-D grid, one-shot, independent per voxel | Compute shader via `chisurf/core/gpu` |

`imp` is available because **IMP is now a declared dependency** — it costs +68
packages (138 → 206, including `rmf`, `libboost`, `libopencv`, `ffmpeg`,
`mpich` and `qt6-main`), which is a deliberate trade. Watch the `qt6-main`
entry: it sits beside the conda `pyqt` the app runs on, and two Qt providers in
one environment is the shape that produces "Class … implemented in both" then
`QObject::moveToThread` failures.

**One deliberate exception to `imp`.** `math/functions/rdf.py` and
`math/functions/distributions.py` have identical twins in `IMP/bff/polymer.py`
and `IMP/bff/distributions.py`, but those twins are themselves `@njit`-decorated
and imp-tricks keeps numba for now. Delegating the fit path to them would
re-import the first-call JIT stall this work exists to remove, so they stay in
chisurf as NumPy. The duplication collapses when imp-tricks is ported.

## How a port is proven

**Against committed fixtures generated from the numba original, never against
numba at test time.** A live comparison evaporates — as a *skip that reads like
a pass* — on the day numba leaves, which is the trap the mdtraj retirement
recorded. `test/data/numba_parity/` holds inputs *and* the outputs numba
actually produced; `test/fluorescence/test_general_kernels_parity.py` is the
worked example.

**Write the harness to attack the port, not to confirm it.** Three real
disagreements were caught this way and every one is invisible to a
does-it-run test:

* **`_fast_convolve_loop` bins right-closed.** `searchsorted(edges, v) - 1`
  puts a value equal to an interior edge in the bin *below* it and drops a value
  equal to `edges[0]` entirely. `np.histogram` is left-closed. The smallest
  product the caller feeds in is `edges[0]` by construction, so the two
  conventions disagree on real input.
* **`minmax`'s `ignore_zero` is asymmetric.** The `continue` sits *after* the
  maximum is updated, so a zero can still be the largest value while being
  excluded from the minimum, and an all-zero input must still return `+inf`.
* **`histogram1D`'s top bin is closed.** `floor((v - min) * width)` maps
  `v == tth_max` to exactly `n_bins - 1`.

**And discard the first benchmark run in a fresh process.** A cold run came out
uniformly slow, with one cell reading 2.983 s against the 0.61 s it actually
costs — enough to credit an unrelated change with a fivefold speedup. Attribute
any apparent movement by swapping the old file back in and re-measuring in the
same session; the general.py port did that and came out at 0.637 s vs 0.636 s
with byte-identical evaluation counts.

## Open upstream: the Gopich-Szabo scheme rejection

Filed in the photon library's `BUGS.md` (commit `511d654a7`) and **owned by
another agent** — do not fix it here. `GopichSzabo::set_scheme` refuses any
scheme with a repeated zero eigenvalue: the all-zero no-exchange limit, or any
scheme with a state that does not exchange with the rest (a plain three-state
model with one isolated state is enough).

**What to check when it lands:** the warning in
`gopich_szabo.log_likelihood` stops firing; `test_gopich_szabo.py` passes
through the *compiled* path rather than the fall-through; and the
[known-issues](../references/known-issues.md) entry can close. The fall-through
itself stays either way — a setup failure is not an impossible model.

## A defect in the photon library is filed there, not worked around here

**USER RULE.** When a port uncovers a bug in the compiled library, it goes in
that repo's `BUGS.md` with a runnable reproduction and is **fixed there**. A
ChiSurf-side patch that makes the symptom go away is not a fix — it is how a
library defect becomes permanent, because the results come out right and nobody
ever looks again.

Where ChiSurf still needs a fall-back for correctness in the meantime, the
fall-back **says so**: `gopich_szabo.log_likelihood` logs a warning naming the
filed bug when the compiled engine refuses a scheme. Silence is what turns a
temporary path into an architectural one, and the warning disappears by itself
once the library is fixed.

## Bugs the ports have found

Kept here because they are the argument for doing this carefully rather than
mechanically.

* **`calculate_fluorescence_decay` rewrote its caller's spectrum.**
  `am = lifetime_spectrum[0::2]` is a strided view and `am /= am.sum()` divided
  through it, so asking for a decay renormalised the array passed in and a
  second call with the same spectrum returned a *different* curve.
  `[1,4,3,1]` came back as `[0.25,4,0.75,1]`. Fixed; pinned by a mutation test
  *and* a call-to-call stability test, because a test that only checks the
  returned decay passes either way.
* **The periodic convolution's numba twin never gave the final channel its
  inter-pulse tail** — and the guard test written to catch exactly that had been
  failing. Settled with an independent brute-force sum rather than by picking a
  side: at two lifetimes the twin returned 2.2e-53 where the truth is 1.55e-27,
  and at 128 it was 200x low, while the C kernel reproduces the reference. So
  deleting the twin was a *fix*, not a like-for-like swap. The rewritten
  `test/test_periodic_convolution_reference.py` now asserts the surviving
  implementation is **right** rather than that two implementations agree.
  Two things learned there that the next comparison will need: the kernel's
  **channel 0** uses its own start convention (~1.94x a plain trapezoid's
  half-weighted first term — characterised, not derived), and a brute force that
  does not model the **IRF's own periodic wrap** is not a valid reference for a
  response carrying weight at the far end.
* **`_reaction.py`'s numba path was never compiled.** Two byte-identical copies
  of the Gillespie SSA loop behind a `_HAVE_NUMBA` switch, the numba one
  `jit(forceobj=True)` — object mode, because the loop calls Python propensity
  callables. The switch chose between the same interpreted code reached
  directly and reached through a dispatcher.

## Progress

| | Files | Kernels |
| --- | ---: | ---: |
| At the start | 59 | 186 |
| Ported so far | 25 | ~70 |
| Remaining | 34 | ~116 |

Done: `fluorescence/general.py`, `math/datatools.py`, `math/statistics.py`,
`math/signal.py`, `fluorescence/burst/utils.py`, `math/reaction/_reaction.py`,
`fluorescence/tcspc/convolve.py`, `fluorescence/tcspc/corrections.py`,
`fluorescence/tcspc/tcspc.py`, and the three LLTF modules, which now re-export
the shared implementations instead of copying them.
