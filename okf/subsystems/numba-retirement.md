---
type: Subsystem
title: Retiring numba from the shipped package
description: Why numba is leaving chisurf/, the five routes a kernel can take out of it, the measurements that decide which, and the shrinking allow-list that tracks it.
resource: test/numba_import_allowlist.txt
tags: [core, dependencies, performance, numba, seam]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

**The remaining work is issued as tickets, not as prose here.** Seven on the
shared board (`okf/agent-board.md`), each carrying its **interface** and its
**test cases** so it can be picked up without re-deriving anything:

| Ticket | Files | Kernels | State |
|---|---|---:|---|
| `T-20260811-14` | `flc_2d/core.py` | 5 | delegation written and exact; land it |
| `T-20260811-15` | `_hdbscan.py` (part) | 3 | compiled path exists; make it required |
| `T-20260811-16` | h2mm call sites | 0 | prerequisite for `h2mm.py`'s 8 |
| `T-20260811-17` | `av/static.py` + part of `av/functions.py` | 9 | PRD-100 g1 |
| `T-20260811-18` | `av/dynamic.py` + rest of `av/functions.py` | 7 | PRD-100 g2, decision first |
| `T-20260811-19` | `potentials.py`, `protein.py` | 7 | PRD-100 g3, **no IMP target** |
| `T-20260811-20` | `_kmeans`, `kalman`, `segmentation`, `dcd`, `_hdbscan` rest | 15 | blocked on tttrlib PRD-037 B |

Two things the tickets encode that this file used to bury:

- **Every route tag is a hypothesis.** Six were wrong and were corrected by
  *importing* rather than reading. The tickets state what was checked and when.
- **A parity fixture recorded from the code being replaced cannot tell a
  faithful port from a shared mistake.** Every ticket that deletes a kernel also
  names a property or simulation test with an independent answer.

**Everything this needs from the photon library is one document**:
tttrlib `okf/prds/PRD-037-kernels-to-finish-chisurfs-numba-retirement.md`
(2026-08-11, written at the user's request because the per-file round trips were
costing three build cycles each). It unblocks **8 of the 13 remaining files and
30 of the 56 kernels**; the other five need nothing from there —
[PRD-100](../prds/prd-100.md) for the AV/IMP group, a WGSL shader for
`av/functions.py`, and ChiSurf-side routing for `h2mm.py`. **Do not open
per-file requests upstream** — add to that PRD instead.

Two route labels were corrected while writing it, both by import rather than
argument: `OptsCluster` is 2-D Gaussian *peak fitting*, not k-means, and
`_frc_smooth` is FRC smoothing, not a Kalman filter. `core_distances` and
`mutual_reachability_mst` do exist and already cover three of `_hdbscan.py`'s
seven kernels.

1. **The tracker is `test/numba_import_allowlist.txt`** and it only shrinks.
   Every entry carries its route. **12 chisurf-owned files remain**, and **route `numpy` is now empty -- Phase 1 is done** of the 48 this work covers. ChiMOL's 11 are **excluded from the guard entirely** — the WebGPU port removes them on its own schedule, and listing them here only made this test fail nine times in one session with news about someone else's progress;
   `test/test_numba_seam.py` fails both on a new importer and on a stale entry,
   so the list cannot drift from the tree.
2. **`maxent_decay/core/solver.py` is done, and the granularity of a delegation
   is a measurement, not a detail.** All three kernels (`_shift_lamp`,
   `_fconv_single_shot`, `_fconv_periodic`) are deleted and the *design
   matrices* come from `tttrlib.tcspc_build_fi_lifetimes` /
   `tcspc_build_fi_distances` in one call each. **Delegating the kernels
   themselves — the obvious reading of route `tttrlib` — was 10.6× slower than
   numba**: 1.57 → 16.6 ms for a 301-lifetime grid, because marshalling a
   512-element `std::vector` cost ~26 µs against a ~0.4 µs kernel. **That
   number is historical**: the typemap conversion below cut the marshalling to
   ~0.8 µs, so per-kernel delegation is no longer 10.6× slower. The conclusion
   is unchanged and is the point — per-column is still 2.3× the cost of the one
   whole-matrix call, and the ratio was never the argument. Per-column is
   the wrong seam whatever is on the other side of it; the whole matrix has to
   cross at once. **The cause is now measured and filed upstream**: tttrlib's
   `%template(VectorDouble) std::vector<double>` makes every such binding convert
   through the Python sequence protocol at ~50 ns per element, so a
   zero-channel shift costs 24.4 µs of the 24.8 µs a real one does — 98%
   wrapper. The rule that follows governs this whole route: **a loop stays whole
   in C++, and the seam is crossed once per analysis, never per iteration or per
   column.** Numbers, the NumPy-typemap fix and the worklist are in tttrlib's
   `okf/bindings/marshalling-cost.md` and its `BUGS.md`.
   (For the record, a banked NumPy recursion — one pass over the
   channel axis with the lifetime axis vectorised — is *bit-exact* and 2.9×
   faster than numba, so route `numpy` was viable here too. It was not taken:
   **the maximum-entropy engine belongs in the photon library**, and a second
   implementation in ChiSurf is the thing this work exists to remove.)

   Two defects fell out, both in the same shape — code that exists but cannot
   be reached:
   - **`tcspc_build_fi_lifetimes` / `_distances` were unusable from Python.**
     They return four arrays through reference parameters, which SWIG's
     `std::vector` typemaps turn into four *required inputs* no caller can
     supply. Fixed in tttrlib `ext/python/MaxEntTcspc.i` with NumPy bindings
     returning `(Fi, y, sigma, fit_additive)`. Nothing failed before: the
     high-level `solve_tcspc_mem_*` covered the only exercised path, so the
     builders were dead in the binding while alive in C++.
   - **tttrlib's own `test_maxent_tcspc.py` compared against ChiSurf** through a
     hard-coded `sys.path.insert('/Users/tpeulen/dev/chisurf')` inside a
     `try/except` that set `_HAVE_REF = False`. Deleting ChiSurf's kernels would
     have turned every one of those tests into a **skip that reads like a
     pass** — and the two solver tests were already tautological, since
     ChiSurf's fast path *is* the C++ call. Rewritten to stand alone: analytic
     shifts, a brute-force reference recursion, KKT conditions for the QP,
     column-by-column checks of the new builders, and recovery of a known
     lifetime and a known distance.

   Validation stays on the ChiSurf side deliberately: the C++ builder does not
   filter `tau <= 0` (it would divide by zero) and does not reject an empty
   grid.

   Done already on this route: `tcspc/convolve.py` (deleting its numba twin
   *fixed* a bug) and the LLTF copies, which are now re-exports.
   Verified present in tttrlib 0.27.0 — do not re-derive: `fconv`,
   `fconv_per_cs`, `sconv`, `fconv_ref`, `shift_lamp`, `rescale_w_bg`,
   `rescale_w`, `add_pile_up_to_model`, `histogram1D_double`,
   `histogram1D_int`, `decode_records`, `GopichSzabo`, `HMM`/`HmmModel`/
   `HmmVB`, `maxent_invert`, `solve_tcspc_mem_lifetime`, `OptsCluster`.

   **Still open there, and it is not numba:** `_run_mem` and `_quadpr_bound` are
   a second copy of `tcspc_run_mem` / `tcspc_quadpr_bound` in NumPy. They stay
   until the C++ grows a per-iteration progress callback — the MEM loop is where
   the seconds go, and the plugin's GUI drives its progress bar and its
   convergence history off exactly that callback. Worth knowing before anyone
   reads that QP as broken: **it is not an optimal solver and does not claim to
   be** — the sweep clamps a violating variable, re-solves the free block
   *without* the clamped variables' coupling, and never releases one or checks a
   multiplier's sign. Neither stationarity nor dual feasibility holds; the outer
   MEM iteration re-solves it every step with an updated diagonal, which is why
   that is tolerable. Both copies share the behaviour.

3. **`plugins/core/acq/gui/tool.py` is done — the copy is deleted, not ported.**
   `_process_bh_spc_records_numba` was a hand-maintained transcription of
   `RecordProcessor<BH_RECORD_TYPE_SPC130>`, and its own test said why it
   existed: the library exposed that decoder only behind a *file* reader, and
   live acquisition decodes records arriving from the card **in memory**. It
   exposes `decode_records(buffer, record_type, state)` now, so
   `_decode_bh_spc_records` is 15 lines of delegation and the format has one
   implementation again. Verified against `bh_spc132.spc` and
   `bh_spc132_sm_dna/m000.spc`: identical macro times, micro times, routing
   channels *and* overflow counter (1127184 / 1252232) — the numba copy was
   correct, which is the only reason this reads as tidying rather than a bug
   fix.

   Two things the port had to keep, neither visible in the diff:
   - **The wrap counter across chunk boundaries.** `state.overflow_counter`
     carries it; a fresh state per chunk restarts every buffer at time zero and
     yields a perfectly plausible first chunk and nonsense from the second on,
     with nothing raised. The rewritten test decodes a real file in 4096-record
     chunks and demands the file back.
   - **`uint8` routing channels.** The library hands back `int8`, and
     `_accumulate` reinterprets what it is given, so the cast is load-bearing.

   The test that pinned the copy said "if the library ever grows an in-memory
   record decoder, this test should be deleted along with the copy". It is
   rewritten instead: comparing two implementations is now a tautology, but the
   chunk-boundary state is still ChiSurf's to get wrong.

   Check what the library exposes *first*: this entry cost far less than
   budgeted because `decode_records` already existed and nothing in ChiSurf
   knew.

   **Four routing corrections, all from checking or measuring before porting.
   Do not re-derive these.**

   - **`core/math/hmm.py` is NOT route `tttrlib`.** The library's HMM is a
     *photon-stream* model — per-burst, Δt-dependent transition matrices,
     discrete symbol emissions (`obs[k*p + y]`) — and its recursion is
     **scaled, not log-domain** (`forward_burst` in `modules/spectroscopy/hmm/
     src/HMM.cpp`, `static`, unexported). ChiSurf's is a generic log-domain
     lattice over a caller-supplied `log_frameprob`. Different algorithm,
     different numerics; `HmmEval.gamma_obs_np` / `xi_np` are E-step outputs of
     that other model, not a lattice one can borrow. **Reroute to `tttr-c`**: a
     generic log-domain forward / backward / posteriors-and-xi kernel in
     tttrlib's `modules/math`, NumPy-bound. Route `numpy` is out — the
     recursions are serial in `t` and only vectorise over states, so a NumPy
     rewrite pays Python loop overhead once per sample.
     **Done 2026-08-11.** tttrlib PRD-035 landed the lattice
     (`hmm_forward_log`, `hmm_backward_log`, `hmm_backward_posteriors_xi`,
     `hmm_viterbi_log`, `hmm_logsumexp`, plus an `hmm_estep_log` taking
     `lengths`); the five numba kernels here are thin forwards to it and
     `import numba` is gone. It came out **1.1–1.6× faster** than the numba it
     replaces rather than merely matching. Proven by
     `test/math/test_hmm_lattice_parity.py` against the committed fixture, and
     the fixture itself is anchored to hmmlearn (above). Two things went with
     it: `LOG_DOMAIN_FASTMATH` (the constraint moved into a translation unit
     built without fast-math, and the test now checks the *behaviour* against a
     written-out reference instead of the flag set) and a dead
     `_squared_distances`, a duplicate of the live one in
     `core/ml/cluster/_kmeans.py`.
     **It depends on tttrlib files that are not committed** — see
     [known issues](/references/known-issues.md).
   - **`fio/trajectory/dcd.py` and `xtc.py` are NOT route `imp`.** The label
     said "already migrated to imp-tricks; delete the leftover", and imp-tricks
     has **no trajectory reader at all** — nothing to delegate to. Nor do they
     vectorise, measured rather than assumed:
     - `dcd.py`'s `_gather_frames` de-interleaves DCD's separate X/Y/Z blocks.
       A NumPy fancy-index gather is **7.4–21.5× slower** (bit-identical), and
       describing the payload as a 3-D strided view — the better idea — only
       gets to **2.5–9.4×**. It is a parallel gather *with a transpose*, which
       is the shape NumPy expresses worst; the broadcast index array alone is
       80 MB at 200 frames × 50k atoms.
     - `xtc.py`'s six kernels were the **XDR bit-unpacking decompressor**
       (`_decodebits`, `_decodeints`, `_sizeofint`, `_sizeofints`,
       `_decompress`, `_decompress_many`). Serial bit manipulation; NumPy
       cannot express it at all.
     **`xtc.py` was then deleted outright** (2026-08-11, user's instruction:
     DCD is enough). That is the cheapest way off this list and the one worth
     asking about first — six kernels left with the feature, and the format was
     also the only place in the tree where coordinates were rescaled on read.
     `dcd.py` moved to route `tttr-c`; it is the one entry there with no photon
     content, so whoever writes that kernel should settle where a trajectory
     reader belongs first.
   - **`av/dynamic.py`'s kernel does not vectorise either**, though its route
     (`imp`) is right — `IMP.bff.AV` exists. `_quenching_rate_per_frame` is a
     masked row-sum, i.e. a matrix–vector product, and both NumPy spellings are
     **2.9–16.2× slower** and not bit-exact: `(collided != 0) @ k` upcasts a
     `uint8` `(100000, 500)` mask to a 400 MB `float64` temporary, which is the
     materialisation the numba loop exists to avoid. So the file leaves by
     delegating to `IMP.bff`, not by deleting the decorator.
   - **The `imp` group is not "delete the leftover", and nothing in this area
     is dead.** Importers, absolute + relative: `potentials.py` 10,
     `dcd.py` 5+1, `protein.py` 4, `av/dynamic.py` 3, `av/static.py` 1+1,
     `xtc.py` 2+1 — and `av/functions.py` (route `wgsl`) **11, all relative**,
     via `from . import functions` inside `av/__init__.py`. Count relative
     imports: a grep for the dotted module path alone reports `functions.py` as
     having no callers, which is exactly backwards for the most-used file of
     the set. These need real ports or real delegation to `IMP.bff` /
     `IMP.cgmol`; budget accordingly.

   **`core/structure/av/utils.py` is done** and is the cheap shape: a two-pass
   `@nb.jit` loop that was a boolean mask all along. Vectorised, bit-identical
   on 27 recorded cases, pinned by `test/structure/test_atoms_in_reach_parity.py`
   against a fixture frozen from the numba original. Its one caller,
   `av/static.py`, indexes the two returned arrays against each other, so the
   port had to keep index order and the self-exclusion — both asserted.

   **Next on this route: `core/ml/cluster/_hdbscan.py`** (see item 10 — it
   splits, and the measurement is already recorded).
4. **PCH is done, and it was three copies, not one.** `plugins/pch/api/algorithms.py`
   (numba) turned out to duplicate `core/models/pch/pch.py`, which *already*
   delegated to tttrlib behind an unexercised pure-Python fallback — and
   `gui/widgets/models/pch/widgets.py` had carried a third copy until a peer's
   `4df1b1041` extracted it. There is now one implementation in
   `core/models/pch/pch.py`; the plugin module is a re-export.

   The two conventions that decided the delegation was safe, both confirmed
   rather than assumed: the shell weight `x**2` of the *3-D* Gaussian (dropping
   it gives `2**-0.5` instead of `gamma_2 = 2**-1.5`), and `p1[0]` as the
   complement of the `k >= 1` terms, which folds the `4 pi w^3 / V_0` prefactor
   into the reference volume. **The second is the one that would not have shown
   up in an amplitude comparison** — a different normalisation changes what
   `avgN` *means*, not what it equals. Measured: `p1[0]` agrees to the last
   digit, arrays to `1e-16`, mixtures to `4e-17`.

   Two defects fell out of the check, both silent:
   - **tttrlib `pch_mixture` reads past the end of `avg_numbers`** — it loops
     over `brightnesses` and subscripts the occupancies with the same index,
     unchecked. It does not crash: the heap there is zero, the
     `avg_numbers[s] <= 0.0` guard on the *next line* then skips the species
     whose occupancy was never supplied, and the caller gets a normalised finite
     histogram of fewer species than it asked for — stable across processes, so
     even a reproducibility test calls it correct. Filed in tttrlib `BUGS.md`
     (`6b505cf24`). The length check in `pch_mixture` stays in front of the
     delegation until that lands.
   - **A non-contiguous count axis was answered for a different axis.** The C++
     takes a scalar `k_max` and builds `0, 1, ... k_max` itself, so the
     pre-existing `int(k_vals[-1])` delegation could not represent the axis
     `pch_model.py` reads from dataset metadata. Now `_k_max` raises and
     `update_model` logs and flattens — a flat curve reads as bad data, a
     wrong-axis histogram reads as a bad fit.

   Also fixed here: `test/gui/test_pch_models_resolve.py` had been red since
   `4df1b1041` (importing the widget kernels that refactor deleted). Retargeted
   at the surviving implementation rather than deleted — what they pin,
   `gamma_2` and the `k = 171` factorial overflow, is still worth pinning.
5. **`linalg` is done, and it is the case where "delete the decorator" was not
   enough.** The 3-vector helpers are now NumPy and bit-exact against the numba
   versions (0.0e+00 on every one). But measured on the only live consumer,
   `protein.py`'s per-residue walk over hGBP1 (3456 internal coordinates), the
   naive port was a **4.9× regression** — 0.096 s compiled to 0.474 s scalar
   NumPy, because a 3-element operation is all call overhead. **Do not ship a
   Route-`numpy` port on measurement of the kernel alone; measure the loop that
   calls it.**

   The fix is the one the routing table always implied: the helpers are written
   against the last axis, so they take `(n, 3)` stacks, and
   `calc_internal_coordinates_bb` now collects its quadruples and measures them
   in three stacked calls instead of ~10,000 scalar ones — **0.021 s, 4.5×
   faster than the numba version it replaces**. Compiling could never have
   reached that, because the cost was the Python calls, not the arithmetic.
   The same shape applies to the remaining `numpy` entries: check the call
   pattern before assuming the decorator is all that has to go.

   Three latent defects surfaced, all pre-existing, all now fixed with a
   guardrail suite (`test/structure/test_internal_coordinates.py`):
   `angle` returned **NaN for collinear points** (the normalised dot product
   overshoots one by 4.4e-16 and `arccos` of that is not a number; `dihedral`
   had always clamped, `angle` never did), and `ProteinCentroid` could not load
   *any* crystallographic PDB — `KeyError: 'H'` because it chose side-chain
   atoms by residue name rather than by what the file contains and X-ray does
   not resolve hydrogens, `KeyError: 'CA'` on the waters that `residue_dict`
   also holds, and `ValueError: -1 is not in list` from looking up the
   absent-atom sentinel. 148L now loads. 1RTD still does not — nucleotides are
   a capability gap, recorded in
   [known-issues](../references/known-issues.md), deliberately not fixed here
   because `protein.py` is route `imp` and `IMP.cgmol.protein` may already
   cover it.

   `rotate_point` sliced the quaternion vector part as `quaternion[1:3]` — two
   elements — so it read past the end inside `cross3`. It has no callers and
   never ran; under numba that read memory instead of raising.
6. **`olga_greedy.py` is done, and the port found a wrong answer that had been
   shipping.** The FRET experiment-planning weight is the chi-squared
   right-tail, `Q(nu/2, chi2/2)`. Olga takes its closed-form expansion from
   Boost, whose half-integer branch loops `for (n = 2; n < a; ++n)` with `a` a
   half-integer; the port wrote `range(2, int(a))`, and `int(2.5)` is `2` — so
   it ran **one term short for every odd `ndof`**, returning `0.3903934` where
   the truth is `0.6987524`. `ndof` is the number of pairs chosen so far, so it
   is odd on every other greedy step, and this weight is precisely what decides
   which pair looks most informative. Fixed, vectorised, and checked against
   `scipy.special.gammaincc` over `ndof` 1..1001 (`4e-15`).

   Three things worth carrying forward:
   - **`scipy.special.gammaincc` is the same function but must not carry the
     common path** — it is general-purpose and measured **18× slower** end to
     end on the `(candidates, n, n)` arrays. It settles *correctness*; the
     few-term series carries *speed*. The one place it is now used is `a > 100`,
     where Olga substituted a normal approximation good to only `1.3e-2` and the
     series would need ~200 terms.
   - **Cost of the port: 2.9–4× slower** (0.035→0.140 s at 60×120, 0.461→1.327 s
     at 120×300). Accepted because this is a one-shot planning wizard, not a fit
     loop — and it removes a `parallel=True`, the decorator that latches
     `NUMBA_NUM_THREADS`. If it ever needs to be fast, the route is `tttr-c`.
   - **I wrote the in-place-scaling bug myself** while chasing that gap:
     scaling `chisq` by a half with `out=` halved the *caller's* chi-squared
     accumulator, so the decay curve stopped decaying while the selection still
     looked plausible. It is the same defect this project filed against a
     library's CDF sampler. Pinned now by
     `test_the_weight_does_not_modify_the_chi_squared_it_is_given`.

   Pre-existing and **not** caused by this: six failures in
   `plugins/modelling/fret/test/test_examples.py` (olga example JSON, AVs on
   PDB, project save/load, CLI info, FastAPI endpoints), verified identical with
   `HEAD`'s file swapped back in.
7. **ndxplorer is numba-free, and both files came off the list without a
   kernel being ported.** `utils/performance_optimizations.py` kept a
   `try: import numba` whose `nb` and `_HAVE_NUMBA` were referenced nowhere, plus
   `compute_histogram1d_adaptive` / `Histogram1DComputation` with **zero callers**
   and a `used_numba` field hard-coded `False`. All deleted.

   Committed in the nested repo as `db52784`, necessarily carrying a peer's work
   with it: `modules/ndxplorer` is a separate repository, and their uncommitted
   removal of the numba histogram kernels is what made the `nb` import dead.
   Neither half imports alone, so the file could not be split.

   **The "zero callers" claim was wrong the first time, and how it was wrong is
   the point.** `compute_histogram1d_adaptive` *did* have a caller —
   `compute_histograms_parallel`, in the same file, which the grep had excluded
   in order to skip the definition. Deleting the callee alone would not have
   raised: the call sits inside a `try`/`except` that logs a warning and falls
   back, so it would have degraded **silently** to the fallback. Both are gone
   now, together, after checking neither has a caller in either repository.
   **Grep the file you are editing, not only the rest of the tree.**

   `utils/vectorized_ops.py::digitize_parallel` is **deleted**, not ported —
   and the route I first gave it was wrong. I re-routed it `numpy` → `tttr-c` to
   protect "ndxplorer's interactive redraw path", which I never checked: grepping
   for callers found **none anywhere in either repository except the function's
   own tests**. Nothing in ndxplorer digitizes at all; binning happens inside
   `utils/fast_histogram`, which is tttrlib's C++ fill. The accelerator was
   carrying a function the application never called.

   **That is the same mistake twice in one file** — asserting a caller
   relationship from a grep that excluded the place the caller actually was, then
   from no grep at all. Both times the wrong answer was the comfortable one
   (delete it / keep it fast). Check callers before routing, not after.

   The measurement is kept in the source as a comment so the kernel is not
   rebuilt on the same reasoning. 2,000,000 points:

   | | 64 bins | 512 bins |
   | --- | --- | --- |
   | numba `prange` binary search | **7.2 ms** | **20.1 ms** |
   | uniform-bin arithmetic + rounding correction | 68.9 ms | 88.3 ms |
   | `np.searchsorted(side='right')` | 111.4 ms | 275.5 ms |
   | `np.digitize` | 168.5 ms | 139.4 ms |

   All four agree **exactly**, including `NaN` and `±inf` (`np.digitize` on
   increasing bins *is* `searchsorted(side='right')`). The uniform-bin
   arithmetic path is exact too — verified over 400 randomised trials that place
   points on every bin edge and on both `nextafter` neighbours of each — but its
   rounding correction needs two full-array gathers, and that is where the time
   goes. This is ndxplorer's interactive redraw path (2 M points), so 4-10× is
   not affordable.

   tttrlib has no digitize to delegate to — `histogram*`, `bincount1D` and
   `make_bin_edges_double` all *count*, none returns a per-point bin index — but
   none is needed: the binning ndxplorer actually does happens inside the
   histogram. **No new compiled kernel is required, and none should be written.**

   **The settings surface is gone too** (`6593d06`): the
   `Use Numba JIT Compilation` checkbox, `NDXPLORER_USE_NUMBA`, the
   `use_numba` config field and the key in the shipped `mfd.settings.json`, the
   `use_numba` parameters on `fast_histogram_1d/2d` documented as "accepted and
   ignored", and the stale claims that `performance.py` "uses Numba acceleration
   when available". A checkbox controlling nothing is not dead code — it is a
   false statement to the user, who toggles it and concludes the setting does
   not help rather than that it does not exist. Verified with the before/after
   grab pair: exactly one control lost, no gains, layout intact.

   **The verification that mattered was rendering from an isolated
   `git worktree`, not from the shared tree.** Doing so caught a real break in
   `db52784`: it deleted `compute_histogram1d_adaptive` after a caller check run
   against the *working tree*, where a peer had already dropped the import —
   at `HEAD` the import was still there, so the committed tree raised
   `ImportError` on any `ndxplorer.ui` import. Fixed in `cbebc9c`.
   **A working tree containing other people's uncommitted work does not verify
   your commit**; `git worktree add --detach <sha>` to a scratch path does, and
   costs one command.
8. **`kappa2.py` closes Route 1, and blocking is what made it win.** All four
   kernels are NumPy and the `k2` grids are **bit-exact**; the histograms differ
   by `3e-14` relative, from summation order alone. Timings (median of 7):

   | | numba | NumPy |
   | --- | --- | --- |
   | `kappasq_all(20000)` | 20.8 ms | **9.6 ms** |
   | `kappasq_all_delta(step=0.25)` | 72.1 ms | **60.0 ms** |

   `kappasq_all_delta` was **269.9 ms** written as one flat `(360, 1440)` grid —
   *worse* than numba — and became 60 ms by **blocking the beta1 rows 32 at a
   time**. `kappasq` allocates about a dozen temporaries the size of its input,
   so the one-shot form streams ~4 MB through cache a dozen times over. That is
   the same lesson as `linalg` from the other side: vectorising is necessary but
   the working set still has to fit.

   Two details worth not re-deriving:
   - **The RNG order can be preserved exactly.** `np.random.randn(n, 2, 3)` in C
     order is the same sequence as alternating `randn(3)` draws inside a loop,
     so `kappasq_all` reproduces the per-sample result under a fixed seed rather
     than only in distribution. (Parity must be checked against the *un-jitted*
     original — numba's `np.random` is a separate stream.)
   - **A caught `ZeroDivisionError` was load-bearing and is gone.**
     `calculate_kappa_distance` logged a skipped frame by catching the exception
     a degenerate dipole raises — which only worked while the kernel was
     compiled, because `nopython` raises where NumPy returns `nan` and warns.
     The NaN reached the output either way, so the arrays stayed right and
     **only the log line silently stopped**. Now the result is tested for
     finiteness, which is what the caller meant and does not depend on which
     layer does the arithmetic. Watch for this shape elsewhere: numba raising on
     `0.0/0.0` is a behavioural difference no parity test on values will catch.
9. **A `tttrlib` route is a hypothesis, not a verdict — diff the maths first.**
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
10. **`_hdbscan.py` splits — measured, so do not re-derive.** The compiled
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
11. **`gopich_szabo.py` has a red test that is not the port's fault.**
   `test_no_exchange_reduces_to_a_static_mixture` returns `-inf` where
   `-3.665` is expected — `-inf` is the numba kernel's own numerical-failure
   sentinel. Check whether `tttrlib.GopichSzabo` gives the expected value
   *before* debugging the kernel that is about to be deleted. Recorded in
   [known-issues](../references/known-issues.md) with four unrelated
   `mfd_burst_roundtrip` failures, so the retirement's test runs are not read
   as having caused them.
12. **ChiMOL is out of scope and out of the guard.** `test_numba_seam.py` skips
   `chisurf/plugins/chimol/` via `_EXCLUDED_PREFIXES`, and the allow-list no
   longer names those files. They belong to the WebGPU port; when it lands
   them, nothing here needs touching.

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

## The HMM fixture is anchored to hmmlearn, not only to ourselves

**USER RULE (2026-08-11): use hmmlearn as the reference.** A fixture recorded
from our own numba kernels only proves a port matches *us* — and the first
version of this one encoded a live bug (below). `core/math/hmm.py` replaced
hmmlearn, so hmmlearn is the independent oracle for exactly these recursions.

Measured over all ten fixture cases
(`build_tools/dev_utils/hmm_lattice_fixture.py`, run by hand):

- **forward and backward lattices are bit-identical** — `0.0` difference, not
  "within tolerance". Same recursion, same order.
- log-likelihoods agree on every case, including the two that are `-inf`.
- posteriors ≤ `3.1e-14`, `xi_sum` ≤ `6.8e-13` — accumulation-order noise only:
  we fuse the backward sweep with the posterior and transition-count
  accumulation where hmmlearn makes three passes.
- Viterbi paths are identical **wherever a path exists**. They diverge only in
  the two cases where the sequence is impossible, and there every candidate
  scores `-inf`, so the arg-max is arbitrary — both implementations report the
  meaningful part (`-inf`) and differ only on which labels to emit. A port
  should assert the log-probability there and **not** the path.

hmmlearn stays a **developer** tool: it is not in the manifests, nothing
shipped imports it, and it is deliberately not an `importorskip` in the suite —
that becomes a skip on any machine without it, and a skip reads like a pass.
The committed artifact is the `.npz`; the script regenerates and re-checks it.

Two hmmlearn API traps, both of which return confident nonsense rather than
raising, and both of which cost a run: `_hmmc.forward_log`/`backward_log`/
`viterbi` take `startprob` and `transmat` as **plain probabilities** (only the
frame probabilities are logged), so passing logs makes every log-likelihood
`nan`; and `_hmmc.viterbi` returns `(logprob, states)`, not the reverse.

## 2D-FLC is a tttrlib candidate, specified against the original MATLAB

**USER INSTRUCTION (2026-08-11).** `plugins/fcs/flc_2d/core.py` moves to route
`tttrlib` as a **candidate** — the compiled equivalent does not exist yet, so
this is a specification rather than a delegation. It is specified by
**tttrlib PRD-036** (`okf/prds/PRD-036-2d-flc-photon-kernels.md` in that repo);
the link is deliberately a path rather than a relative link, because the two
repos are siblings and a relative link resolves in neither.

Five kernels move: `_fdc_scan_log_kernel`, `create_2d_fdc_numba_int`,
`_log_bin_int` and the two `_ceil_div_*` helpers. The inversions (Tikhonov,
MEM, the rate-matrix fit) are already NumPy/SciPy and stay here — this is only
the photon pass, which touches macro and micro times together and does a binary
search per lag window, the shape numba was compensating for.

**Written against the reference, not against our own code.** The original is
Toru Kondo's MATLAB in `junk/2D-FLC-code` (Schlau-Cohen lab, MIT), with *A
Technical Note on 2D-FLC.pdf*. ChiSurf's kernel is already a faithful port of
`TK_Create2DFDC_04.m` — same lin/log matrix pair, same log-tick construction
`t_Imax^(j/(L-1))·tStep − tStep`, same `dT ± ddT/2` window — so the C++ has a
third implementation to agree with rather than only ours. Files read are marked
with `CHISURF-REVIEWED` headers pointing at the PRD.

**Everything in it is tested by simulation**, which is the user's requirement
and the PRD's spine: `TK_MyMain_Simu_PhotonStream.m` prescribes the generator
(N states with per-state cps and lifetime, an interconversion rate matrix, an
IRF for the micro-time, `Tstep = 1e-6 s`, `tstep = 0.004 ns`), and its default
case — **two states, 1 ns and 2 ns, 10 s⁻¹ both ways, equal intensity** — is the
recovery target. ChiSurf already ports that generator as
`flc_2d.api.simulate_stream`. The PRD requires the negative control too (a
single state must produce no cross-peak at any lag), because without it a kernel
that fabricates correlation passes every positive test.

The lesson PRD-035 paid for is why: a fixture recorded from the code being
replaced cannot tell a faithful port from a shared mistake. Simulation with a
known answer can.

## The `imp` route is a re-expression, not a deletion — checked, not assumed

**Scoped as [PRD-100](../prds/prd-100.md)** (2026-08-11): three groups that
should land separately, the consumers that must not move, and a parity bar that
is not "the tests pass" — those were written against the current
implementation.

**2026-08-11.** The route text said these files "already migrated to imp-tricks
under the same function names" and the label said "delete the leftover". Neither
is true, and the check is one import:

| ChiSurf symbol | in `IMP.bff` / `IMP.cgmol` / `IMP.bff.cgdye`? |
|---|---|
| `centroid2`, `internal_potential`, `lj_calpha`, `gb`, `go` | no |
| `make_grid_axis`, `find_atom_clashes`, `define_starting_positions`, `distance_lookup`, `calc_linker_distance` | no |
| `_quenching_rate_per_frame` | no |

Nothing matched, exactly or fuzzily, and `~/dev/imp.bff` (the fourth repo
PRD-93 created) does not carry them either.

The route is right in **direction**: `IMP.bff.AV` is a real accessible-volume
decorator (`get_linker_length`, `get_map`, `get_mean_position`,
`create_path_map_header`) and `IMP.cgmol` has `ProteinCentroid`. But ChiSurf's
kernels are the *internals* of an AV calculation, so this is re-expressing
ChiSurf against a different API and proving the volumes still agree — not
deleting a duplicate. Different work, and much more of it.

**`potentials.py` is the clearest counter-example**: `GoPotential`,
`HPotential` and `Ramachandran` are live behind `proteinmc`, the ProteinMC model
and three GUI widgets, and `IMP.bff` exposes only `AVNetworkRestraint`. There is
nothing to delegate to today.

**Do not start this without checking `protein.py` first** — a peer is mid-change
in it for PRD-97 (`Hand fret/core's algorithms to IMP.bff.fret`), 159 uncommitted
lines, and that work may settle where these belong.

This is the fifth route label corrected by checking rather than reading, after
`dcd.py`/`xtc.py` (no trajectory reader in imp-tricks), `hmm.py` (a different
algorithm) and `av/dynamic.py` (does not vectorise). The pattern is consistent
enough to state as a rule: **the route tag is a hypothesis written when the file
was catalogued, and the first step of any entry is re-checking it.**

## flc_2d cannot leave the list yet, and the reason is recorded so nobody re-checks

**2026-08-11.** tttrlib PRD-036 landed its side (`fdc_scan_log`, `fdc_log`), and
its `fdc_scan_log` **agrees exactly with our numba kernel on all nine recorded
cases** — including a lag inside the window half-width, a narrow gate, an empty
gate, and a 1.05M-pair dense stream. Fixture:
`test/data/numba_parity/flc_2d_fdc.npz`, pinned by
`plugins/fcs/flc_2d/test/test_fdc_parity.py`. Performance at 1M photons /
20 lags / 100 bins, interleaved A/B best-of-4: **1.14× faster** than numba
(1.01× at 200k).

**What blocks the strike**: `create_2d_fdc_numba_int` returns
`(mat_lin, lint_axis, mat_log, logt_axis)` and the **linear-binned** matrix has
no upstream equivalent. It is live — `flc_2d/fit/helpers.py` returns
`np.diag(mat_lin)` as the linearly-binned decay and `api.two_d_fdc` hands
`mat_lin` to callers — and it is **not** recoverable from the log matrix,
because log binning collapses many micro-time channels into one bin. PRD-036
originally claimed the opposite; that claim was written before the call sites
were checked and is corrected there.

**That gap is closed** (2026-08-11): tttrlib has `fdc_scan_axis`
(caller-supplied tick array) and `fdc_scan_two_axes` (both matrices from one
walk, which is what `create_2d_fdc_numba_int` does). The A/B that justified the
two-axis form: at comparable bin counts and 1M photons, one axis is 144.8 ms and
two axes in two calls 329.1 ms — the second pass is a full pass, not noise.

**What now blocks the delegation is not code but two method decisions**, both of
which change numbers users have published, and both recorded in
[known issues](/references/known-issues.md):

1. **Which `t_imax` the log axis uses.** The builder couples it to
   `lint_bin_factor` (faithful to the MATLAB); the scan uses `span + 1` and does
   not. They disagree for any factor > 1.
2. **Whether the linear matrix's trim is removed.** It slices its last row and
   column on return, dropping 654 pairs at factor 3 and 974 at factor 5 against
   a brute-force count of 6443.

They are the same derivation and should be settled together, by whoever owns the
method. **Then** the delegation lands in one change: all five kernels via
`fdc_scan_two_axes`, the allow-list line, and the parity fixture regenerated
against whichever axis is chosen. Do not delegate before that — the fixture
would pin the axis that is about to change.

**Measurement caution worth keeping**: the first benchmark of this pair ran the
two implementations *sequentially* and reported tttrlib 21% slower. Interleaved
A/B/A/B, best-of-4, it is 14% faster. A sequential timing of two kernels on the
same data is a thermal/ordering measurement, not a performance one.

## flc_2d delegation: three gaps found, two closed, one open (2026-08-11)

Worked in order; each was found by comparing against the recorded fixture rather
than by reading, and each is recorded so the next attempt starts past it.

1. **No linear matrix upstream** — closed. `fdc_scan_axis` takes a caller-supplied
   tick array and `fdc_scan_two_axes` produces both matrices from one walk, which
   is the shape `create_2d_fdc_numba_int` needs. Justified by measurement: at
   comparable bin counts and 1M photons, one axis is 144.8 ms and two axes in two
   calls 329.1 ms, so the second pass is a full pass.
2. **The log axis ignored `lint_bin_factor`** — closed, both sides.
   `fdc_t_imax(span, factor)` upstream; `_fdc_scan_log_kernel` here.
3. **The micro-time gate differs** — **OPEN, blocks the strike.** The reference
   gates on `t_Imax`, not on `tMax`:

   ```matlab
   if (tauI <= 0) || (tauI >= t_Imax)      % TK_Create2DFDC_04.m:66
   ```

   and `t_Imax = lint_Imax * lint_BinFactor` is ≥ the span, so photons **above
   `tMax`** are admitted whenever the span is not a whole number of linear bins.
   ChiSurf's builder is faithful to that. tttrlib's `fdc_scan_two_axes` gates at
   `t_max`, so it counts fewer pairs: on the narrow-gate fixture case (gate
   `[15, 25]`, factor 4, `t_imax` 16) it returns **432 pairs against 972**, with
   63 of 400 cells differing. The other three fixture cases agree exactly,
   because their gate is `[1, 40]` with no micro-times above 40 — so nothing
   falls in the excess range and the difference is invisible.

   That last point is why this is worth writing down: **a gate difference only
   shows up when the data reaches past `tMax`**, so a fixture built from
   well-behaved streams will not catch it.

**Do not delegate until the gate matches.** Raised upstream. When it does, the
delegation is: `_fdc_scan_log_kernel` → `fdc_scan_axis`, `create_2d_fdc_numba_int`
→ `fdc_scan_two_axes` (log ticks length `logt_imax_in + 1`, linear ticks
`[-1, 0, f, 2f, …]`, then the reference's one-bin trim in Python), and the three
helpers deleted.

## `gopich_szabo.py` is done — the fallback outlived the defect (2026-08-11)

Both kernels delegate to the photon library's `GopichSzabo`; `import numba` is
gone. The file kept a numba copy **solely** because `set_scheme` used to reject
any scheme with a repeated zero eigenvalue — the no-exchange limit, or a state
that does not exchange. **That defect was fixed upstream and nobody told
ChiSurf.** The warned fallback is what made the reason findable at all, which is
the argument for warning rather than falling through silently.

Verified before deleting: five schemes (connected fast/slow, no exchange,
one-way, asymmetric) plus a sparse 80×8-photon set, agreeing to 6.8e-13 – 2.8e-10
in log-likelihood and on **every one of 3040 Viterbi states**. Pinned by
`test/fluorescence/test_gopich_szabo.py::test_the_delegation_returns_what_the_numba_kernels_returned`.

**Two things the delegation had to keep, and one nearly lost:**

- **`-inf` is reserved for a model with no likelihood** — a defective,
  non-diagonalisable generator — and that decision stays in ChiSurf, *before*
  the engine is asked. A setup failure is a different thing; conflating them is
  how the no-exchange limit once reported "forbidden" for a perfectly well
  defined likelihood. The first version of this delegation dropped that check
  and `test_a_defective_rate_matrix_backs_the_optimiser_off` caught it.
- **`offsets` is correctness, not an optimisation.** Upstream measured the leak
  at τ = 250 s: an entire 30-photon burst still dragged at a gap of 5e5 s — two
  thousand relaxation times — because Viterbi maximises a path rather than
  marginalising. "Our bursts are well separated" is not a defence.

A refusal now raises `ValueError` instead of falling back. The rewritten test
forces a refusal to pin that, since a library build that refuses this scheme no
longer exists.

## Bugs the ports have found

* **The whole 2D-FLC plugin was failing to compile its kernels**, found by
  taking `flc_2d/api.py` off this list. ChiSurf's `env_bootstrap` rewrites
  `NUMBA_NUM_THREADS` from settings (`numba_num_threads: "auto"` = cores − 1),
  and it can do so *after* numba's pool has launched. numba re-reads that
  variable on **every cold compile** and raises when it no longer matches, so
  the first kernel compiled afterwards died with *"cannot set NUMBA_NUM_THREADS
  to a different value once the threads have been launched (currently have 7,
  trying to set 8)"* — a message pointing at threading rather than at the
  setting that moved. Its whole test suite was red (5 of 6 in one file) and it
  reproduced 3/3, so it was not flaky. The H2MM engine has carried a
  `_sync_numba_threads` guard for exactly this since it hit the same wall;
  `flc_2d/core.py` now has one too, and the suite is 26 passed. **Any module
  that compiles numba kernels lazily needs this** — the crash lands on whoever
  compiles first after the rewrite, which is a matter of import order.

* **An impossible sequence turned the whole HMM transition matrix into `nan`**,
  found while recording a parity fixture for PRD-035 — not by any test, and not
  by the port itself, which had not started. `_backward_posteriors_xi` scales
  its transition counts by `exp(maximum + fwd[t, i] - log_prob)`; when the
  sequence is impossible that is `exp(-inf + -inf - -inf)` = `exp(nan)`. Since
  `xi_sum` is the accumulator **shared by every sequence** in `_do_estep`, one
  unexplainable frame poisoned the entire transition matrix for that EM
  iteration, then the M-step, then every iteration after it. It hid because the
  *posteriors* survive — their uniform fallback triggers on the `nan` total and
  returns clean numbers — so the only visible symptom was a model that stopped
  improving. Fixed by contributing zero counts for an impossible sequence,
  which is the correct answer rather than merely a finite one; pinned by two
  tests in `test/math/test_hmm.py`. **The fixture handed to PRD-035 is the
  fixed output**: recording it first would have required the C++ to reproduce
  the bug.

* **The acquisition dock drew three widgets on top of each other**, found by
  screenshotting the panel while porting its decoder — not by any test. The
  output-folder row, the Save/Load buttons and the whole "Show" group box were
  all added at grid row 4, and `QGridLayout` silently stacks overlapping cells
  rather than complaining: "Fluorescence Decays" and "Count Rate" were behind a
  line edit, "Save Settings" on top of "Correlation Curve". Fixed by moving the
  group to row 5 and pinning the spare vertical space to the empty row above
  the status bar, so five checkboxes no longer occupy a group box taller than
  the controls it belongs to. This is what the screenshot rule is for: nothing
  raised, nothing failed, and the panel had presumably looked like that for a
  long time.

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
| Ported so far | 30 | ~79 |
| Remaining | 18 | ~76 |
| ChiMOL (excluded, owned elsewhere) | 11 | 29 |

Done: `fluorescence/general.py`, `math/datatools.py`, `math/statistics.py`,
`math/signal.py`, `fluorescence/burst/utils.py`, `math/reaction/_reaction.py`,
`fluorescence/tcspc/convolve.py`, `fluorescence/tcspc/corrections.py`,
`fluorescence/tcspc/tcspc.py`,
`plugins/fluorescence_decay/maxent_decay/core/solver.py`, and the three LLTF
modules, which now re-export the shared implementations instead of copying
them.
