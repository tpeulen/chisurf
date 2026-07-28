# Three-colour PDA (PDA3c)

:::{admonition} Theory
:class: seealso
Why three colours give more than three two-colour experiments, the coupled
transfer pathways, the burst likelihood, correlated distance distributions and
the multistate dynamics are explained in the concept page {ref}`concept-pda3c`.
:::

## What it does

Three-colour PDA recovers **three inter-dye distances and their correlations**
from the photon statistics of single bursts. The correlations are the reason to
run it: three separate two-colour experiments give three marginal distributions
and cannot say whether the distances move *together*, which is the difference
between one conformational coordinate and three independent ones.

Unlike two-colour {doc}`PDA <11_pda2c>`, which fits a histogram, PDA3c fits a
**per-burst likelihood**: each burst's five photon counts are scored directly.
There is no histogram to bin and no burst-size distribution to supply.

## In ChiSurf

PDA3c is its own experiment type (`PDA3c (3-colour)`) with an AutoForm-rendered
model in `chisurf/core/models/pda3c/`.

### Loading data

Three readers, all under the same experiment:

| reader | use it for |
| --- | --- |
| **PTU/HT3/SPC** | real measurements — the *same* reader as two-colour PDA, with three detection channels and two excitation windows |
| **Burst table (CSV/NPZ)** | a five-column table produced elsewhere |
| **Simulator** | trying the model, or checking a fit against a known truth |

The TTTR reader picks its path from the **Colours** selector, which defaults to
the number of configured detection-channel groups — so a three-channel setup
selects PDA3c on its own. With three colours the micro-time ranges are the
**excitation periods** (the blue and green halves of the PIE cycle) rather than
photon-selection windows.

:::{admonition} Burst selection is not identical between the two paths
:class: warning
The burst-table path finds time windows directly, while the two-colour engine
applies a further internal selection. On the same file at 2 ms / 20 photons
they yield 731 and 455 bursts respectively; the recovered proximity-ratio
*distributions* agree to a total variation of ~0.17. Comparable, but do not
treat a two- and a three-colour analysis of one file as sharing a burst set.
:::

### Setting up the model

**Distance populations** — one row per species: an amplitude, then a mean and
width for each of the three dye pairs. Start with one species and add more only
if the residuals ask for it.

**Distance correlations** — three per species, fixed at zero by default. Free
them to ask whether the distances move together. This is the measurement most
users are here for, so it is worth fitting deliberately: fit the means first,
then release the correlations.

**Instrument / corrections** — Förster radii, spectral crosstalk, relative
detection efficiencies, direct excitation and per-channel background. These
become the excitation and emission probability matrices the model composes; a
light-path simulation can supply the same two matrices directly.

**Corrections** — both off by default, because each is only physical under a
condition you have to assert:

- *Swapped labels* — turn on when the two labelling sites are chemically
  equivalent, so green and red land on either one.
- *Species brightness* — turn on when transfer changes how bright a species is
  enough to change its burst sizes. It alters the likelihood normalisation, so
  $\chi^2_r$ is not comparable across the switch.

**Exchange (dynamic)** — treats the species as interconverting states. With no
rates entered, the first two exchange at `K_ex`, the mean number of transitions
per observation window, and species three onward stay static; zero is the static
limit, so the dynamic model nests the static one exactly. Entering rates
switches to the full scheme — see below.

The states are the species you entered, *not* the mirror populations that
*Swapped labels* adds: a molecule keeps its labels for its lifetime, so the
mirrors interconvert among themselves. Switching both on therefore runs the
exchange twice — once per labelling — and mixes the two by $F_{labeling}$; the
rate scheme stays the size of the species table.

**Quadrature** — Gauss–Hermite nodes per distance axis. Five is ample; raise it
only if a fit looks resolution-limited.

## A worked run against known truth

The simulator reader exists so you can check the machinery before trusting it on
data:

```python
import chisurf.core.fitting.fit as fit_mod
from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
from chisurf.core.models.pda3c.pda3c import Pda3cModel

# Ground truth: three distances and a strong GR/BG correlation.
reader = Pda3cSimulatorReader(
    n_bursts=6000, r_gr=52.0, r_bg=46.0, r_br=68.0,
    sigma=6.0, correlation=0.8, photons_blue=40.0, photons_green=35.0, seed=11,
)
data = reader.read()[0]
fit = fit_mod.Fit(model_class=Pda3cModel, data=data)
model = fit.model

# Free the three mean distances, start them away from the truth.
model.find_parameters()
for parameter in model.parameters_all:
    parameter.fixed = True
for parameter, start in zip(model.species.means_of(0), (48.0, 50.0, 62.0)):
    parameter.fixed = False
    parameter.value = start
model.find_parameters()

fit.run()
print([round(float(p.value), 2) for p in model.species.means_of(0)])
# -> [52.10, 46.14, 66.60]   (truth 52, 46, 68)
```

Note which distance is least well recovered. `R_GR` and `R_BG` land within
0.15 Å; `R_BR` comes back 1.4 Å short. That ordering is not accidental —
blue→red is the weakest pathway and is partly degenerate with the
blue→green→red relay, so it carries the least information. Expect `R_BR` to be
your loosest number, and check its confidence interval rather than reading the
point estimate.

Now release the `GR`/`BG` correlation and refit: it comes back at **+0.767**
against a truth of 0.8. Generating with `correlation=0.0` and fitting the same
way returns **+0.024**. Run that uncorrelated control whenever a correlation
matters to your conclusion — a method that measures joint motion has to be
shown not inventing it.

## Fitting a kinetic scheme

The exchange scheme is a matrix of ordinary fitting parameters, one state per
distance population, so a scheme can be **recovered** and not only assumed.
`k_ij` is the rate from state *i* to state *j* in Hz.

```{figure} figures/pda3c_exchange.png
:name: fig-pda3c-exchange
:width: 90%

The exchange panel with three species and a linear chain 1↔2↔3: `k13` and `k31`
sit at zero, so there is no direct 1↔3 transition. The grid and the parameter
table below it are the same objects — type in one, fix or free in the other.
```

Say which transitions the scheme has by zeroing the ones it does not:

```python
model.dynamic = True
model.setup._window.value = 2e-3         # must match how the data was segmented

rates = model.rates_by_name()            # {"k1_2": parameter, ...}
for name in ("k1_3", "k3_1"):
    rates[name].value = 0.0              # a linear chain 1-2-3
for name in ("k1_2", "k2_1", "k2_3", "k3_2"):
    rates[name].fixed = False            # fit the rest
model.find_parameters()                  # <- populates the free-parameter list

rates["k2_1"].link = rates["k1_2"]       # or impose detailed balance
```

The scheme resizes with the species: adding a population adds a row and a
column and keeps the rates already entered. Leaving every rate at zero means
"no scheme", and the model stays on the static mixture or the `K_ex` route.

:::{admonition} A fitted rate is a timescale, not a measurement
:class: warning
On bursts simulated from a known two-state scheme by an independent forward
route, the profile likelihood along $k_\text{tot}$ peaks near 650–700 Hz for a
truth of 500 Hz — and that offset does not shrink with more sampling (unchanged
from 600 to 8000 trajectories, and across an eightfold range of occupancy
resolution). It comes from the model collapsing each state to its
distance-averaged probability vector before the time averaging. Compare
conditions and quote orders of magnitude; do not quote the absolute rate.
:::

## Uncertainties

Priors and both error-surface routes work on this model:

```python
from chisurf.core.fitting.priors import NormalPrior
import chisurf.core.fitting.sample

model.species.means_of(0)[0].prior = NormalPrior(mu=50.0, sigma=2.0)  # MAP
chain = chisurf.core.fitting.sample.walk_mcmc(fit=fit, steps=600, step_size=0.01)
```

:::{admonition} Prefer the MCMC interval
:class: note
Both routes bracket the true value, but the support-plane interval is currently
unreliable on this objective, for two reasons: its threshold uses the F-test
form, which rescales by $\chi^2_r$ and is right for least squares with unknown
variance but wrong for a likelihood deviance; and the adaptive scan was
returning its own grid edge rather than a crossing. Quote the **MCMC** interval
— it samples $e^{-\text{deviance}/2}$, the actual posterior here, and matches
the corrected likelihood-ratio interval to 2%.
:::

Read $\chi^2_r$ as a **relative** measure here — it settles near 2.4 for a good
fit rather than at one, for the reason given in the concept page.

## Troubleshooting

**The fit does not move.** Check the parameters are actually free:
`find_parameters()` is what *populates* `parameters_all`, so fix flags set
before calling it do nothing.

**A distance comes out systematically long.** Its neighbour is probably held at
a wrong value. The pathways compete, so a fixed neighbour is not a nuisance
constant — fit the three means together, or seed them all sensibly.

**Dynamics look wrong at slow exchange with three or more states.** The
multistate approximation degrades there. Slow exchange means the states are
resolved, so fit a static multi-species model instead.

## See also

- {doc}`PDA <11_pda2c>` — the two-colour method.
- {doc}`Burst identification <13_burst_identification>` — producing burst tables.
- {doc}`Parameter uncertainty <39_parameter_uncertainty>` — error surfaces.
- Concept: {ref}`concept-pda3c`.
