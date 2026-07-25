# Parameter uncertainty: priors, posteriors and sampling

Fitting a model gives a *best* parameter value. What a measurement actually
supports is a *range*. This page explains the three ways ChiSurf turns a fit
into an uncertainty, what each one assumes, and how to tell when the most
general of them — posterior sampling — has failed.

See the [lifetime](tcspc_lifetime.md) and [FRET](fret.md) concepts for the
models these uncertainties are attached to, and the
[uncertainty guide](../guides/39_parameter_uncertainty.md) for how to run each
method.

## From least squares to a posterior

ChiSurf minimises a sum of squared weighted residuals,

$$\chi^2(\theta) = \sum_i \left(\frac{y_i - m_i(\theta)}{\sigma_i}\right)^2 ,$$

which for Gaussian noise is the same as maximising the likelihood
$\ln L(\theta) = -\tfrac12 \chi^2(\theta)$. Bayes' rule turns that into a
**posterior** by multiplying in what was known beforehand:

$$p(\theta \mid D) \;\propto\; L(\theta \mid D)\, \pi(\theta),
\qquad
\ln p = -\tfrac{1}{2}\chi^2(\theta) + \sum_i \ln \pi_i(\theta_i) + \text{const.}$$

Every parameter may carry a **prior** $\pi_i$ — a Gaussian around an
independently measured lifetime, a log-normal on a positive rate, a beta on a
fraction, or the degenerate uniform prior that a hard bound *is*. A bound and a
soft prior are one concept in ChiSurf, not two.

Two consumers use the prior:

- **Optimisation (MAP).** Each prior contributes an extra residual
  $r = \operatorname{sign}(\theta-\theta^\ast)\sqrt{-2\,\Delta\ln\pi}$ appended
  to the data residuals — for a Gaussian prior simply $(\theta-\mu)/\sigma$ —
  so the ordinary least-squares engine minimises $\chi^2 - 2\ln\pi$ and lands on
  the posterior *mode* instead of the likelihood maximum.
- **Sampling.** The sampler evaluates $\ln\pi$ directly.

Reported $\chi^2$ and $\chi^2_r$ always exclude the prior, so they remain
goodness-of-**fit** numbers rather than a mixture of fit and belief.

## Three uncertainty estimates, in increasing generality

| Method | What it does | Assumes |
| --- | --- | --- |
| `laplace` | $\pm$ the square root of the diagonal of the covariance at the optimum | the posterior is Gaussian near its peak |
| `profile` | scans one parameter, re-optimising the rest, until $\chi^2$ rises by an F-test threshold | one parameter at a time; the scan resolves the minimum |
| `mcmc` | quantiles of a sample drawn from the full posterior | nothing beyond convergence of the chain |

`laplace` is free (the covariance is computed anyway) and is right whenever the
posterior really is close to a parabola in $\chi^2$. `profile` (the "support
plane" scan) copes with asymmetric and skewed intervals. `mcmc` is the only one
that describes correlations, multiple modes, and genuinely non-Gaussian shapes —
and the only one that costs real time.

ChiSurf's parameter report labels every interval with the method that produced
it, and prefers `mcmc` over `profile` over `laplace` when more than one is
available.

## Why a chain needs diagnostics

An MCMC chain is not a sample from the posterior — it is a sample from
*wherever the chain happened to go*. Those coincide only after the chain has
forgotten its starting point and explored the whole distribution. A chain that
has done neither looks exactly like one that has.

ChiSurf therefore reports, per parameter:

- **Split $\hat R$** — the Gelman–Rubin statistic, comparing the variance
  *between* chains (and between the halves of each chain) with the variance
  *within* them. If the chains have converged to the same distribution these
  agree and $\hat R \to 1$. Above **1.01** the chains have not mixed.
- **Effective sample size (ESS)** — successive draws are correlated, so $N$
  draws are worth fewer than $N$ independent samples:
  $$\mathrm{ESS} = \frac{N}{\tau}, \qquad \tau = 1 + 2\sum_{t\ge1}\rho_t ,$$
  with $\rho_t$ the autocorrelation at lag $t$. Below ~400 the reported
  quantiles are mostly sampling noise.
- **Integrated autocorrelation time $\tau$** — how many draws must pass for one
  independent sample. Directly comparable between samplers.
- **Monte-Carlo standard error**, $\mathrm{sd}/\sqrt{\mathrm{ESS}}$ — how much
  of the reported mean is noise rather than posterior. Only meaningful when it
  is small against the posterior width.
- **Burn-in** — how many initial draws to discard, taken as $2\tau$. ChiSurf
  *reports* this and applies it to the summary statistics; the stored chain
  keeps every draw.

These statistics can only ever detect failure, never prove success. No warnings
means "nothing detectably wrong", not "correct".

## Why the proposal matters so much

A random-walk sampler proposes a step, then accepts or rejects it. If the
proposal has the wrong *shape*, almost every step is rejected and the chain
crawls.

Fluorescence posteriors are strongly correlated by construction: amplitude and
lifetime in a multi-exponential decay trade off against each other, as do the
terms of a polynomial baseline. Along the correlated direction the posterior is
long and thin; a proposal that steps independently in each coordinate — a
*diagonal* proposal — must use a step small enough for the thin direction, and
so takes forever to traverse the long one.

The fix is to propose from the posterior's own **covariance**, which ChiSurf
seeds from the curvature at the optimum (the same matrix that produces the
`laplace` error bars) and then refines during warm-up. On a deliberately
collinear three-parameter fit (parameter correlations $\approx 0.99$):

| Sampler | Proposal | $\tau$ | Effective samples per 1000 model evaluations |
| --- | --- | --- | --- |
| `mcmc` | diagonal | 2024 | 0.4 |
| `emcee` | affine-invariant ensemble | 39 | 26 |
| `blocked` | per-block covariance | 12 | 64 |

The diagonal sampler produced **4** effective samples out of 8000 draws. This is
why `blocked` is the recommended backend for anything with correlated
parameters.

## Blocking, and why a global fit has structure

A global fit's posterior factorises: dataset $k$'s likelihood depends only on
the parameters its own model reads,

$$p(\theta \mid D) \;\propto\; \prod_k L_k(\theta_{S_k}) \cdot \prod_i \pi_i(\theta_i).$$

ChiSurf builds this as an explicit graph — parameters are nodes, per-dataset
likelihoods and per-parameter priors are factors — and groups parameters into
**blocks** by the set of datasets that depend on them. In a typical global fit
with one shared parameter, each dataset's private parameters form a cheap block
(moving them re-evaluates one dataset) and the shared parameters form one
expensive block.

The same graph tells you something about the *fit* rather than the sampler: its
**treewidth**, its independent components, and its **separator** — the
parameters that, once fixed, make the datasets independent of one another. That
last one is the identifiability statement a global fit exists to make.

## Don't sample what doesn't need sampling together

If the graph falls into several **connected components**, no factor links them:
no dataset likelihood, no prior. The posterior then factorises *exactly*,

$$p(\theta \mid D) = \prod_c p_c(\theta_c),$$

and sampling all of them in one chain is pure waste. A random walk's cost for a
given effective sample size grows roughly with the square of the dimension it
moves in, and in a group every joint proposal re-evaluates every dataset. Two
independent 2-parameter problems are far cheaper than one 4-parameter problem,
and the gap widens with every dataset added.

ChiSurf therefore samples each component on its own — holding the others at a
common reference, whose datasets then contribute a constant that cancels in the
Metropolis ratio — and merges afterwards. **The merge is analytic, not a second
approximation:**

- *Draws.* Independence means any pairing of draws from different components is
  itself a draw from the joint. The components' chains are shuffled
  independently and stacked side by side. (The shuffle matters: without it the
  ordering of the chains would appear as a correlation between components that
  the posterior does not have.)
- *Objective.* $\chi^2$ is a sum over datasets and each dataset belongs to
  exactly one component, so run $c$ reports
  $\chi^2_{\text{run},c} = \chi^2_c(\theta_c) + [\chi^2_0 - \chi^2_c(\theta^0_c)]$.
  Summing over the $C$ components and cancelling the shared reference gives
  $$\chi^2(\theta) = \sum_c \chi^2_{\text{run},c} - (C-1)\,\chi^2_0 ,$$
  and the log-prior, being a sum over parameters, obeys the same identity. Both
  are exact and cost no extra model evaluation.

Measured on 8 independent datasets (16 parameters), for the same number of
recorded draws: **72.6 effective samples per 1000 model evaluations against 5.6**
for one joint chain — 7.8× the effective sample size for 40% fewer evaluations.

A group whose datasets *do* share a parameter is a single component and cannot
be decomposed this way; that is what the shared parameter means. The
`components` line of the structure report says which case you are in — and
`components > 1` in something called a "global fit" means nothing is actually
being shared.

## Adaptation and validity

Both random-walk samplers tune their proposal during a **warm-up** phase and
then **freeze** it. This is not an implementation detail: a chain whose
transition rule keeps changing is not a homogeneous Markov chain and is not
guaranteed to converge to the posterior. Only the frozen, post-warm-up draws are
recorded.

## References

- Gelman, A. & Rubin, D. B. *Inference from iterative simulation using multiple
  sequences.* Statistical Science **7**, 457–472 (1992).
- Vehtari, A. *et al.* *Rank-normalization, folding, and localization: an
  improved $\hat R$ for assessing convergence of MCMC.* Bayesian Analysis
  **16**, 667–718 (2021).
- Geyer, C. J. *Practical Markov chain Monte Carlo.* Statistical Science **7**,
  473–483 (1992).
- Haario, H., Saksman, E. & Tamminen, J. *An adaptive Metropolis algorithm.*
  Bernoulli **7**, 223–242 (2001).
- Goodman, J. & Weare, J. *Ensemble samplers with affine invariance.*
  Communications in Applied Mathematics and Computational Science **5**, 65–80
  (2010).
- Foreman-Mackey, D. *et al.* *emcee: the MCMC hammer.* PASP **125**, 306 (2013).
