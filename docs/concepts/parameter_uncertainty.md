(concept-parameter-uncertainty)=
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

## Finding the minimum before describing it

Every interval on this page describes the minimum the optimiser stopped at. A
least-squares run is *local*: it goes downhill from where it starts, so if the
start was in the wrong basin, the covariance, the profile and the chain all
describe the wrong basin — confidently. Two situations produce that routinely:

- **Degenerate pairs.** Two parameters that scale the same thing (a
  detection-correction factor scaling the data against a lifetime scaling the
  model) trade off along a valley; the optimiser slides a little way down it and
  stops.
- **Rough objectives.** Anything reduced from counts is not smooth at the scale
  of the finite-difference step, so the derivative it measures is noise — or
  exactly zero, and the fit terminates having moved nothing.

`Fit.grid_scan` is the blunt instrument for this: evaluate $\chi^2$ on a coarse
grid over the free parameters and start the fit at the best point. It spends a
fixed number of model evaluations however many parameters there are, takes each
parameter's grid from its bounds (or a factor either side of where it sits, on
a *geometric* axis — a lifetime or a correction factor is a scale), and always
includes the current value, so it cannot return something worse than the start.

```python
result = fit.grid_scan()      # leaves the parameters at the best grid point
fit.run()                     # ...and the local fit descends from there
print(result.improved, result.evaluations)
```

A grid point is the deepest *point*, not the deepest *basin*: on a smooth
objective the start you chose often descends further than any grid point does.
Callers that cannot afford to be wrong about this run the local fit from both
starts and keep the better result — which is what
[nDXplorer's curve fit](../guides/46_ndxplorer.md) does behind its **Scan first**
box. Different in kind from the profile scan below, which maps *one* parameter's
$\chi^2$ to get an interval, not to find where the minimum is.

Implementation: `chisurf.core.fitting.grid_scan`.

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

### One way to ask

All three sit behind a single engine interface, so a caller declares what it
wants to know and reads the answer without knowing which estimator produced it:

```python
from chisurf.core.fitting import engine

eng = engine.get_engine('mcmc', fit)
eng.condition('tau2', 4.0)        # fix a parameter, re-optimise the rest
eng.add_target('tau1')            # only declared targets are computed
eng.add_joint_target(('tau1', 'x1'))
eng.run(steps=5000, n_runs=2)

m = eng.marginal('tau1')
print(m.value, m.interval(0.68), m.method)
print(eng.joint(('tau1', 'x1')).correlation)
```

- **`condition(name, value)`** fixes a parameter and re-optimises the rest. That
  is what a profile scan *is*, and what the other engines do by construction, so
  it means the same thing whichever engine is used.
- **Targets are declared, not assumed** — a profile scan of one parameter should
  not scan the other nine.
- **`joint`** returns a covariance and a `correlation` matrix. Only a chain has
  a real one; a profile scan handles one parameter at a time and returns `None`
  rather than pretending.
- **`log_evidence`** is available from engines that integrate over the
  parameters. A profile scan maximises rather than integrates, so it has none.
- **`stored`** reports what has *already* been computed without computing
  anything new — which is what a summary table needs, since reading a table must
  never kick off a scan or a sampling run. `Fit.posterior_summary` is a loop
  over it.

An answer is a `Marginal`: `value`, `sd`, `interval(p)`, `quantiles`, the
`method` that produced it, and the engine's diagnostics. A plot or a report
consumes one without caring where it came from.

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
| `ensemble` | affine-invariant ensemble (stretch) | 39 | 26 |
| `blocked` | per-block covariance | 12 | 64 |

The diagonal sampler produced **4** effective samples out of 8000 draws. This is
why `blocked` is the recommended backend for anything with correlated
parameters.

### The ensemble samplers

The covariance proposal has to get its covariance from somewhere — the curvature
at the optimum — and that is exactly what is missing when the optimum is not
where the posterior's mass is. The **ensemble** samplers avoid the question
entirely: they run many *walkers* at once and build each proposal out of the
positions of the other walkers, so the proposal inherits the posterior's scale
and correlations without anyone estimating them. Both are *affine invariant* —
they behave identically on a posterior and on any linear reparameterisation of
it — and both live in `chisurf.core.fitting.ensemble`, with no external MCMC
package involved.

- **`ensemble`** — the **stretch move** (Goodman & Weare). A walker is moved
  along the line joining it to another walker, by a factor $z$ drawn from
  $g(z)\propto z^{-1/2}$ on $[1/a, a]$, and accepted with probability
  $\min(1, z^{n-1} p(y)/p(x))$. One model evaluation per walker per step.
  Needs at least $2n$ walkers to span an $n$-dimensional space.
- **`slice`** — **ensemble slice sampling** (Karamanis & Beutler). The direction
  still comes from the other walkers, but the walker is then moved by
  one-dimensional [slice sampling](https://doi.org/10.1214/aos/1056562461) along
  it: a level $y$ is drawn below the density, an interval is stepped out until
  both ends fall below $y$, and points are drawn from it — shrinking it on each
  miss — until one lands above $y$. There is no accept/reject and no step size;
  every walker moves at every step, and the length scale is learnt from the
  ratio of expansions to contractions. It costs several model evaluations per
  walker per step and buys a much longer move: on a $\rho = 0.95$ Gaussian it
  delivered ~1.5x the effective samples per model evaluation of the stretch
  move.

Neither needs a gradient, a covariance, or a per-parameter step size, which
makes them the honest fallback when nothing is known about the posterior's
shape. What they do need is walkers — and an initial spread that is neither
degenerate nor tiny, since the ensemble takes its step size from itself.

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

## Linking reduces the dimension and makes sampling *harder*

This is the counter-intuitive one. Linking a parameter across $N$ datasets
removes $N-1$ free parameters — the fit is genuinely smaller. Measured on six
datasets of $c + a x^2$, linking $a$ took the dimension from 12 to 7. Sampling
then got **~50× worse** per model evaluation, and the shared parameter's
autocorrelation time went from 1 to 20.

Dimension is simply the wrong difficulty measure. **Coupling** is the right one.
Unlinked, the fit is six independent 2-parameter problems that each draw
essentially independent samples. Linked, it is one 7-parameter problem in which
$a$ is strongly correlated with every dataset's $c$ — and a conditional move can
only shift $a$ a little before the $c$'s object. The factor graph reports the
right quantity: number of components, separator, treewidth.

### Collapsing: integrate the private parameters out

At fixed shared parameters the datasets are conditionally independent, so each
one's *private* parameters can be optimised alone and integrated out
analytically (Laplace), leaving a target over the shared parameters only:

$$p(\theta_S \mid D) \;\propto\; \pi(\theta_S)\prod_k
  \int L_k(\theta_S, \theta_k)\,\pi_k(\theta_k)\,\mathrm{d}\theta_k .$$

That is a genuinely low-dimensional posterior — usually one to three parameters
however many datasets there are. Private parameters are then drawn from their
conditional Gaussian at each recorded shared state, so the output is still a
full joint sample (and the private parameters carry no autocorrelation of their
own — they are Rao-Blackwellised).

**This is exact when each dataset's model is linear in its private
parameters**, which covers amplitudes, offsets, scatter fractions and scaling
factors — most nuisance parameters in fluorescence decay and FCS models. Where
a private parameter enters non-linearly the Laplace integral is an
approximation and should be checked against a joint chain.

Measured, one shared parameter across datasets of $c + b x + d x^3 + a x^2$
(three private parameters each, 25 dimensions total):

| Sampler | τ(shared) | min ESS | ESS / 1000 evals | reported $a$ |
| --- | --- | --- | --- | --- |
| `blocked` | 589 | 3.4 | 0.045 | 1.25069 ± 0.00682 |
| `collapsed` | 4.9 | 411 | **1.154** | 1.24845 ± 0.03857 |

Note the second column of numbers as much as the first. The blocked run's error
bar is **5.6× too small** — with an effective sample size of 3.4 it had not
explored the posterior at all, and would have been quoted as a confident wrong
answer. Only the ESS diagnostic distinguishes it from the correct run.

The nested per-dataset optimisation is not free: with a *single* private
parameter per dataset, collapsing buys 3–4× the effective sample size per draw
but costs ~3.5× the evaluations, so it is roughly a wash. It wins outright as
soon as each dataset carries several private parameters — which is the normal
case.

## Adaptation and validity

Both random-walk samplers tune their proposal during a **warm-up** phase and
then **freeze** it. This is not an implementation detail: a chain whose
transition rule keeps changing is not a homogeneous Markov chain and is not
guaranteed to converge to the posterior. Only the frozen, post-warm-up draws are
recorded.

What the warm-up may change is deliberately limited. The curvature at the
optimum *is* the posterior covariance for a near-Gaussian posterior, and a short
chain cannot improve on it — a warm-up chain that has not yet mixed spreads
*less* than the posterior it is exploring, so its empirical covariance is biased
narrow. Replacing a good curvature seed with it makes the sampler dramatically
worse. So a block seeded from the curvature adapts only its **scale**; only a
block with no usable curvature (a global model, where the curvature's indices do
not apply) adapts its **shape**.

## Changing your mind about a prior, without sampling again

A prior changes the posterior but not the likelihood. Two posteriors that differ
only in their prior therefore have draws in common up to a reweighting:

$$w_s \;\propto\; \frac{p_{\text{new}}(\theta_s)}{p_{\text{old}}(\theta_s)}
  \;=\; \exp\!\big[\ln\pi_{\text{new}}(\theta_s) - \ln\pi_{\text{old}}(\theta_s)\big],$$

because the likelihood — the expensive part — is identical in both and cancels
exactly. Every prior that did *not* change cancels too, so the ratio is a
difference of two scalar densities per draw. **No model is evaluated**, and a
chain that took minutes to produce answers a new question in milliseconds.

The catch is the one every importance sampler has: if the new prior puts its
mass where the old chain has few draws, a handful of samples carry almost all
the weight, and the estimate is noise — silently, because the numbers still look
like numbers. **Pareto-smoothed importance sampling** addresses both halves. It
replaces the largest weights with the order statistics of a generalised Pareto
distribution fitted to them, which caps their variance without the bias of plain
truncation; and it returns the fitted shape $\hat k$, which *diagnoses* the
failure:

| $\hat k$ | meaning |
| --- | --- |
| below 0.5 | behaves like ordinary Monte Carlo |
| 0.5 – 0.7 | usable, converging slowly; treat tail quantiles with caution |
| above 0.7 | **not usable** — the weight variance is infinite; sample again |

That diagnostic is the reason to prefer this over raw importance sampling: it
gives an honest refusal instead of a confident wrong answer. Reweighting shares
the draws of *one* chain, so it can only reshape a posterior within the region
that chain explored; a prior that moves the mass somewhere it never visited is
exactly the case $\hat k$ flags.

## Reading a chain's convergence from a picture

$\hat R$ and the effective sample size are single numbers, and a threshold
cannot show you *how* a chain failed. Two plots do.

A **rank plot** ranks the draws across all chains together and histograms each
chain's ranks. If the chains sample the same distribution, each holds an equal
share of the low, middle and high ranks, so every histogram is flat. A chain
that lingers somewhere the others do not shows as a slope or a spike. This is
recommended over the traditional trace plot because a trace plot's resolution
collapses as the chain lengthens — it becomes an unreadable smear exactly when
there are finally enough draws to judge.

Reading one requires a calibrated eye, which is why ChiSurf states the verdict
rather than leaving it to be guessed. A rank histogram is *never* exactly flat:
under the null each bin count is $\mathrm{Binomial}(n, 1/b)$, and the largest of
$N$ standardised deviations is about $\sqrt{2\ln N}$ even when nothing is wrong.
Autocorrelation inflates that further, since no chain produces independent
draws. Both are accounted for, and the correction uses the **within-chain**
autocorrelation rather than the pooled effective sample size — the pooled figure
collapses precisely *because* chains disagree, so using it would let a badly
split run explain its own fault away.

An **ESS-growth** plot shows the effective sample size against the number of
draws taken. A converged sampler's grows linearly: twice the effort buys twice
the information. One that is stuck — in a mode, or with an autocorrelation time
longer than the run — flattens, and the flattening is visible long before any
single number crosses a threshold. A final ESS on its own cannot show this,
being one point on that curve with the shape discarded.

## When "uncorrelated" does not mean "independent"

The posterior graph shades each edge by how strongly two parameters constrain
each other. For a Gaussian posterior the correlation coefficient answers that
completely — mutual information is a monotone function of it,

$$I \;=\; -\tfrac12 \ln\!\left(1 - r^2\right),$$

so shading by $|r|$ and shading by $I$ produce the same picture. Away from
Gaussian they do not, and the failure is not subtle. Two parameters lying on a
**banana** — the ordinary shape when a lifetime trades against an amplitude near
a bound — or on a ring have $r \approx 0$ while determining each other almost
perfectly. Drawn from $|r|$ alone, no edge is drawn at all: the strongest
coupling in the fit becomes the one thing the picture omits.

Mutual information has no such blind spot, being zero **iff** two variables are
independent whatever the shape. ChiSurf reports it on the scale of a correlation
coefficient through the informational coefficient

$$r_I \;=\; \sqrt{1 - e^{-2I}},$$

which equals $|r|$ exactly for a Gaussian. That equality is the point: the two
numbers are directly comparable, and the quantity worth looking at is where they
**disagree**. A pair with $r = +0.02$ and $r_I = 0.97$ is one measurement wearing
the disguise of two.

Two things make the estimate a verdict rather than a number:

- **A measured null.** The plug-in estimator is positively biased — independent
  variables score above zero by roughly $(B-1)^2/2N$ nats, the same size as a
  weak real dependence. Miller–Madow removes the leading term, and the remainder
  is measured directly by permuting one variable, which destroys the dependence
  while preserving both marginals. Nothing is called dependent until it clears
  that null by several of its own standard deviations.
- **Thinning to independent draws.** A permutation destroys the chain's
  autocorrelation as well as its dependence, so on a sticky chain the null
  describes a far more informative sample than the one in hand. Measured on
  *independent* AR(1) columns, the uncorrected estimator called them dependent 7
  times in 12 at an effective size near 100, and every time at 20 — reporting up
  to $r_I = 0.51$ between variables sharing nothing. Thinning by the worse of the
  two autocorrelation times removes the effect entirely, and is the principled
  repair rather than a fudge: the mutual information of a posterior is a property
  of the posterior, not of how correlated the sampler's steps happened to be.

Two refusals matter as much as the measurement. A chain that $\hat R$ or the
effective sample size **rejected** cannot support the claim, because an unmixed
chain looks exactly like a curved posterior. And a parameter that barely moved is
reported as *unmeasurable*, never as independent — rank binning is blind to how
few distinct values a column holds, and a parameter pinned at a bound is one of
the commonest cases, not an exotic one.

## The numbers you actually publish

Nobody publishes an amplitude. What leaves ChiSurf is a **derived quantity** — a
FRET efficiency, a species- or fluorescence-averaged lifetime, a distance — each
a function $g(\theta)$ of the fitted parameters, and each printed for years as a
bare number with no error bar at all. The uncertainty was never absent; it was
simply never carried across $g$.

There are two ways to carry it, and the difference between them is not
cosmetic.

**Linear propagation** (the *delta method*) expands $g$ to first order about the
optimum:

$$\sigma_g^2 \;=\; \nabla g^{\mathsf{T}}\,\Sigma\,\nabla g,$$

with $\Sigma$ the parameter covariance. It needs no sampling and costs two model
touches per parameter. It is also **symmetric by construction** — it returns one
width and uses it on both sides — and that is exactly what a derived quantity in
fluorescence is usually not.

**Propagating draws** evaluates $g(\theta_s)$ at every posterior draw and reads
the interval off the resulting sample. It makes no approximation, so no
approximation can break, and it recovers the true shape.

The FRET efficiency shows why this matters. Written from lifetime contrast,

$$E \;=\; 1 - \frac{\langle\tau\rangle_{x,DA}}{\langle\tau\rangle_{x,D}},$$

it is a **ratio**, and a ratio's distribution is skewed as soon as the
denominator carries appreciable relative uncertainty — however Gaussian the
numerator and denominator each are. It is bounded above by 1 as well. Measured on
a fit whose denominator was moderately determined, the two routes gave:

| | lower arm | upper arm |
| --- | --- | --- |
| draws (true) | 0.278 | 0.101 |
| linear propagation | 0.163 | 0.163 |

The single symmetric width is **60 % too wide above and 1.7× too narrow below**,
at the same time. That is not a rounding difference: an interval built from it
overstates one end and understates the other, and nothing about the printed
$\pm\sigma$ says so.

So ChiSurf reports which route produced each row, prefers draws whenever the fit
carries a converged chain, and flags any quantity whose two arms differ by more
than sampling noise can explain. The flag uses the same calibrated threshold as
the per-parameter one: an asymmetry is only worth reporting when it is both
*detectable* given the effective sample size and *material* enough to change the
quoted interval.

Two rules keep the report honest:

- A chain that $\hat R$ or the effective sample size **rejected** is not used,
  because passing bad draws through a function does not improve them. The report
  falls back to linear propagation and says the chain was refused.
- A quantity that does not vary across the posterior is reported as *constant*,
  not as a failure to compute. Zero width is an answer.

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
- Karamanis, M. & Beutler, F. *Ensemble slice sampling.* Statistics and
  Computing **31**, 61 (2021).
- Neal, R. M. *Slice sampling.* Annals of Statistics **31**, 705–767 (2003).
- Vehtari, A., Simpson, D., Gelman, A., Yao, Y. & Gabry, J. *Pareto smoothed
  importance sampling.* Journal of Machine Learning Research **25**, 1–58 (2024).
- Zhang, J. & Stephens, M. A. *A new and efficient estimation method for the
  generalized Pareto distribution.* Technometrics **51**, 316–325 (2009).
