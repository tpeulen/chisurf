---
type: Manual Page
title: Parameter sampling
description: Optimisation returns the best parameter values.
tags: [manual, sampling, parameter]
---

# Parameter sampling

```{seealso}
What an error bar from sampling actually means, which sampler suits which
posterior, and how to tell a converged run from a stuck one:
{ref}`concept-parameter-uncertainty` and
{doc}`/guides/39_parameter_uncertainty`.

```

Optimisation returns the *best* parameter values. Sampling returns the
**distribution** of values compatible with the data, which is what an
uncertainty is — and, unlike the curvature at the optimum, it shows the
correlations between parameters and survives a posterior that is not a
paraboloid.

Sampling is started with the **Sample** button beside **▶ Fit** in the Fit box
of the Analysis dock (**Fig.15**); **⚙** beside it holds the sampler, the chain
length and format.

```{image} figures/manual_sampling.png
:align: center
```

**Fig.15 A sampled lifetime fit.** **Sample** (Fit box, left) samples the free
parameters and writes the chains to an output folder. The fit window then shows
them: here the *Chain diagnostics* page, whose rank plot of the lifetime `t0`
compares the four runs (flat = converged) and says whether the chains cover the
same distribution; *Posterior graph* and *What-if* show the correlations. The
chains can also be opened in nDXplorer, which ships with ChiSurf, to look at the
distributions and their correlations.

Defaults for the number of steps, the number of independent runs and the chain
format live in the `optimization.sampling` section of the settings file
(**Fig.14**).

## From the shell

```
fit = cs.current_fit
report = chisurf.core.fitting.fit.sample_fit(fit, "/output/directory")
```

The function is {src}`sample_fit <chisurf/core/fitting/fit.py#sample_fit>` —
that link opens it in the code editor, at its definition.

The second argument is a **directory**, not a file name: a timestamped
sub-directory is created inside it holding the chains and a `diagnostics.json`.
The same report is returned — per-parameter mean, standard deviation, quantiles,
effective sample size, split R-hat and autocorrelation time, plus a list of
warnings. **Read the warnings before the numbers**: a chain that has not
converged still produces a confident-looking standard deviation.

The sampler is chosen with `method`:

| `method` | When to use it |
| --- | --- |
| `ensemble` | The default. An affine-invariant ensemble whose walkers take their scale from each other, so it needs no prior knowledge of the posterior — the fallback when nothing is known about it. |
| `slice` | The same ensemble idea without an accept/reject step: every walker moves every step, at the cost of several model evaluations per step. |
| `blocked` | Proposes from a per-block covariance seeded by the curvature at the optimum. The one to reach for on a strongly *correlated* posterior. |
| `de` | Proposes from the differences within a population of chains: no gradient, no covariance, and so it cannot be misled by a covariance taken at the wrong point. Strong on curved posteriors started away from the optimum. |
| `collapsed` | For a **linked global fit**: each data set's private parameters are integrated out analytically and only the shared parameters are sampled. |
| `mcmc` | The historical diagonal random walk, kept for reproducing old analyses. |

Other useful arguments: `steps` and `thin` (chain length and thinning),
`n_runs` (independent runs, which is what makes the R-hat diagnostic
meaningful), `chi2max` (reject moves above a score), and `chain_format` —
`er4`, tab-separated text that any tool reads, or `hdf5`, about a quarter of
the size, which is what a long run needs. Both open in nDXplorer.

```{note}
For a trustworthy analysis the sampling has to be *complete*. A
high-dimensional or strongly correlated model needs more steps than the
default, and the diagnostics — not the appearance of the histogram — are how
you know whether it got there.

```
