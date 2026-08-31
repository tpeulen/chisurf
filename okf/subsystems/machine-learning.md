---
type: Subsystem
title: "Machine learning estimators"
description: chisurf.core.ml — the in-tree replacements for the six scikit-learn estimators the tree used (GaussianMixture, KMeans, PCA/IncrementalPCA, StandardScaler, MLPRegressor, HDBSCAN), mirroring scikit-learn's layout and spelling, with the density-clustering kernels compiled in the photon library.
resource: chisurf/core/ml/
tags: [subsystems, ml, clustering, dependencies, math, burst-selection, ndxplorer]
timestamp: '2026-08-10T00:00:00Z'
---

# Machine learning estimators

`chisurf/core/ml/` holds every statistical estimator the tree reaches for. It
exists because the alternative was a large third-party dependency installed for
six classes — and because the tree had already written most of them anyway, as
private helpers inside a module about something else.

# Where to pick this up

The port is **complete**: nothing in `chisurf/` imports scikit-learn, the
package is struck from every manifest, and a guardrail
([`test/test_no_retired_dependency_imports.py`](/../test/test_no_retired_dependency_imports.py))
fails if it comes back. What is worth knowing before touching it:

1. **Steps 1 and 2 are the photon library's and are required.** There used to be
   a second implementation of both here — an `O(n²·d)` brute-force core distance
   and an `O(n²)` Prim spanning tree — selected by a `hasattr` probe. They were
   *bit-identical by construction*, and that was verified on real photons
   (max |Δ| = 0 in core distance, in every MST edge weight and in the edge set,
   on 500 and 2000 photons of `BH_SPC132.spc` at `min_samples` 3/5/10) before
   they were **deleted on 2026-08-31** for being 700–3000× slower and never
   exercised. They are called directly, with no capability check in front of
   them, so a library that lacks them fails on the attribute. Two things
   still make the answer reproducible and both are easy to undo: the edge order
   is **total** (weight, then the sorted endpoint pair) rather than by weight
   alone, and the compiled translation unit is built with `-ffp-contract=off`.
   Removing either changes cluster counts silently. The guards are now
   independent rather than parity: SciPy's `minimum_spanning_tree` over an
   explicit mutual-reachability matrix, the distance matrix's k-th column, and a
   check that `alpha` actually moves the tree.
2. **Ties are the whole story in HDBSCAN.** A mutual-reachability weight is
   frequently a *core distance*, and one core distance is the weight of every
   edge it dominates, so hundreds of edges share a value and the minimum
   spanning tree is not unique. This is why parity with scikit-learn is exact in
   five dimensions and approximate in one: not an error, a different choice
   among equals. The sharp parity assertion is
   `test_only_tied_weights_can_make_the_two_differ` — feed scikit-learn's own
   dendrogram in and the labels and probabilities match exactly, for every
   configuration and every dimension.
3. **The candidate comparison happens in distance space, and moving it there
   was a bug fix, not a tidy-up.** The fast form — accumulate the squared
   distance and stop once it passes `(best × alpha)²` — is wrong at exactly the
   values this depends on, because `best` is itself a square root and
   `sqrt(x) · sqrt(x)` is not `x`. An edge that *ties* then reads as one unit in
   the last place too far and is skipped, the endpoint tie-break never sees it,
   and the kernel returns a different — perfectly valid — spanning tree. It hid
   for a while because the kernels still agreed on most fixtures; the guard is
   now swept over several shapes, sizes and seeds.
4. **There is no dimension crossover any more, and the history matters.** Prim
   used to be faster than Borůvka above about ten features, and the code
   dispatched between them. Once the comparison moved into distance space —
   which also removed the squaring from the inner loop — Borůvka won at every
   dimension measured, up to thirty-two, so the dispatch is gone. `mst_prim`
   stays as the obviously-correct kernel the fast one is checked against, and
   `default_leaf_size` still varies with the dimension.
5. **Three things were implemented against the reference, measured, and
   removed.** All three are recorded in the source, because each is the kind of
   idea someone re-derives:
   - a **dual-tree traversal**, which prunes the query side as well and is what
     keeps the reference implementation fast in high dimensions. Correct, and
     slower here at every dimension, for a reason unrelated to the traversal:
     its candidate edges are shared mutable state across one recursion, so it
     runs on one core while the per-point search uses eight.
   - a **brute-force neighbour search** above the old crossover — slower than
     the tree even at sixteen dimensions. The tree stops paying for the
     *spanning tree* long before it stops paying for the *neighbour search*.
   - a **parallel Prim**: an OpenMP barrier per round costs more than the round
     it separates, and a spin barrier, though faster in isolation, burns every
     core for the duration, which a library called from a GUI must not do.
6. **`parallel=True` is banned in this package.** A numba kernel with
   `parallel=True` launches numba's thread pool on first call, after which
   `NUMBA_NUM_THREADS` can no longer be set — and the settings bootstrap sets it
   from a preference. The Python kernels that remain (the condensation and
   labelling, steps 3 and 4) are single-threaded on purpose; the compiled path is
   where the threads are.

## What is here

| Estimator | Mirrors | Notes |
|---|---|---|
| `GaussianMixture` | `sklearn.mixture` | four covariance types, `n_init`, `aic`/`bic`, `score_samples`; **extra**: `fix_means` / `fix_covariances` masks, which the library cannot do and which a companion tool had written its own EM for |
| `KMeans` | `sklearn.cluster` | k-means++ seeding and Lloyd iterations, shared with the HMM's initialisation |
| `HDBSCAN` | `sklearn.cluster` | core distances → mutual-reachability MST → condensed tree → excess of mass; accepts the standalone package's `prediction_data` and ignores it |
| `PCA` / `IncrementalPCA` | `sklearn.decomposition` | covariance eigendecomposition and batch moments, `svd_flip` sign convention |
| `StandardScaler` | `sklearn.preprocessing` | `fit`/`transform`/`inverse_transform` |
| `MLPRegressor` | `sklearn.neural_network` | Adam with early stopping; keeps the `coefs_`/`intercepts_`/`out_activation_` names the surrogate's JSON export reads |

The layout mirrors scikit-learn's package structure and public spelling, so
porting a call site is an import line and someone arriving from the library's
documentation finds the attribute they expect.

## HDBSCAN, in four steps

Density-based clustering with no density threshold to choose: the hierarchy over
*all* thresholds is built once and the flat clustering read off it by keeping
whichever clusters persist over the widest range.

1. **Core distance** — distance to the `min_samples`-th neighbour, the local
   density estimate. `min_samples` counts the point itself, as in scikit-learn;
   the standalone package excludes it, so its `min_samples=5` is this one's `6`.
2. **Mutual-reachability MST** — edge weight `max(core_i, core_j, d(i, j))`, the
   distance inflated so sparse regions cannot be crossed cheaply. This is where
   the time goes, and it is the photon library's Borůvka.
3. **Condense** — a split that sheds fewer than `min_cluster_size` points is not
   a split, it is the parent losing noise.
4. **Select** — excess of mass (keep a cluster when it is more stable than its
   descendants together) or the leaves.

Steps 3 and 4 are integer bookkeeping over `O(n)` records and stay in NumPy and
numba; they are not the cost.

## The compiled kernel

`modules/math/{include/Cluster.h,src/Cluster.cpp}` in the photon library: a
k-d tree with k-nearest-neighbour queries and a Borůvka minimum spanning tree
over the mutual-reachability graph, with Prim beside it as the
obviously-correct kernel the fast one is checked against. It is there rather
than here because a k-d tree over an `(n × d)` table is wanted in several places
at once — burst feature spaces, localisation tables, density clustering — and
one implementation is the point.

Three optimisations carry the Borůvka, and removing any of them costs an order
of magnitude:

* **Nearest-child-first descent.** A depth-first traversal that does not go
  towards the query point first establishes no bound and walks the whole tree.
* **Seeding from the cached neighbours.** The k nearest neighbours are already
  known from the core-distance pass; any real edge is an upper bound, and a
  point's own neighbours are the tightest one available.
* **A bound shared by the whole component**, not one per point — taken from the
  reference implementation (annotated in `junk/hdbscan/`). The first short edge
  any member of a component finds prunes the search for every other member, and
  it enables two scalar tests that skip work outright: a query point whose own
  core distance exceeds the component bound cannot contribute at all, and
  neither can a reference point whose core distance does. Read racily across
  threads on purpose: the bound only ever decreases and is only used to prune,
  so a stale read costs a little work and cannot change the answer — the winning
  edge is chosen by an exact reduction afterwards.

Two further optimisations were implemented, measured, and **reverted**, and both
for the same reason:

* **Carrying each point's candidate across rounds.** Valid only while every
  point's stored edge is that point's *own* minimum, which the shared component
  bound breaks — a point may stop early against someone else's edge. The two are
  mutually exclusive and the shared bound is much the stronger.
* **The reference implementation's free first round.** For a point `i`, every
  edge weighs at least `core[i]`, so a neighbour `j` with `core[j] <= core[i]`
  gives an edge of exactly `core[i]` — provably minimal, no search needed. It
  works and it is fast, and it produced a **different spanning tree from the Prim
  kernel** on the same data. Both are valid; only one can be this library's
  answer. A shortcut whose agreement with the total edge order cannot be
  established does not get to decide which.

Performance against the packages this replaced is tracked in
[benchmarks](/../docs/development/benchmarks.md).

## Where it is used

* `chisurf/plugins/burst/burst_selection/` — the Gaussian mixture over burst
  features, in one dimension over a histogrammed feature and in five over the
  feature matrix.
* `chisurf/plugins/burst/burst_h2mm/core/surrogate.py` — the MLP and the scaler;
  its JSON export is read by a C++ engine, so the attribute names are a
  compatibility surface, not an internal detail.
* `chisurf/core/math/hmm.py` — the k-means initialisation and the Gaussian
  log-density, shared rather than copied.
* The photon-data exploration companion — k-means, PCA/IncrementalPCA, HDBSCAN,
  and the constrained mixture.

See also: [hidden Markov models](hidden-markov-models.md) for the module these
estimators used to hide in, [compiled modules](compiled-modules.md) for the
build side, and [PRD-87](/prds/prd-87.md) for the design record.
