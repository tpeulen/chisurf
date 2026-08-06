(plugin-f_test)=
# F-Test

F-test calculator: compare two nested model fits (confidence <-> chi2 threshold) and compute the chi2-max upper limit of a single fit at a confidence level. Declarative AutoForm view; values load from open fits.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `f_test` |
| Menu path | Main → Tools → **F-Test** |
| Categories | Main, Tools, Statistics |
| Version | 2.0.0 |
| Surfaces | gui |
| State namespace | `f_test` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### F-test — compare two nested models

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| χ²(1) | `chi2_1` | float |  | 0.0 … 1000000.0 (step 0.001) | Reduced χ² of the first (simpler) model. |
| n₁ | `n1` | int |  | 1 … 1000000 (step 1) | Degrees of freedom of the first model. |
| χ²(2) | `chi2_2` | float |  | 0.0 … 1000000.0 (step 0.001) | Reduced χ² of the second (more complex) model; recomputed when the confidence changes. |
| n₂ | `n2` | int |  | 1 … 1000000 (step 1) | Degrees of freedom of the second model (points minus free parameters). |
| confidence | `conf_level` | float |  | 0.0 … 1.0 (step 0.001) | F-test confidence level; recomputed from the χ² ratio, or drives the χ²(2) threshold when edited. |

### χ²-max — upper limit from one fit

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| χ² min | `chi2_min` | float |  | 0.0 … 10000.0 (step 0.01) | Reduced χ² (minimum) of the fit. |
| params | `npars` | int |  | 0 … 1000000 (step 1) | Number of free parameters of the model. |
| ν (dof) | `dof` | int |  | 0 … 1000000 (step 1) | Degrees of freedom (observations minus parameters). |
| confidence | `conf_level_2` | float |  | 0.0 … 1.0 (step 0.01) | Confidence level for the χ² upper limit. |
| χ² max | `chi2_max` | float |  |  | Resulting χ² upper limit at the chosen confidence level. |

## Theory and workflow

- **Theory** — [Parameter uncertainty: priors, posteriors and sampling](/concepts/parameter_uncertainty.md)

## Source

- Plugin package: `chisurf/plugins/core/f_test/`
- Manifest: {src}`chisurf/plugins/core/f_test/manifest.json`
- UI spec: {src}`chisurf/plugins/core/f_test/gui/ftest.view.json`
