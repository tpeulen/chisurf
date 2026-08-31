---
type: Concept
title: 'Factor graphs: the structure ChiSurf fits through'
description: A ChiSurf posterior factorises exactly, and making that factorisation explicit is what turns a global fit from a dense parameter vector into a structure that can be queried.
tags: [concepts, fitting, global-analysis, statistics]
anchor: concept-factor-graphs
---

(concept-factor-graphs)=
# Factor graphs: the structure ChiSurf fits through

[Global analysis](global_analysis.md) says *what* linking asserts. This page is
the other half: **how ChiSurf represents a linked fit internally**, and why that
representation is a user-facing result rather than an implementation detail.

The short version: a ChiSurf posterior factorises exactly, the factorisation is
built as an explicit graph {cite}`kschischang2001`, and three things fall out of
it that are otherwise expensive or invisible — which models a change forces to
recompute, which parameters move together, and which datasets the fit has
actually coupled.

## The posterior factorises

Nothing about a global fit requires treating its parameters as one dense
vector. Dataset $k$'s model reads only some of them, and a prior touches one at
a time, so

$$p(\theta \mid D) \;\propto\;
  \prod_k L_k\bigl(\theta_{S_k}\bigr) \cdot \prod_i \pi_i(\theta_i) ,$$

where $S_k$ is the set of free parameters dataset $k$'s model actually reads.
A **factor graph** makes that product explicit: variable nodes are free
parameters, factor nodes are the per-dataset likelihoods and the per-parameter
priors, and an edge joins a parameter to every factor that reads it.

This is the same object used throughout probabilistic graphical modelling
{cite}`kschischang2001`. What does *not* carry over is the inference: the
discrete sum-product kernels those methods are built around do not apply to a
continuous fluorescence posterior. The **structural** machinery does, and that
is all ChiSurf takes.

## What the structure is for

### Relevance: the objective costs what moved

Before the graph, the global model flattened every local model's free parameters
into one vector and recomputed **all** local models on **every** objective
evaluation. A proposal touching one parameter of one dataset therefore cost $N$
model evaluations instead of one.

{src}`chisurf/core/fitting/factorgraph.py#FactorGraph.affected_fits` answers
"which local models must be recomputed when *these* parameters change?", which
makes the cost proportional to what actually moved rather than to the number of
datasets.

```{warning}
A parameter that no likelihood factor reads is reported separately, by
`unexplained_variables`. It is free but reaches no data as far as the graph can
see — either it genuinely does nothing, or a model couples it to its datasets by
some route other than a parameter link. Code that uses `affected_fits` to *skip*
work has to treat those conservatively and recompute everything, because an
empty answer there is not evidence that nothing depends on them.
```

### Structure: which parameters must move together

Moralising the graph, eliminating variables in a greedy `min_fill` order and
building a junction tree exposes the **cliques** (the blocks a sampler or a scan
should move jointly), the **separators** (what the datasets genuinely share) and
the **treewidth** {cite}`lauritzen1988`.

Treewidth is `max clique size − 1`, and it is the fit's structural difficulty:
the cost of exact marginalisation is exponential in it, and it is the dimension
a blocked sampler has to move at once. A star-shaped global fit — many datasets,
a few shared globals — has a small treewidth *however many datasets it holds*.

The elimination order is chosen greedily rather than optimally on purpose:
finding the best one is NP-hard {cite}`arnborg1987`, and the heuristic is
sufficient for the shapes real global fits take.

### Identifiability: what the fit actually couples

This is the part that belongs in a result, not a profiler. "These datasets are
conditionally independent given $R_0$ and $\tau_D$" is precisely the statement a
global analysis exists to make, and it is read directly off the graph:
`connected_components` returns the independent sub-problems, and `separators`
returns the parameters they share.

The consequence is blunt: **`components > 1` in something called a global fit
means nothing is being shared.** Three datasets, three components, no separator
is not a global fit — it is three separate fits sharing a window.

## Reading the structure report

`FactorGraph.describe()` prints the whole thing. Three decays of
$a\,e^{-x/\tau}$, each with its own amplitude, before and after linking $\tau$
— `host` is the `GlobalFitModel` fit built in the guide's
[joint-fit section](../guides/60_global_analysis.md):

```python
from chisurf.core.fitting import factorgraph

graph = factorgraph.build_factor_graph(host)
print(graph.describe())
```

```text
### BEFORE LINKING
variables      : 6
likelihoods    : 3
treewidth      : 1
components     : 3
separators     : (none — no shared parameters)

### AFTER LINKING tau
variables      : 4
likelihoods    : 3
treewidth      : 1
components     : 1
separators     : {1:tau}
```

Every line changes in a way worth reading:

- **variables 6 → 4.** Two followers left the free vector. This is the same
  free-parameter drop the [guide](../guides/60_global_analysis.md) tells you to
  check, and if it does not happen the link did not take effect.
- **components 3 → 1.** Before the link the "global" fit was three independent
  problems. This is the line that says whether a global analysis is happening at
  all.
- **separators (none) → {tau}.** The fit now names what its datasets share.
- **treewidth stays 1.** Sharing one parameter across a star of datasets does
  not make the problem structurally harder — which is why global fits over many
  datasets remain tractable.

```{note}
`FitGroup.model` is the model of the currently *selected* local fit, not the
global one. The joint parameter vector lives on `_model`, and
{src}`chisurf/core/fitting/factorgraph.py#posterior_model` resolves it. Building
a graph from the wrong one silently describes a single dataset instead of the
group — the counts look plausible, which is what makes it worth naming.
```

A plain {src}`chisurf/core/fitting/fit.py#Fit` yields a single likelihood factor
over all of its free parameters: one clique, treewidth `n_free − 1`. That is the
honest answer rather than a degenerate case — a single dataset has no
dataset-level structure to exploit. Structure appears with a `FitGroup`.

## Where this shows up elsewhere

Dimension is the wrong measure of how hard a linked fit is to sample, and the
factor graph reports the right one. Linking *reduces* dimension while making
sampling harder, because it introduces coupling; the components, separator and
treewidth are what describe that, and conditioning on the separator is what
makes collapsing possible. See
[parameter uncertainty](parameter_uncertainty.md) for the sampling side.

## See also

- Concepts: {ref}`concept-global-analysis` (what linking asserts) ·
  {ref}`concept-parameter-uncertainty` (why coupling, not dimension, sets
  sampling difficulty).
- Guide: [global analysis](../guides/60_global_analysis.md) — the Global View
  draws this same structure as an editable picture.
- Implementation: {src}`chisurf/core/fitting/factorgraph.py` ·
  {src}`chisurf/core/models/global_model/globalfit.py#GlobalFitModel`.
- Literature: {cite}`kschischang2001` factor graphs and the factorisation they
  make explicit; {cite}`lauritzen1988` moralisation, triangulation and the
  junction tree; {cite}`arnborg1987` why the elimination order is chosen
  greedily.
