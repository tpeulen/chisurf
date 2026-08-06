---
type: Fundamentals
title: Photon statistics and goodness of fit
description: Photon detection is a counting process, and its noise is not an instrumental imperfection that better hardware would remove.
tags: [fundamentals, photons, fitting]
anchor: fundamentals-photon-statistics
---

(fundamentals-photon-statistics)=
# Photon statistics and goodness of fit

Photon detection is a counting process, and its noise is not an instrumental
imperfection that better hardware would remove. It sets the precision of every
result here. This page covers what that noise is, how it determines the correct
fitting statistic, and how to read a goodness-of-fit number. The machinery of
confidence intervals and posterior sampling is in
{ref}`concept-parameter-uncertainty`.

## Photon arrivals are Poisson

Under constant illumination, detections form a Poisson process. In a bin
expecting $\mu$ counts, the probability of observing $k$ is
$P(k) = \mu^k e^{-\mu}/k!$, with variance equal to the mean:

$$
\sigma^2 = \mu, \qquad \sigma = \sqrt{\mu}.
$$

The relative precision therefore improves only as $1/\sqrt{\mu}$. Halving an
error bar costs four times the photons — or four times the acquisition time, at
a count rate that is already capped by the sample's lifetime and the pile-up
limit ({ref}`fundamentals-photon-counting`). This is why photon budget is the
central currency of the single-molecule methods, and why bleaching, which caps
the total photons a molecule can emit, is a precision limit and not just an
inconvenience ({ref}`fundamentals-quenching`).

Two consequences propagate everywhere:

- **The noise is not uniform across a decay.** The peak channel of a TCSPC
  histogram has thousands of counts and the tail has tens. Their absolute
  uncertainties differ by an order of magnitude, so an unweighted fit is
  dominated by the peak and largely ignores the tail — which is where the long
  lifetime lives.
- **The shot-noise limit on a ratio.** A FRET efficiency estimated from $N$
  photons in a burst has variance $E(1-E)/N$ from counting statistics alone,
  before any real heterogeneity. A histogram of per-burst efficiencies always
  has non-zero width, and the question is never whether it is broad but whether
  it is broader than this. Comparing the observed width against the shot-noise
  width is the basis of burst variance analysis ({ref}`concept-bva`) and of the
  photon-distribution methods ({ref}`concept-pda2c`).

## Weighting, least squares, and maximum likelihood

Weighted least squares minimizes

$$
\chi^2 = \sum_i \frac{\left(y_i - y_i^{\text{model}}\right)^2}{\sigma_i^2},
\qquad \sigma_i^2 = y_i,
$$

which is the correct estimator when each bin holds enough counts for the Poisson
distribution to be approximately Gaussian — conventionally more than about 10,
comfortably true for a cuvette decay.

It breaks in two ways at low counts. The Gaussian approximation is asymmetric in
the wrong direction, and taking $\sigma_i^2 = y_i$ from the *observed* count
rather than the expected one gives empty and near-empty bins zero or absurdly
small variance, so they dominate. Fitted lifetimes come out systematically
short.

Poisson maximum likelihood has neither problem and is what per-burst and
per-pixel analyses require, where a whole decay may hold tens to hundreds of
photons. ChiSurf routes those through the $2I^*$ estimator
({ref}`concept-tcspc-lifetime`). The distinction is not a refinement: at burst
photon counts, least squares is simply biased.

Three related rules follow, and all three are enforced in ChiSurf's forward
model:

- Corrections are applied to the **model**, never to the data. Pre-correcting
  counts — subtracting background, dividing out non-linearity — destroys the
  Poisson property that the statistic assumes.
- Rebinning to make bins "look better" throws away time resolution and is not a
  substitute for the right statistic.
- Data must not be smoothed before fitting. Smoothing correlates neighbouring
  residuals and makes any goodness-of-fit test optimistic.

## Reading $\chi^2_r$

The reduced statistic is $\chi^2_r = \chi^2/(n - p)$ for $n$ fitted points and
$p$ free parameters. A correct model with correct weights gives $\chi^2_r
\approx 1$, and its expected scatter is

$$
\sigma(\chi^2_r) \approx \sqrt{\frac{2}{n - p}} .
$$

For a 1000-channel decay that is about 0.045, so 1.1 is a real deviation and not
noise, while for a 50-point curve the same value is unremarkable. Quoting
$\chi^2_r$ without $n$ is uninformative.

Interpret the deviations:

- $\chi^2_r \gg 1$ — the model is wrong, or the weights are wrong, or there is
  an unmodelled nuisance. Uncorrected scatter, a mismatched instrument response,
  and a wrong time shift all raise it.
- $\chi^2_r \ll 1$ — usually the errors are overestimated or the data have been
  smoothed. It is not a better fit.
- $\chi^2_r \approx 1$ — the model is *adequate*, which is a much weaker claim
  than being correct. Several distinguishable physical models routinely fit the
  same decay equally well.

## Residuals carry what $\chi^2_r$ discards

$\chi^2_r$ is a sum and therefore loses all information about *where* the model
fails. The weighted residuals as a function of time carry it.

Random residuals scattered about zero are what a correct model gives.
Systematic structure — a run of positive residuals at early times, a wave, a
spike at the peak — indicates a specific defect, and its position identifies it:
deviations concentrated near the rising edge point at the instrument response or
the time shift, and deviations in the tail point at a missing long component or
an incorrect background.

The autocorrelation of the residuals makes this quantitative. Correlated
residuals are the signature of a systematic error, and the autocorrelation
detects runs that are not obvious in a residual plot. Both are standard outputs
of a TCSPC fit and should be inspected before the parameters are read.

## Comparing models

Adding an exponential term always lowers $\chi^2$, because it adds parameters.
The question is whether it lowers it more than chance would.

For nested models the $F$-test on the ratio of $\chi^2$ values, with the
appropriate degrees of freedom, gives the criterion. In practice the
improvement from a genuine additional component is dramatic and the improvement
from an unnecessary one is marginal, so borderline cases are usually resolved by
other evidence — parameter stability across repeats, physical plausibility of
the recovered lifetime, or a global fit that constrains the same component
across several datasets.

That last option is the strongest one available. Linking a parameter across
measurements that share it — several emission wavelengths, several quencher
concentrations, several samples — adds information without adding photons, and
routinely resolves components that a single curve cannot
({ref}`concept-tcspc-lifetime`).

## How many photons

The useful question is not "did it converge" but "can this photon budget support
this many parameters".

Rough guidance for TCSPC: a single lifetime is well determined with a few
thousand photons in the decay. Two lifetimes differing by a factor of two or
more need of order $10^5$–$10^6$. Two lifetimes closer than a factor of two are
frequently not resolvable at any budget, because the exponential problem is
ill-conditioned rather than merely noisy — the parameters trade off against each
other, and the confidence region is a long thin valley rather than an ellipse.

That valley shape is why a parameter's uncertainty must not be read from its
diagonal error estimate alone when the parameters are correlated, and why
ChiSurf provides profile and sampling-based intervals
({ref}`concept-parameter-uncertainty`).

## See also

- Previous: {ref}`fundamentals-photon-counting`.
- Concepts: {ref}`concept-parameter-uncertainty` (confidence intervals, priors,
  sampling) · {ref}`concept-tcspc-lifetime` (the statistics in the fitted model)
  · {ref}`concept-bva` · {ref}`concept-pda2c`.
- Guides: {doc}`/guides/39_parameter_uncertainty`.
- Literature: {cite}`lakowicz2006`, data-analysis sections; {cite}`oconnor1984`
  for goodness-of-fit practice in TCSPC; {cite}`maus2001` for the maximum
  likelihood estimator.
