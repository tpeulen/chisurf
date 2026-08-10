---
type: PRD
prd: "87"
title: "PRD-87: chisurf.core.ml — the four estimators the tree actually uses, and the end of scikit-learn"
description: scikit-learn is installed for four estimators reached from five files, and the tree already contains most of them as private helpers inside the HMM module. This PRD extracts them into one sklearn-shaped namespace so the call sites change by an import line, absorbs the constrained EM the companion exploration tool wrote because scikit-learn could not do it, and names HDBSCAN as the one algorithm that is genuinely new work.
status: in-progress
phase: "stages 1-4 implemented (chisurf-side done; companion tool call sites re-pointed); stage 5 (HDBSCAN) deliberately deferred and scikit-learn+manifest removals gated on it"
resource: chisurf/core/ml/
tags: [prd, dependencies, math, ml, gmm, kmeans, pca, burst-selection, h2mm, ndxplorer]
timestamp: '2026-08-07T00:00:00Z'
updated: '2026-08-09T00:00:00Z'
---

# Where to pick this up

**Implemented (2026-08-09): stages 1–4.** `chisurf/core/ml/` exists with the
full layout; all three burst-selection call sites import it; the HMM shares the
kmeans + Gaussian density implementations; the companion tool uses
`chisurf.core.ml` for KMeans/PCA/IncrementalPCA and its private
`GaussianMixtureFixedEM` is absorbed into `GaussianMixture`'s `fix_means` /
`fix_covariances` masks (with `covs_`/`converged_` aliases). Numeric parity with
scikit-learn is proven in `test/ml/test_parity.py` (11 tests, `importorskip`).
The MLP recreates Adam + early stopping and passes the surrogate's JSON
round-trip and task bar.

**What remains (all one stage): stage 5 — HDBSCAN.** Until HDBSCAN is written
in-tree, `hdbscan` and scikit-learn must both stay declared, so the manifest
(sixth bullet in Definition of done) and the package-count prize are gated on
stage 5. The companion tool keeps its `_SklearnHdbscanShim` and the ndxplorer
test suite must run with the fixed tttrlib wheel build, which was broken in
this env (`Mat.h:1034` undeclared `var`, unrelated to this PRD).

What is worth knowing before touching anything:

1. **The cross-section is four estimators, and it is smaller than the import
   count suggests.** Five files import scikit-learn; between them they touch
   `GaussianMixture`, `MLPRegressor`, `StandardScaler`, `KMeans`, `PCA` and
   `IncrementalPCA` — and nothing else. No `Pipeline`, no `model_selection`, no
   `metrics`, no `preprocessing` beyond the one scaler, no sparse input, no
   `n_jobs`. Re-derive with
   `grep -rn "from sklearn\|import sklearn" --include="*.py" chisurf/ modules/ndxplorer/`.
   *Trap*: `modules/ndxplorer/ndxplorer/utils/lazy_imports.py` has a
   `get_gmm()` that reads like a sixth call site and is **dead** — nothing
   calls it, because that tool fits mixtures with its own constrained EM.
   Grepping for the import overcounts; grep for the accessor.
2. **Most of the code is already written, in a place nothing can reach it.**
   `chisurf/core/math/hmm.py` privately holds `COVARIANCE_TYPES` (the same four
   spellings scikit-learn uses), `_log_gaussian_density` (Cholesky log-density
   for all four), `_kmeanspp_seed` / `_kmeans_lloyd` / `_kmeans` (k-means++ with
   `n_init` restarts and inertia selection — that *is* `KMeans`), `_logsumexp`,
   and `aic`/`bic` on the estimator. This is the reason the PRD exists and the
   reason it is smaller than "reimplement scikit-learn": the estimators are in
   the tree, sealed behind leading underscores in a module about something else.
3. **The dependency does not leave when chisurf stops importing it.** `hdbscan`
   requires `scikit-learn>=0.20`, and the companion tool's HDBSCAN path *falls
   back to* `sklearn.cluster.HDBSCAN` when the standalone package is absent.
   The two are a knot — dropping one by keeping the other is not available in
   either direction. Stages 1–4 are therefore worth doing on their own merits
   (one implementation instead of four, a constrained fit the library cannot
   do), and the package-count prize is gated entirely on stage 5.
4. **The measurement, and how to retake it.** Solve the recipe's `run:` list on
   conda-forge with and without `scikit-learn hdbscan`:
   **256 → 251 packages**, the five being `scikit-learn`, `hdbscan`, `joblib`,
   `narwhals`, `threadpoolctl`. Installed payload for the three with a directory
   is **46 MB** (scikit-learn 42, joblib 3, hdbscan 2), measured on this
   machine's environment, not on a packaged install. Use `conda create --dry-run
   --json` and count `actions.LINK`; the JSON carries no sizes, so disk has to be
   measured separately. *Shell trap*: zsh does not word-split an unquoted
   variable, so a package list built into one string arrives as a single
   malformed spec and the solve fails with `CondaValueError` rather than
   returning a count — build the list as a bash array.
5. **The exported surrogate is a compatibility surface, not an internal
   detail.** `SurrogateModel.to_json` writes the simulation library's
   `tttrlib.neural_net` schema by reading `net.coefs_`, `net.intercepts_`,
   `net.activation` and `net.out_activation_`, and transposing every weight
   matrix from `(n_in, n_out)` to row-major `(n_out, n_in)`. A replacement MLP
   that renames any of those, or that stores weights already transposed, breaks
   the C++ engine **silently** — the JSON still validates, the numbers are
   wrong. `test_surrogate_tttrlib.py` is the guard and must keep passing.

# Why

scikit-learn, `joblib`, `threadpoolctl` and `narwhals` are installed so that
five files can call four estimators. The surface those files use is not a
sampling of a large library — it is the whole of what they need, and it is
listed exhaustively in the table below. Nothing reaches for cross-validation,
pipelines, metrics, or any of the model-selection machinery that is the reason
to depend on a machine-learning library in the first place.

Meanwhile the tree has been writing the same estimators anyway. `hmm.py`
contains the Gaussian log-density for all four covariance layouts and a
complete k-means++ implementation, both private, both written with the comment
that they "keep this module free of a machine-learning dependency" — in a tree
that installs one. The companion photon-data exploration tool contains a third
mixture implementation, `GaussianMixtureFixedEM`, written because
`GaussianMixture` **cannot fix a subset of means or covariances** and that tool
needs to hold one population while fitting the rest. So the count today is:

| Implementation | Where | Why it exists |
|---|---|---|
| `GaussianMixture` | scikit-learn | the burst-selection call sites |
| emission half of `GaussianHMM` | `chisurf/core/math/hmm.py` | avoid the dependency inside the HMM |
| `GaussianMixtureFixedEM` | the companion tool | the library cannot fix parameters |
| `_kmeans` | `chisurf/core/math/hmm.py` | avoid the dependency for initialisation |

Four implementations of two algorithms, none sharing a line, and the dependency
still installed. The argument for this PRD is convergence first and the package
count second — which is the honest ordering, because stage 5 may not land.

# What is actually used

Everything, verbatim. Anything not in this table is out of scope and must not
be written.

| Estimator | Called from | Constructor args | Methods | Fitted attributes |
|---|---|---|---|---|
| `GaussianMixture` | `burst_selection/api/features.py:18`, `burst_selection/gui/tool.py:2593`, `burst_selection/gui/legacy/burst_selector.py:17` | `n_components`, `covariance_type` (all four offered by the settings dialog), `random_state`, `max_iter`, `n_init`, `tol`, `reg_covar` | `fit`, `fit_predict`, `bic`, `aic`, `score_samples` | `weights_`, `means_`, `covariances_`, `n_components` |
| `StandardScaler` | `burst_h2mm/core/surrogate.py:53` | — | `fit`, `transform`, `inverse_transform` | `mean_`, `scale_` |
| `MLPRegressor` | `burst_h2mm/core/surrogate.py:52` | `hidden_layer_sizes`, `activation="relu"`, `max_iter`, `early_stopping=True`, `random_state` | `fit`, `predict` | `coefs_`, `intercepts_`, `activation`, `out_activation_` |
| `KMeans` | companion tool, `analysis/clustering.py` | `n_clusters`, `random_state` | `fit` | `labels_`, `cluster_centers_` |
| `PCA` / `IncrementalPCA` | companion tool, `analysis/pca_helpers.py` | `n_components`, `svd_solver="auto"`, `random_state`, `batch_size` | `fit_transform` | `explained_variance_ratio_`, `components_` |
| `HDBSCAN` | companion tool, via the standalone package with a scikit-learn shim | `min_cluster_size` etc., `prediction_data` dropped by the shim | `fit` | `labels_`, `probabilities_` |

Two dimensionalities matter and are easy to miss: `features.py` fits a **5-D**
mixture over the burst feature matrix, while `gui/tool.py` and the legacy
selector fit **1-D** mixtures over a single histogrammed feature with
`data.reshape(-1, 1)`. A port validated only on the 1-D path is not validated.

# Shape

The organising decision is to **mirror scikit-learn's package layout and its
public spellings**, so that porting a call site is an import line and nothing
else, and so that anyone arriving from the library's documentation finds the
attribute they expect.

```
chisurf/core/ml/
    __init__.py                       re-exports the six estimators
    base.py                           Estimator: get_params/set_params, __repr__, the fit->self contract
    _gaussian.py                      shared: logsumexp, Cholesky log-density, the four covariance layouts
    mixture/
        __init__.py                   GaussianMixture
        _base.py                      the EM loop: n_init restarts, convergence, aic/bic, _n_parameters
        _gaussian_mixture.py          the four covariance types, reg_covar, and the fixed-parameter masks
    cluster/
        __init__.py                   KMeans          (HDBSCAN joins at stage 5)
        _kmeans.py                    k-means++ seeding, Lloyd, inertia restarts  <- moved out of hmm.py
    decomposition/
        __init__.py                   PCA, IncrementalPCA
        _pca.py                       SVD, and the batched covariance update for the incremental form
    preprocessing/
        __init__.py                   StandardScaler
        _data.py
    neural_network/
        __init__.py                   MLPRegressor
        _base.py                      activations and their derivatives
        _multilayer_perceptron.py     forward/backward, validation split, early stopping
        _stochastic_optimizers.py     Adam
```

Three rules make the layout load-bearing rather than decorative:

* **Public names are the library's names.** `fit`, `fit_predict`, `bic`,
  `weights_`, `means_`, `covariances_`, `labels_`, `cluster_centers_`,
  `components_`, `explained_variance_ratio_`, `mean_`, `scale_`, `coefs_`,
  `intercepts_`, `out_activation_`. This is what keeps the surrogate's exported
  JSON meaningful and what keeps the diff at each call site to one line.
* **The `_base.py` files hold the shared half.** The duplication this PRD
  removes came from four modules each keeping a private copy; a layout without a
  shared base invites the fifth.
* **`hmm.py` imports from here.** If the HMM keeps its private `_kmeans` and
  `_log_gaussian_density`, this PRD has added an implementation instead of
  removing three. The move is behaviour-neutral and the existing HMM suite is
  what proves it.

# Decisions

* **Only what is used gets written.** No `Pipeline`, no `GridSearchCV`, no
  sparse input, no `n_jobs`/`joblib` parallelism, no `set_output`, no metadata
  routing. The table above is the specification and the ceiling.
* **Reproducibility is in-tree, not bit-equal to the library.** A given seed
  must give the same answer run to run and machine to machine; it need not give
  *scikit-learn's* answer, because reproducing `check_random_state`'s exact
  `RandomState` stream would constrain the implementation for no benefit. The
  parity tests below compare converged optima, not draws.
* **The constrained mixture is a first-class option, not a fork.**
  `GaussianMixture` gains `fix_means` / `fix_covariances` boolean masks, which is
  what the companion tool wrote its own EM for. This is the one place the port
  is deliberately *more* than the library, and it is the reason the fourth
  implementation can be deleted rather than merely re-pointed.
* **The MLP reproduces behaviour, not initialisation.** scikit-learn's
  `MLPRegressor` defaults to Adam with `early_stopping=True` holding out 10% for
  validation. The replacement does the same; it will not produce the same
  weights, so its bar is the task bar (below), not a numeric diff.
* **The legacy burst selector is ported, not exempted.**
  `burst_selection/gui/legacy/burst_selector.py` is still reachable through the
  plugin's `__init__.py` fallback, so leaving it importing the library would
  leave the dependency required. If it is genuinely dead it should be deleted in
  this change instead — but that is a separate decision, to be settled by
  checking the fallback path rather than assumed here.
* **Deleting the surrogate's training path is the recorded alternative to
  stage 3.** The surrogate is already optional (`surrogate_available()` falls
  back to EM), ships no pretrained model, and exports to a C++ engine that can
  run it. scikit-learn there exists *only* to train one locally. Writing an MLP
  is the larger of the two options and should not be chosen by default; it is
  chosen if local training is a capability worth keeping.

# Stages

1. **`mixture` + `preprocessing`, and the three burst-selection call sites.**
   `GaussianMixture` over the extracted `_gaussian.py` density, with all four
   covariance types, `n_init` restarts and `aic`/`bic`; `StandardScaler`. Port
   `features.py`, `gui/tool.py`, and the legacy selector (or delete it).
2. **`cluster/_kmeans.py`.** Move `_kmeanspp_seed` / `_kmeans_lloyd` / `_kmeans`
   out of `hmm.py` and give them the `KMeans` surface; `hmm.py` imports them.
   Pure move — the HMM suite is the proof, and any numeric change is a bug.
3. **`neural_network`, or the decline.** Either `MLPRegressor` + Adam + early
   stopping, or delete `train_surrogate` and keep only the load/predict/export
   path. Whichever is chosen, `to_json` must keep emitting the same schema.
4. **The companion tool.** `decomposition` (`PCA`, `IncrementalPCA`), point
   `get_kmeans` at `chisurf.core.ml.cluster`, absorb `GaussianMixtureFixedEM`
   into `mixture` as the fixed-parameter option, and delete the dead `get_gmm`.
   Lands as commits in that tool's own repository, not here.
5. **HDBSCAN — the only genuinely new algorithm.** Mutual-reachability graph,
   minimum spanning tree, condensed tree, excess-of-mass extraction, and the
   membership probabilities the caller reads. Until this lands, neither
   `hdbscan` nor `scikit-learn` can leave any manifest, and stages 1–4 have
   bought convergence without buying the package count. **This is the honest
   stopping point**: if HDBSCAN is not worth writing, that is a decline to
   record here and in [known issues](/references/known-issues.md), not a reason
   to leave stages 1–4 undone.
6. **The declarations.** `pyproject.toml` (the required dependency *and* the
   `ml` extra, which is already a no-op because it names the same required
   package), `pixi.toml`, `rattler-recipe/recipe.yaml`, and the `sklearn` entry
   in `build_tools/build_installer.py`'s `TEST_PKGS`. Add `sklearn` to `RETIRED`
   in `test/test_no_retired_dependency_imports.py`, which covers imports and
   manifests in one place. The `pixi.toml` comment justifying the dependency is
   already stale — it claims "PCA for the parameter decomposition" as a chisurf
   use, and no PCA is reached from `chisurf/` at all.

# How parity is proven

* **Numeric agreement, where it is meaningful.** A test module guarded by
  `pytest.importorskip("sklearn")`, so it runs wherever the library happens to
  be installed and CI without it still passes. `GaussianMixture`: equal
  converged log-likelihood, `bic` and `aic` to tolerance, and equal labels up to
  a permutation, on fixtures with known components — **in 1-D and in 5-D**.
  `KMeans`: equal inertia. `PCA`: equal explained-variance ratios, and equal
  loadings up to a per-component sign flip.
* **The MLP's bar is the task, not the weights.** The existing
  `test_surrogate.py` recovery assertion (per-state FRET within 0.12 of ground
  truth) and the `test_surrogate_tttrlib.py` round-trip through the C++ engine.
  The round-trip is the load-bearing one, because it is the only test that would
  catch a transposed weight matrix.
* **The constrained fit gets its own test**, since it has no counterpart to
  compare against: fixing a component's mean must leave that mean exactly
  unchanged and must still improve the likelihood of the rest.
* **A before/after screenshot pair for the burst-selection GMM overlay**, in a
  realistic state, judged on control inventory — per the migration rule, the
  before-half captured *before* the code is touched.

# Definition of done

- [x] `chisurf/core/ml/` exists with the layout above and no dependency on the library
- [x] `GaussianMixture` (four covariance types, `n_init`, `reg_covar`, `aic`/`bic`) + `StandardScaler`
- [x] Fixed-mean / fixed-covariance masks, with a test that a fixed value does not move
- [x] All three burst-selection call sites ported; the legacy selector ported or deleted
- [x] `_kmeans*` moved out of `hmm.py`; `hmm.py` imports `chisurf.core.ml.cluster`
- [x] `MLPRegressor` written **or** the surrogate's training path deleted, with the choice recorded (written)
- [x] `to_json` still produces a schema the C++ engine reads, proven by the round-trip test
- [x] Companion tool: `PCA`/`IncrementalPCA`, `KMeans` re-pointed, `GaussianMixtureFixedEM` absorbed, dead `get_gmm` deleted
- [ ] HDBSCAN implemented, **or** the decline recorded in known issues with the reason (deferred: stage 5 untouched)
- [ ] `scikit-learn`, `hdbscan` and the `ml` extra struck from every manifest and from `TEST_PKGS`
- [ ] `sklearn` added to `RETIRED` in the guardrail test
- [ ] Package count re-measured and written down here

See also: [hidden Markov models](/subsystems/hidden-markov-models.md) for the
module the estimators are currently hiding in,
[graph layer](/subsystems/graph.md) and [PRD-81](prd-81.md) for the shape of an
in-tree replacement, [PRD-86](prd-86.md) for the sibling port closing the other
scientific-Python dependency out of imaging, [PRD-60](prd-60.md) for the
surrogate this touches, and [known issues](/references/known-issues.md).
