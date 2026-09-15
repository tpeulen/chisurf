---
type: Concept
title: 'Fitting objectives: which statistic a fit minimises'
description: 'Weighted least squares, the Neyman and Pearson chi-squares and the Poisson likelihood — what each one estimates, where the least-squares forms are biased, and the setting that chooses between them.'
tags: [concepts, fitting, statistics, tcspc]
anchor: concept-fitting-objectives
---

(concept-fitting-objectives)=
# Fitting objectives: which statistic a fit minimises

A fit finds the parameters that make some number as small as possible. *Which*
number is not a display choice — it decides what the fitted parameters are, and
two objectives on the same data give different answers. This page explains the
statistics ChiSurf can minimise, which one is right for photon counting, and how
to change it.

See [parameter uncertainty](parameter_uncertainty.md) for what happens to the
error bars afterwards, and [TCSPC lifetimes](tcspc_lifetime.md) for the models
this applies to.

## The four statistics

Write $d_i$ for the measured value in channel $i$, $m_i$ for the model there,
and $\sigma_i$ for the weight.

**Weighted least squares** minimises $\sum_i (d_i - m_i)^2 / \sigma_i^2$. What
distinguishes the variants is entirely where $\sigma_i$ comes from.

| statistic | weight | notes |
|---|---|---|
| **Neyman** $\chi^2$ | $\sigma_i^2 = \max(d_i, 1)$ — from the **data** | fast, familiar, **biased low** at small counts |
| **Pearson** $\chi^2$ | $\sigma_i^2 = m_i$ — from the **model** | nearly unbiased; the weights move as the fit moves |
| **Poisson MLE** ($2I^*$) | none — a likelihood, not a weighted square | the correct estimator for counts |
| **Gehrels** | an approximate Poisson confidence interval | a middle ground when least squares is required and counts are low |

A photon-counting histogram has $\mathrm{Var}(d_i) = \lambda_i$, the *expected*
count. Neyman substitutes the observed count for it and Pearson substitutes the
model; the Poisson likelihood needs no such substitution, which is why it is the
one with no small-count bias to discuss.

## Why the Neyman weighting is biased

If a channel happens to fluctuate **down**, $\sigma_i^2 = d_i$ is small, so that
channel is given *more* weight. Downward fluctuations therefore pull the fit
harder than upward ones, and the estimate comes out low. The bias is a function
of counts per bin — measured on 400 Poisson bins over 4000 trials, estimating a
single rate:

| counts per bin | Neyman (data-weighted) | Pearson (model-weighted) |
|---|---|---|
| 3 | −31.1 % | +0.12 % |
| 10 | −11.5 % | +0.04 % |
| 100 | −1.0 % | −0.01 % |

Two things follow, and the second is the one that matters for decays.

**It does not announce itself.** The biased fit's residuals look fine. There is
no diagnostic in a residual plot, a $\chi^2_r$ or an autocorrelation that
distinguishes it — the fit is *good*, it is just centred on the wrong answer.

**On a decay it distorts the shape, not the scale.** The bias depends on the
counts in each channel, and a fluorescence decay always has a low-count tail
however bright its peak. The tail is exactly where the long lifetimes live, so a
Neyman-weighted fit pulls the long components low while leaving the peak almost
untouched. A recovered lifetime *distribution* comes out with the wrong shape,
not merely the wrong normalisation.

## What ChiSurf uses, and how to change it

Two settings, because the right answer differs by data type:

```yaml
tcspc:
  noise_model: default      # photon-counting decays
optimization:
  noise_model: default      # everything else
```

`default` is weighted least squares on the data's error column — the Neyman
$\chi^2$ when that column is $\sqrt{N}$. `poisson` is the $2I^*$ deviance.

For **non-counting data** — an FCS curve, an anisotropy, a stopped-flow trace —
`default` is not merely convenient but correct: those are not counts, their
error column is not $\sqrt{N}$, and a Poisson deviance would be the wrong
likelihood for them regardless of the argument above.

For **TCSPC decays** the statistics favour `poisson` and ChiSurf nonetheless
ships `default`. The reason is the optimiser, not the estimator. On the
repository's own convergence fixture — a two-exponential decay, $2\times10^6$
photons, started deliberately far from the answer at $\tau = 8.0$ against a true
$4.0$ — the `poisson` fit stops at $\tau = 7.24$. The objective is not what is
wrong: it scores $1.47$ at the true answer against $875$ at $7.24$, so it
prefers the truth by a wide margin. The *search* does not get there. The
numerical-Jacobian step (`optimization.leastsq.epsfcn`) was tuned against
weighted least squares, and the deviance surface is not the surface it was tuned
on. A silently wrong lifetime does more damage than a slightly biased one, so
the biased-but-convergent estimator remains the default until the optimiser
handles the deviance as reliably.

**Switch to `poisson` when** the counts are low enough for the bias to matter
and you can start the fit near the answer — from a good start it converges, and
it is then the better estimator. Recovering a lifetime *distribution* from
sparse data is the case where the difference is largest, because that is where
the tail carries the information.

**Switch back to `default`** to reproduce a historical fit, or to compare with
software that uses the same weighting — which most TCSPC packages do.

### It also changes the error bars

The two objectives take different support-plane thresholds: an F-test form for a
least-squares fit, a likelihood-ratio form for a likelihood. ChiSurf follows the
fit's objective automatically (`objective_type`), so confidence intervals move
when the setting changes. That is correct rather than incidental — using the
F-test form on a likelihood inflates every interval by $\sqrt{\chi^2_r}$ — but
it means intervals are not comparable between fits made under different
settings. Record which one a published fit used.

## Per-fit override

A single fit can be built with an explicit estimator, which overrides both
settings:

```python
from chisurf.core.fitting.fit import Fit
fit = Fit(model_class=..., data=..., noise_model="poisson")
```

Omitted, the estimator is resolved from the data and the model — the TCSPC key
for a counting decay, the general key otherwise — by
`chisurf.core.fitting.default_noise_model`.
