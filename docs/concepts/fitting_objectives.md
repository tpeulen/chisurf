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

(concept-fitting-objectives-f-test)=
## Comparing nested models: the F-test

Two models are **nested** when the simpler one is the complex one with some
parameters held — one exponential is two exponentials with $a_2 = 0$. Freeing
parameters can only lower $\chi^2$, so "the complex model has the smaller
$\chi^2$" is no evidence; the question is whether the drop is larger than fitting
noise would produce. With $\chi^2_1$ on $\nu_1 = N - k_1$ degrees of freedom for
the simpler model and $\chi^2_2$ on $\nu_2 = N - k_2$ for the complex one:

**Extra-sum-of-squares F.** Under the null hypothesis that the extra
$\nu_1 - \nu_2$ parameters are zero,

$$
F = \frac{(\chi^2_1 - \chi^2_2)/(\nu_1 - \nu_2)}{\chi^2_2/\nu_2}
\;\sim\; F(\nu_1 - \nu_2,\ \nu_2),
$$

and the p-value is the upper tail {cite}`bevington2003,motulsky1987`. The
numerator is the drop per added parameter, the denominator the noise level per
degree of freedom estimated from the better model, so a uniform misestimate of
the weights cancels. For a likelihood objective the analogue is the
likelihood-ratio test: the drop in deviance, $\Delta(2I^*) \sim \chi^2(k_2 - k_1)$ {cite}`wilks1938`.

**Variance ratio.** The **F-Test** tool compares the two *reduced* statistics,

$$
\text{conf} = F_{\text{cdf}}\!\left(\frac{\chi^2_{r,1}}{\chi^2_{r,2}};\ \nu_1, \nu_2\right),
$$

the classical test for two independent variance estimates {cite}`bevington2003`
(`chisurf.core.math.statistics.f_test_confidence`). Two fits of the same data are
not independent, so this is a conservative stand-in: with $\nu_1 \approx \nu_2$
large, the ratio has to exceed one by about $3.3/\sqrt{\nu}$ to reach 95 %
(17 % at $\nu = 420$), however few parameters were added. On the repository's donor-only decay
(`test/data/tcspc/ibh_sample/Decay_577D.txt`, 425 channels in the window):

| comparison | $\chi^2_r$ | variance-ratio conf. | extra-SS $F$ | $p$ | $\Delta$AIC |
|---|---|---|---|---|---|
| 1 → 2 exp. | 11.12 → 6.16 | 1.000 | 171 | $5\times10^{-55}$ | −2101 |
| 2 → 3 exp. | 6.16 → 6.02 | 0.59 | 5.8 | 0.003 | −66 |

The first comparison is decided by any test. The second is where they part: the
variance ratio calls the third component unjustified, the extra-sum-of-squares
test and AIC call it significant. Neither verdict can be taken at face value here,
for the reasons below.

**Assumptions** {cite}`johnson1992,straume1991`:

- **the errors are Gaussian with the right weights** — $\chi^2_r \approx 1$ for
  the complex model. At $\chi^2_r = 6$ the residuals are dominated by systematic
  misfit, not noise, and any test that treats $\chi^2$ as a noise statistic
  answers a question about the wrong thing. The variance-ratio form is also
  sensitive to non-normal errors {cite}`box1953`;
- **the models are nested**, and both fits reached their global minimum — a
  complex fit that stops *above* the simple one (possible with a poor start) makes
  $F$ negative;
- **the extra parameters are interior.** The three-exponential fit above put
  $\tau_1$ on its lower bound (0.1 ns) with amplitude 0.05. A parameter on a
  boundary breaks the $F$ and $\chi^2$ reference distributions {cite}`self1987`;
  treat such a component as unresolved rather than significant.

**Information criteria.** For a Gaussian likelihood with known weights,
$-2\ln L = \chi^2 + \text{const}$, so

$$
\text{AIC} = \chi^2 + 2k,
\qquad
\text{BIC} = \chi^2 + k\ln N
$$

{cite}`akaike1974,schwarz1978`. Only differences matter; they need no nesting and
no significance level, and they rank any set of candidates at once. AIC estimates
predictive accuracy and tends to keep a marginal parameter; BIC's penalty grows
with $N$ and is consistent, choosing the true model when it is among the
candidates {cite}`burnham2002`. With millions of photons both penalties are
small against $\chi^2$, so like the F-test they are only as good as the weights —
the same $\chi^2_r = 6$ caveat applies.

**The $\chi^2_\text{max}$ threshold.** The same distribution sets confidence
intervals: a parameter vector is inside the joint region at confidence $1 - \alpha$
when

$$
\chi^2 \le \chi^2_\text{min}\left(1 + \frac{p}{\nu}\,F(p, \nu;\ 1-\alpha)\right)
$$

{cite}`johnson1992,beechem1992`, with $p$ the number of parameters varied jointly
($p = 1$ for a single-parameter support plane). The **F-Test** tool's
$\chi^2$-max panel evaluates it (`chi2_max`); the profile scan in
[parameter uncertainty](parameter_uncertainty.md) stops at the same form with
$p = 1$ for a least-squares fit (`chi2_threshold`), and at the likelihood-ratio
level for a likelihood.

The **F-Test** tool, its readouts and the batch run that produced the table:
{doc}`/guides/78_model_comparison_and_batch`.
