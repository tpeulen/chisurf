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

1. **The clustering answer must not depend on which kernel ran.** There are two
   implementations of the mutual-reachability spanning tree — a compiled
   k-d-tree Borůvka in the photon library and a numba Prim here — and they are
   *bit-identical by construction*, not by coincidence. Two things enforce that
   and both are easy to undo: the edge order is **total** (weight, then the
   sorted endpoint pair) rather than by weight alone, and the compiled
   translation unit is built with `-ffp-contract=off`. Remove either and the two
   paths start returning different cluster counts on the same data, silently,
   depending on whether the compiled kernel happened to be importable.
2. **Ties are the whole story in HDBSCAN.** A mutual-reachability weight is
   frequently a *core distance*, and one core distance is the weight of every
   edge it dominates, so hundreds of edges share a value and the minimum
   spanning tree is not unique. This is why parity with scikit-learn is exact in
   five dimensions and approximate in one: not an error, a different choice
   among equals. The sharp parity assertion is
   `test_only_tied_weights_can_make_the_two_differ` — feed scikit-learn's own
   dendrogram in and the labels and probabilities match exactly, for every
   configuration and every dimension.
3. **The crossover between the two MST kernels is measured, not guessed.**
   A k-d tree prunes while the bounding boxes are tight; past about ten
   dimensions it visits most of itself on every query and the textbook `O(n²)`
   Prim wins outright (3× at sixteen dimensions). `KDTree::tree_is_worthwhile`
   is that dividing line and `default_leaf_size` the matching leaf size. Two
   things were tried above the crossover and **reverted**: a brute-force
   neighbour search for the core distances (slower than the tree even at
   sixteen dimensions — the tree stops paying for the *spanning tree* long
   before it stops paying for the *neighbour search*), and a parallel Prim
   (an OpenMP barrier per round costs more than the round; a spin barrier was
   faster in isolation but burns every core for the duration, which a library
   called from a GUI must not do).
4. **`parallel=True` is banned in this package.** A numba kernel with
   `parallel=True` launches numba's thread pool on first call, after which
   `NUMBA_NUM_THREADS` can no longer be set — and the settings bootstrap sets it
   from a preference. The fallback kernels here are single-threaded on purpose;
   the compiled path is where the threads are.

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
   the time goes and where the two kernels live.
3. **Condense** — a split that sheds fewer than `min_cluster_size` points is not
   a split, it is the parent losing noise.
4. **Select** — excess of mass (keep a cluster when it is more stable than its
   descendants together) or the leaves.

Steps 3 and 4 are integer bookkeeping over `O(n)` records and stay in NumPy and
numba; they are not the cost.

## The compiled kernel

`modules/math/{include/Cluster.h,src/Cluster.cpp}` in the photon library: a
k-d tree with k-nearest-neighbour queries, a Borůvka minimum spanning tree over
the mutual-reachability graph, and a Prim fallback above the dimension
crossover. It is there rather than here because a k-d tree over an `(n × d)`
table is wanted in several places at once — burst feature spaces, localisation
tables, density clustering — and one implementation is the point.

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

The gap that remains is the reference implementation's **dual-tree traversal**,
which propagates a bound up the *query* tree as well. That is why it is still
ahead above roughly ten features — and why the MST switches to Prim there
instead.

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
