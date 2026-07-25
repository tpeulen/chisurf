# 39 — Parameter uncertainty: priors, sampling and convergence

**Theory:** [Parameter uncertainty](../concepts/parameter_uncertainty.md) ·
**Code:** `chisurf.core.fitting.priors`, `chisurf.core.fitting.sample`,
`chisurf.core.fitting.diagnostics`

This tutorial turns a converged fit into a defensible uncertainty: attach prior
knowledge, sample the posterior, and check whether the chain is worth quoting.
Everything here runs headless.

## 1. Fit something

```python
import numpy as np
import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse

rng = np.random.default_rng(0)
x = np.linspace(1.0, 2.0, 96)
y = 1.0 + 2.0 * x + 0.5 * x**2 + rng.normal(0.0, 0.02, x.size)

data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.02))
fit = chisurf.core.fitting.fit.FitGroup(
    data=chisurf.core.data.DataGroup([data]),
    model_class=chisurf.core.models.parse.ParseModel,
)
fit.fit_range = 0, len(fit.model.y)
fit.model.func = 'c+a*x+b*x**2'
fit.model.find_parameters()
fit.run()

print(fit.chi2r)
```

Printing the fit shows the parameter table and, underneath it, the priors in
play and the interval for each parameter with the method that produced it.

## 2. Attach a prior

A prior is set on the parameter. Bounds *are* the uniform prior, so setting one
replaces the other rather than stacking with it.

```python
from chisurf.core.fitting.priors import NormalPrior, LogNormalPrior

params = fit.model.parameters_all_dict
params['c'].prior = NormalPrior(mu=1.0, sigma=0.05)   # independently measured
params['b'].prior = LogNormalPrior(mu=0.0, sigma=1.0)  # positive, order unity
fit.run()   # now maximum-a-posteriori rather than plain least squares
```

Available families: `UniformPrior` (a bound), `NormalPrior`,
`TruncatedNormalPrior`, `HalfNormalPrior`, `LogNormalPrior`,
`ExponentialPrior`, `GammaPrior`, `BetaPrior`, and `CallablePrior` for any
`logpdf(x)` you write yourself. Same-family priors combine in closed form:
`NormalPrior(1.0, 0.1) * NormalPrior(1.1, 0.2)` is one precision-weighted
Gaussian.

`fit.chi2r` still reports the **data** misfit — the prior never inflates or
deflates your goodness of fit.

## 3. Sample the posterior

```python
report = chisurf.core.fitting.fit.sample_fit(
    fit=fit,
    target_directory='./sampling',
    method='blocked',     # correlated proposal; see step 5
    steps=5000,
    thin=1,
    n_runs=4,             # independent runs -> a meaningful R-hat
)
```

This writes a timestamped directory containing the project, `parameters.json`,
a `chains/` folder with one tab-separated file per run, and `diagnostics.json`.
Each chain file has columns `chi2r`, `lnprior`, then one per parameter — the
data misfit and the prior stay separable, so a stored chain can be reweighted
under a different prior without resampling.

Use `n_runs` of at least 2. A single run cannot be compared with anything.

## 4. Read the diagnostics before the answer

```python
for e in report['parameters']:
    print(f"{e['name']:>4s}  {e['mean']:.4f} ± {e['sd']:.4f}   "
          f"ESS={e['ess']:.0f}  R-hat={e['rhat']:.4f}  tau={e['tau']:.1f}")

for w in report['warnings']:
    print('WARNING:', w)
```

```
   c  0.9756 ± 0.0394   ESS=1763  R-hat=1.0025  tau=11.3
   a  2.0305 ± 0.0544   ESS=1780  R-hat=1.0023  tau=11.2
   b  0.4918 ± 0.0184   ESS=1807  R-hat=1.0020  tau=11.0
   warnings: none
```

(`c` sits slightly below the true 1.0 because the `NormalPrior(1.0, 0.05)` from
step 2 is pulling on it — that is the prior doing its job, and `a` and `b` shift
to compensate along the correlated direction.)

Reject the run and sample longer if any parameter has **R-hat > 1.01** or
**ESS < 400**. The warnings list says which parameter and by how much; it is
also written to the log and repeated in `print(fit)`.

An empty warnings list means *nothing detectably wrong* — not *correct*.

Once a chain passes, `fit.posterior_summary()` quotes credible intervals from
it, labelled `mcmc`. A chain that failed its checks is **not** quoted: you get
the profile or covariance interval instead, and the failure appears in the
report.

```python
for e in fit.posterior_summary(p_value=0.68):
    print(e['name'], e['low'], e['high'], e['method'])
```

## 5. Choosing a sampler

| `method` | Use when |
| --- | --- |
| `collapsed` | a **linked** global fit — integrates each dataset's private parameters out and samples only the shared ones |
| `blocked` | correlated parameters, unlinked groups, single decays |
| `emcee` | many well-scaled parameters, or as an independent cross-check |
| `mcmc` | only for an uncorrelated, well-conditioned posterior |

On a deliberately collinear three-parameter fit, effective samples per 1000
model evaluations: `blocked` 64, `emcee` 26, `mcmc` 0.4. The diagonal proposal
of `mcmc` produced 4 effective samples out of 8000 draws — it is kept for
compatibility, not recommended.

## 6. Global fits

`FitGroup.model` is the **selected member's** model, so `sample_fit` on a group
samples that member. To sample the joint posterior of every dataset, ask for it:

```python
report = chisurf.core.fitting.fit.sample_fit(
    fit=group_fit,
    target_directory='./sampling',
    method='blocked',          # required for global_posterior
    steps=5000,
    n_runs=2,
    global_posterior=True,     # the joint posterior, not one member
)
```

Parameter names are then the group's prefixed ones (`1:c`, `1:a`, `2:c`, …).

With `method='blocked'` ChiSurf first checks whether the fit splits into
**independent components** — datasets sharing no parameter. If it does, each
component is sampled on its own and the results merged analytically (see the
[concept page](../concepts/parameter_uncertainty.md#dont-sample-what-doesnt-need-sampling-together)).
On 8 unlinked datasets this gave 7.8× the effective sample size for 40% fewer
model evaluations. If every dataset shares a parameter, there is one component
and one joint chain — nothing is lost, nothing is gained.

For finer control, drive the sampler directly:

```python
from chisurf.core.fitting import factorgraph
import chisurf.core.fitting.sample

joint = factorgraph.posterior_model(fit)   # the global model
joint.update_model()
r = chisurf.core.fitting.sample.walk_mcmc_blocked(
    fit=fit, steps=5000, step_size=0.02, thin=1, model=joint
)
print(r['parameter_names'], r['block_sizes'])
# ['1:c', '1:a', '2:c', '3:c', '4:c']   [1, 1, 1, 1, 1]
```

Blocks come from the fit's factor structure: each dataset's private parameters
form one block, the shared ones another. `r['block_acceptance']` reports the
acceptance of each, which is what tells you a particular block is badly scaled.

## 7. Linked global fits: use `collapsed`

Linking a parameter across datasets *reduces* the dimension but makes the
posterior **harder** to sample — the shared parameter is correlated with every
dataset's private ones. `collapsed` integrates the private parameters out
analytically and samples only the shared ones:

```python
report = chisurf.core.fitting.fit.sample_fit(
    fit=group_fit, target_directory='./sampling',
    method='collapsed', steps=3000, n_runs=2, global_posterior=True,
)
```

With three private parameters per dataset this gave 26× the effective samples
per model evaluation of `blocked` — and the `blocked` run's error bar on the
shared parameter was 5.6× too small, an under-sampled result that only the ESS
diagnostic exposed. Exact when the private parameters enter linearly
(amplitudes, offsets, scatter fractions); otherwise check against `blocked`.

With one private parameter per dataset the two are about even, so `blocked` is
fine there.

## 8. Inspecting the structure of a global fit

```python
print(joint.structure_report())
```

```
variables      : 5
likelihoods    : 4
treewidth      : 1
components     : 1
separators     : {1:a}
```

Read this as: five free parameters over four datasets, coupled only through
`1:a`. Fix that one parameter and the datasets become independent — which is
exactly the identifiability claim a global fit is making.

`components > 1` means the "global" fit is really several unrelated fits, and
nothing is being shared.

## 9. In the GUI

The **Sampling** button on the fit controller runs the same code on the server.
The backend comes from `optimization.sampling.method` in the settings
(`blocked` by default); `n_runs` and `steps` come from the controller.

When the job finishes, its **convergence verdict is written to the log** — the
warnings if the chain is not usable, otherwise a one-line all-clear. A finished
job is not the same as a trustworthy one, so do not treat the progress bar
reaching 100 % as a result. The full report is in `diagnostics.json` in the
output folder either way.

Programmatically the same verdict comes back from the job status:

```python
status = client.sampling_status(job_id)
status['status']      # 'completed'
status['converged']   # False if R-hat / ESS checks failed
status['warnings']    # what went wrong, per parameter
status['diagnostics'] # the full per-parameter report
```

## 10. Asking directly, without picking an estimator first

```python
from chisurf.core.fitting import engine

eng = engine.get_engine('auto', fit, use=('laplace', 'mcmc'))
eng.add_all_targets()
eng.run(steps=5000, n_runs=2)

for m in eng.marginals():
    lo, hi = m.interval(0.68)
    print(f"{m.name}: {m.value:.4f}  [{lo:.4f}, {hi:.4f}]  ({m.method})")
```

`auto` runs the estimators you allow and takes, per parameter, the best answer
that actually worked — labelled with which one that was. `laplace` costs
nothing, `profile` costs a re-fit per scan point, `mcmc` costs a sampling run;
`stored` costs nothing at all and reports only what is already there.

## 11. From a script, a macro or the server

The same query is on the stable API facade, so it works from the QtConsole, a
macro, a plugin, the CLI, and over RPC:

```python
from chisurf.core.api import ChiSurfAPI
api = ChiSurfAPI()

r = api.posterior(engine='stored')          # what is already known — free
for m in r['marginals']:
    print(m['name'], m['value'], m['low'], m['high'], m['method'])

r = api.posterior(engine='laplace', joint=['tau1', 'x1'])
print(r['joint']['correlation'])
print(r['log_evidence'])

# Fix a parameter and re-optimise the rest, then ask about another.
r = api.posterior(engine='laplace', condition={'tau2': 4.0}, targets=['tau1'])
```

Over the wire it is the `fit.posterior` RPC with the same arguments. `stored`
and `laplace` return immediately; `profile` and `mcmc` block for as long as they
take, so use the `fit.sample.*` / `fit.parameter_scan.*` job endpoints when you
need to poll progress.

## Checklist

- [ ] Priors reflect knowledge you actually have, not a convenience.
- [ ] `n_runs >= 2`.
- [ ] Every parameter R-hat < 1.01 and ESS > 400.
- [ ] `warnings` empty.
- [ ] Intervals quoted with their `method`.
