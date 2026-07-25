---
type: Concept
title: Uncertainty and model choice
description: >-
  Why the error bar a fit hands you is optimistic, what a support-plane
  interval is, and how to decide whether an extra component is justified.
tags: [uncertainty, confidence-interval, f-test, support-plane, model-selection]
timestamp: '2026-07-25T00:00:00Z'
---

# The error a fit reports is not the error you should quote

After optimisation every parameter carries an `error_estimate`. It comes from
the covariance matrix — the curvature of chi-square at the minimum,
extrapolated as if the model were linear in its parameters and the surface a
perfect parabola.

Fluorescence models are not linear in their parameters, and lifetimes,
amplitudes and distances are strongly correlated with one another. The
covariance error is therefore an **optimistic lower bound**: it answers "how
sharp is the minimum in this one direction", not "what values of this
parameter are compatible with the data".

On the sample donor decay, the long lifetime is `4.1201 ns` with a covariance
error of **0.0014 ns**. Its support-plane 95 % interval reaches to
`4.1240 ns` — an uncertainty of **0.0039 ns**, nearly three times larger.
Neither number is wrong; they answer different questions, and only the second
is a confidence interval.

# The support plane

The honest interval is found by *walking the parameter away from its optimum*
and re-optimising everything else at each step. Chi-square rises; where it
crosses an F-test threshold, the parameter is no longer compatible with the
data at that confidence level.

This is what `Fit.adaptive_chi2_scan` does. It returns the crossings, the
threshold, the chi-square minimum, and the degrees of freedom, and it writes
the larger half-width back into the parameter's `error_estimate`.

Two properties matter when reporting it:

* **The interval is asymmetric.** A lifetime can usually be pushed further up
  than down. Quote both bounds rather than a single ±, or say which side you
  are quoting.
* **A missing crossing is information.** When one side returns the parameter's
  own value, the scan found no crossing in that direction — because it hit a
  bound, because chi-square barely moves there (the data does not constrain
  it), or because the scan range was too narrow. Say which, or say the bound
  is open. Do not report it as zero uncertainty.

Sampling (MCMC) answers the same question with a posterior instead of a
threshold, and is worth the cost when parameters are strongly correlated and
you want the joint distribution rather than one-at-a-time intervals.

# Is another component justified?

Adding a component always lowers chi-square, because it adds freedom. The
question is whether it lowers it by *more than freedom alone would*. For
nested models — the same model with more components — that is an F-test:

    F = ((chi2_a - chi2_b) / (p_b - p_a)) / (chi2_b / (n - p_b))

with absolute chi-square values (`chi2r * degrees_of_freedom`), `p` free
parameters and `n` points. The p-value is the tail of the F distribution with
`(p_b - p_a, n - p_b)` degrees of freedom.

On the sample decay, going from two lifetimes to three gives F ≈ 808 with
p ≈ 0: the third component is unambiguously justified. A borderline case —
p of a few per cent — deserves the answer "the data does not clearly support
it", not a silent decision either way.

The F-test only applies to **nested** models. Two different models with the
same number of parameters are not comparable this way; use the residuals, the
Durbin-Watson statistic and physical plausibility instead.

# What to report

A result is a value, an interval, and the assumptions behind it. Quote the
confidence level; say whether the interval came from the covariance matrix or
from a support-plane scan; name the parameters that were fixed or linked,
because an interval computed with a parameter held fixed is conditional on
that choice and is narrower than the truth.

If a parameter's interval is unbounded on one side, that is the result. It
means the measurement does not determine it, and reporting a tight symmetric
error instead would be a fabrication.
