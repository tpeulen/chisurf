---
type: Concept
title: 'Factor graphs: the structure ChiSurf fits through'
description: A ChiSurf posterior factorises exactly, and making that factorisation explicit is what turns a global fit from a dense parameter vector into a structure that can be queried.
tags: [concepts, fitting, global-analysis, statistics]
anchor: concept-factor-graphs
sources:
  - text: Derived in part from the English Wikipedia article "Factor graph"
    url: https://en.wikipedia.org/wiki/Factor_graph
    licence: CC-BY-SA-4.0
  - text: Derived in part from the English Wikipedia article "Treewidth"
    url: https://en.wikipedia.org/wiki/Treewidth
    licence: CC-BY-SA-4.0
  - text: Derived in part from the English Wikipedia article "Junction tree algorithm"
    url: https://en.wikipedia.org/wiki/Junction_tree_algorithm
    licence: CC-BY-SA-4.0
  - text: Derived in part from the English Wikipedia article "Chordal graph"
    url: https://en.wikipedia.org/wiki/Chordal_graph
    licence: CC-BY-SA-4.0
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
A **factor graph** makes that product explicit. It is a *bipartite* graph with
two kinds of node — one per variable, one per factor — and an edge joining a
variable to a factor exactly when that variable is one of the factor's arguments
{cite}`kschischang2001,loeliger2004`. Nothing about it is specific to
fluorescence: it is the general representation of "this function is a product of
these smaller functions", and here the function is the posterior, the variables
are the free parameters, and the factors are the per-dataset likelihoods and the
per-parameter priors.

Bipartite matters. A variable and a factor are adjacent; two variables never
are. The coupling between parameters is therefore never stated directly — it is
*implied*, through the factors they share, and recovering it explicitly is the
first step of everything below.

What does **not** carry over is the inference. Factor graphs are best known as
the substrate for the sum-product algorithm, whose great success is decoding
capacity-approaching error-correcting codes — a discrete problem, where a
message is a distribution over finitely many symbols. A ChiSurf posterior is
continuous and its factors are likelihoods of real-valued data, so those kernels
do not apply. The **structural** machinery does, and that is all ChiSurf takes.

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

Recovering the parameter-to-parameter coupling and reading structure off it is a
standard three-step pipeline {cite}`lauritzen1988`, and ChiSurf runs exactly it:

1. **Moralise.** Replace the bipartite graph by an undirected graph over the
   *variables only*, in which every factor contributes a clique over its scope —
   a factor couples all the variables it reads. Two parameters end up adjacent
   exactly when some dataset's likelihood or some prior depends on both, which is
   to say exactly when they are **not** conditionally independent given the rest.
   This is {src}`chisurf/core/fitting/factorgraph.py#FactorGraph.markov_graph`.
2. **Triangulate.** Eliminate the variables one at a time; each eliminated
   variable together with its then-remaining neighbours becomes a clique. The
   result is a **chordal** graph, and chordality is what makes the rest cheap:
   listing all maximal cliques of a chordal graph is polynomial, while on a
   general graph it is NP-complete. An elimination order that adds no edges at
   all is a *perfect elimination ordering*, and a graph has one precisely when it
   is already chordal.
3. **Build the junction tree.** Take the maximal cliques as nodes and connect
   them by the maximum-weight spanning tree of the clique graph weighted by
   shared-variable count — the standard construction guaranteeing the *running
   intersection property*, without which the separators would not mean what they
   claim to.

Out of this come the **cliques** (the blocks a sampler or a scan should move
jointly), the **separators** (what the datasets genuinely share) and the
**treewidth**.

The elimination order is chosen by a greedy `min_fill` heuristic rather than
optimally, on purpose. Finding the best one is NP-hard {cite}`arnborg1987`;
there *is* a linear-time algorithm for any fixed treewidth bound
{cite}`bodlaender1996`, but its constant makes it theoretical, and the heuristic
is sufficient for the shapes real global fits take.

### What treewidth means

Treewidth is `max clique size − 1`. Informally it measures **how far a graph is
from being a tree**: the minimum is 1, and the graphs of treewidth 1 are exactly
the trees and forests. Equivalently it is the largest clique in a chordal
completion, minus one — which is why the triangulation step above computes it.

It is the fit's structural difficulty in a precise sense. The cost of exact
marginalisation is exponential in it, and it is the dimension a blocked sampler
has to move at once. The reason it is worth reporting at all is that a great many
problems that are hard in general become tractable once treewidth is bounded
{cite}`arnborg1989` — the parameter, not the size, is what decides.

So a star-shaped global fit — many datasets, a few shared globals — has a small
treewidth *however many datasets it holds*, and that is the structural reason
global analysis scales.

```{note}
The parameter was introduced by {cite}`halin1976` under the name *dimension* and
rediscovered independently; the name "tree-width" and the tree-decomposition
formulation now used everywhere come from {cite}`robertson1984`. Older
literature calls the same quantity by either name.
```

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

The last line is worth unpacking, because treewidth 1 is not "small", it is a
statement about shape: **the graphs of treewidth 1 are exactly the trees and
forests.** Both structures here are one. Before linking the moralised graph is
three disjoint `a—tau` edges, a forest of three components. After linking it has
four variables and three edges in one component — a *star*, with the shared
`tau` at the centre and each dataset's private amplitude hanging off it. Every
maximal clique is a single edge, so the largest is 2 and the treewidth is 1.

That shape is the general one for global analysis, and it is why the method
scales: adding a fourth, tenth or hundredth dataset adds another leaf to the
star. It adds variables and it adds likelihood factors, but it does not enlarge
the biggest clique, so the treewidth — and with it the cost of exact
marginalisation and the dimension a blocked sampler must move at once — does not
grow at all.

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
  make explicit, with {cite}`loeliger2004` as the readable introduction;
  {cite}`lauritzen1988` moralisation, triangulation and the junction tree;
  {cite}`halin1976` and {cite}`robertson1984` for the parameter now called
  treewidth; {cite}`arnborg1989` why bounded treewidth is the thing worth
  reporting; {cite}`arnborg1987` and {cite}`bodlaender1996` on why the
  elimination order is chosen greedily rather than optimally.
