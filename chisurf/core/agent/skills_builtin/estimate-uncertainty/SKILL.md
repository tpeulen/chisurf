---
name: estimate-uncertainty
description: >-
  Put an honest confidence interval on a fitted parameter, and decide whether
  an extra component is justified. Use when the user asks how certain a value
  is, for error bars or confidence intervals, or whether a model needs more
  components.
triggers:
  - uncertainty
  - uncertain
  - confidence interval
  - error bar
  - error bars
  - how certain
  - how accurate
  - how precise
  - significant
  - justified
  - f-test
  - f test
  - support plane
  - too many components
  - enough components
  - overfitting
tools:
  - fit_report
  - get_fit
  - run_python
  - set_components
  - run_fit
  - search_documentation
---

# Honest uncertainty

Read [uncertainty and model choice](../../knowledge_base/concepts/uncertainty-and-model-choice.md)
for why this matters. In short: the `error` a fit reports comes from the
covariance matrix and is an optimistic lower bound. A confidence interval
comes from walking the parameter away from its optimum and re-fitting
everything else — the support plane.

There is no dedicated tool for this. Use `run_python`, which runs in the live
session, with the recipes below.

## A confidence interval for one parameter

```python
fit = fits[0]                       # or the index the user means
name = "tL2"                        # exact name, from get_fit

covariance = fit.model.parameters_all_dict[name].error_estimate
result = fit.adaptive_chi2_scan(name, p_value=0.95, max_points_per_side=25)
low, high = result["crossings"]
value = fit.model.parameters_all_dict[name].value

print(f"{name} = {value:.4f}")
print(f"  covariance error : {covariance:.4f}")
print(f"  95% interval     : [{low}, {high}]")
print(f"  chi2r at minimum : {result['chi2r_min']:.4f}, threshold {result['threshold']:.4f}")
```

Read the crossings carefully:

* They are **asymmetric**. Report both bounds, or say which side you quote.
* If a crossing comes back equal to the parameter's own value, the scan found
  no crossing on that side — the data does not bound it there, or it hit a
  limit. Say so; do not report it as zero uncertainty.
* The scan re-fits at every step, so it costs real time. Do it for the
  parameters the user cares about, not for all of them.

For several confidence levels from one scan:

```python
from chisurf.core.fitting.support_plane import confidence_intervals_from_scan_result

for interval in confidence_intervals_from_scan_result(result, p_values=(0.68, 0.95)):
    print(interval["p_value"], interval["crossings"])
```

## Is one more component justified?

Fit with *n* components, note chi-square and the free-parameter count, fit
with *n+1*, then compare with an F-test. Only for nested models — the same
model with more of the same component.

```python
import scipy.stats as stats

fit = fits[0]
n_points = fit.model.n_points

# after fitting with the smaller model
chi2r_a, p_a = fit.chi2r, fit.model.n_free
# ... set_components(n+1), run_fit ...
chi2r_b, p_b = fit.chi2r, fit.model.n_free

nu_a, nu_b = n_points - p_a, n_points - p_b
f = ((chi2r_a * nu_a - chi2r_b * nu_b) / (p_b - p_a)) / (chi2r_b * nu_b / nu_b)
p_value = 1.0 - stats.f.cdf(f, p_b - p_a, nu_b)
print(f"F = {f:.1f}, p = {p_value:.3g} -> justified: {p_value < 0.05}")
```

On the sample donor decay, two lifetimes to three gives F ≈ 808, p ≈ 0: the
third is unambiguously justified. A p-value of a few per cent means the data
does not clearly support the extra component — say that, rather than deciding
silently.

## Reporting

Give the value, the interval, the confidence level, and **where the interval
came from**. Name any parameter that was fixed or linked: an interval
computed with something held fixed is conditional on that choice and is
narrower than the truth.

An unbounded side is a result, not a failure. It means the measurement does
not determine that parameter, which is worth knowing and worth saying.

## What not to do

Do not quote the covariance error as a confidence interval. Do not add
components until chi-square looks nice — check the F-test. Do not scan every
parameter by reflex; each scan is a series of fits.
