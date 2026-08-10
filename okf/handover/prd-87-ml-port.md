# Handover — PRD-87 stages 1–4: the in-tree scikit-learn port

Date: 2026-08-09
Owner of the concept: [PRD-87](../prds/prd-87.md)
Status: stages 1–4 landed in `chisurf/core/ml/`; stage 5 (HDBSCAN) untouched.

## What landed

`chisurf/core/ml/` mirrors scikit-learn's package layout and public spellings.
Everything is exercised against the library in `test/ml/test_parity.py`
(`pytest.importorskip("sklearn")`, 11 tests).

| Estimator | Mirrors | Notes |
|---|---|---|
| `GaussianMixture` | `sklearn.mixture` | 4 covariance types, `n_init`, `aic`/`bic`, `score_samples`; **extra**: `fix_means` / `fix_covariances` masks (the companion tool's old constrained EM is a thin wrapper around it) |
| `KMeans` | `sklearn.cluster` | kmeans++ + Lloyd moved **verbatim** out of `chisurf/core/math/hmm.py`; `hmm.py` imports `_kmeans` from here |
| `PCA` / `IncrementalPCA` | `sklearn.decomposition` | covariance eigendecomposition + batch moments; `svd_flip` sign convention |
| `StandardScaler` | `sklearn.preprocessing` | `fit`/`transform`/`inverse_transform` |
| `MLPRegressor` | `sklearn.neural_network` | Adam + early stopping; reads/writes same `coefs_`/`intercepts_`/`out_activation_` so the surrogate's `to_json` contract holds |

Call sites ported (each is an import-line change):

- `chisurf/plugins/burst/burst_selection/api/features.py`
- `chisurf/plugins/burst/burst_selection/gui/tool.py`
- `chisurf/plugins/burst/burst_selection/gui/legacy/burst_selector.py`
- `chisurf/plugins/burst/burst_h2mm/core/surrogate.py` (MLP + StandardScaler)
- `modules/ndxplorer`: `get_kmeans`/`get_pca` → `chisurf.core.ml`; dead `get_gmm` deleted; `GaussianMixtureFixedEM` →
  wrapper (commit `f74ccde` in the submodule)

Test results in this env: `test/math` (22), `test/ml` (11), surrogate tests
(5; the C++ round-trip still needs a working tttrlib wheel), guardrails
`test_declared_dependencies.py` + `test_no_retired_dependency_imports.py`
(37). The chisurf tree (`chisurf/`) has **zero** `sklearn` imports.

## What remains — stage 5, HDBSCAN

The only genuinely new algorithm; nothing else on the PRD is open.

- While it is unwritten, `hdbscan` **and** `scikit-learn` must both stay
  declared: `hdbscan` requires `scikit-learn>=0.20`, and ndxplorer's HDBSCAN
  path falls back to `sklearn.cluster.HDBSCAN` (the `_SklearnHdbscanShim` in
  `modules/ndxplorer/ndxplorer/utils/lazy_imports.py`).
- The moment HDBSCAN lands in-tree: strike `scikit-learn`, `hdbscan` and the
  `ml` extra from `pixi.toml` (`[dependencies]` + comment), `pyproject.toml`,
  `rattler-recipe/recipe.yaml`, and the `sklearn` entry in
  `build_tools/build_installer.py`'s `TEST_PKGS`; add `sklearn` to `RETIRED`
  in `test/test_no_retired_dependency_imports.py`.

## How to re-measure the package-count prize (from PRD-87)

Solve the recipe's `run:` list on conda-forge with and without
`scikit-learn hdbscan`; expected **256 → 251** packages over several environments
(scikit-learn, hdbscan, joblib, narwhals, threadpoolctl). Use `conda create
--dry-run --json` and count `actions.LINK`. **Shell trap**: zsh does not
word-split an unquoted variable, so a package list built into one string
arrives as a single malformed spec and the solve fails with `CondaValueError`
— build the list as a bash array.

## Env traps for the next session

- **tttrlib wheel build is broken in this env** (`modules/tttrlib`:
  `modules/math/include/Mat.h:1034` "use of undeclared identifier 'var'").
  Pre-existing, unrelated to this PRD; the agent board warns against parallel
  SWIG builds. Until it is fixed, the ndxplorer suite and the burst GUI tests
  cannot import (`chisurf/core/fio/fluorescence/burst.py` needs `tttrlib`),
  and `test_surrogate_tttrlib.py` skips. The parity tests, `test/math`, the
  guardrails and the non-tttrlib plugins suite run fine.
- pyqtgraph-effected: nothing here touches plotting; no `gui` / `widget`
  tests were affected by this change.
- The `test` env has pytest+pandas but no tttrlib; the `default` env has
  tttrlib but no pandas. Use `pixi run -e test python -m pytest …` for suites
  that do not import tttrlib.

## Files touched (parent repo commit `dd5f0d184`)

`chisurf/core/ml/**` (new), `chisurf/core/math/hmm.py`,
`chisurf/plugins/burst/burst_selection/{api/features.py,gui/tool.py,gui/legacy/burst_selector.py}`,
`chisurf/plugins/burst/burst_h2mm/core/surrogate.py`,
`test/ml/test_parity.py`, `pixi.toml` (comment only),
`okf/prds/prd-87.md`, `okf/log.md`. Submodule commit `f74ccde`:
`modules/ndxplorer/ndxplorer/{utils/lazy_imports.py,analysis/gaussian_fit.py}`.
