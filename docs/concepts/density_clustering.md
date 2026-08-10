---
type: Concept
title: Density-based clustering
description: 'Finding populations in a burst or pixel table without being told how many there are: core distances, mutual reachability, the cluster hierarchy, and the stability rule that reads a flat clustering off it.'
tags: [concepts, clustering, exploration, hdbscan]
anchor: concept-density-clustering
---

(concept-density-clustering)=

# Density-based clustering

A burst table is a cloud of points in a space whose axes are the observables —
FRET efficiency, stoichiometry, lifetime, anisotropy, duration. A population is
a *dense region* of that cloud. Everything else is what makes single-molecule
data hard: bursts that caught two molecules, bursts that photobleached
mid-transit, background events. Those points do not belong to a population, and
a method that has to assign every point to one will spread them across the
answers.

Two things follow, and they are what this page is about. The number of
populations is not known in advance, so it must not be an input. And a point
that belongs to nothing must be allowed to say so.

## Why not k-means

k-means — used elsewhere in ChiSurf where its assumptions do hold, notably to
initialise a hidden Markov model's states — asks for the number of clusters,
gives every point a label, and finds clusters that are round and of similar
size, because it minimises within-cluster squared distance. A burst population is often none of
those: a dynamic exchange between two states populates a *curve* in the
E–τ plane, not a ball; a rare population is small next to a common one; and a
quarter of the events may be junk.

Fitting a Gaussian mixture relaxes the roundness — it is the right tool when the
populations really are Gaussian and you want their fractions — but it still
insists on a component count and still assigns every point.

Density-based clustering asks a different question: *where is the cloud dense
enough to be a population, at any density at all?*

## Core distance: local density in one number

Take a point $x_i$ and the distance $c_i$ to its $k$-th nearest neighbour. That
is the **core distance**, and it is a density estimate with the units of the
space: small in a crowd, large in the wilderness. $k$ is the parameter
`min_samples`, and it counts the point itself, so $k = 5$ means "this point and
its four nearest neighbours".

`min_samples` is the smoothing knob. Raise it and small dense knots stop
registering as dense, so more points become noise and the clustering gets
conservative.

## Mutual reachability: a distance that respects density

Plain distance has a flaw for this purpose: two points in a sparse region can be
close to each other by accident and look like the seed of a cluster. The
**mutual-reachability distance** inflates the distance by the local sparsity of
*both* ends:

$$
d_{\text{mreach}}(x_i, x_j) = \max\bigl(c_i,\; c_j,\; d(x_i, x_j)\bigr)
$$

In a dense region $c_i$ and $c_j$ are small and this is just the distance. In a
sparse region it is at least the core distance, so the sparse points are pushed
apart from everything, including each other. Noise cannot bootstrap itself into
a cluster.

## The hierarchy, and why it replaces a threshold

DBSCAN takes a single density threshold $\varepsilon$ and calls everything denser
than it a cluster. On a table with a crowded population and a sparse one there is
no value of $\varepsilon$ that is right for both: raise it and the sparse
population dissolves, lower it and the crowded populations merge.

HDBSCAN {cite}`campello2013` removes the choice by doing *all* thresholds at
once. Build the minimum spanning tree of the mutual-reachability graph, then add
its edges in increasing weight: at every weight, the connected components are
exactly the DBSCAN clusters at that threshold. The result is a dendrogram over
all densities.

Two steps turn that into an answer:

**Condense.** Walking the dendrogram from the root, a split where one side has
fewer than `min_cluster_size` points is not a split — it is the surviving
cluster shedding noise. Recording it as such leaves a much smaller tree in which
every node is a candidate population, and every point carries the density
$\lambda = 1/d$ at which it fell out of its cluster.

**Select by stability.** A cluster that exists over a wide range of densities is
real; one that appears and immediately splits is a fluctuation. Its **stability**
is the mass it holds, integrated over its life:

$$
S(C) = \sum_{x \in C} \bigl(\lambda_{\text{out}}(x) - \lambda_{\text{birth}}(C)\bigr)
$$

The *excess of mass* rule keeps a cluster when it is more stable than all its
descendants put together, and otherwise keeps the descendants. Working from the
leaves up, this selects a set of clusters that never nest — the flat clustering.

## What comes out

Every point gets a label, with $-1$ for noise, and a **membership probability**
$\lambda_{\text{out}}(x) / \lambda_{\max}(C)$: one for a point that stayed with
its cluster to the very end, small for a point that fell out early. This is the
quantity to use when a population's mean is being computed and the fringe should
not count as much as the core.

Each returned cluster also carries its **persistence**, the stability that won it
its place. A population with low persistence next to its siblings is one to be
suspicious of.

## The parameters, in the order that matters

| Parameter | What it decides |
|---|---|
| `min_cluster_size` | The smallest group that counts as a population. The one parameter that has a scientific answer: how many bursts must a species contribute before it is a species? |
| `min_samples` | How aggressively points become noise. Defaults to `min_cluster_size`; lower it to keep more of the fringe. |
| `cluster_selection_method` | `eom` (default) keeps the most persistent clusters and tends to return few large ones; `leaf` takes the finest clusters in the tree. |
| `cluster_selection_epsilon` | A distance below which clusters are not split further. Use it when the method keeps subdividing a population you consider one. |
| `allow_single_cluster` | Whether "it is all one population" is an allowed answer. Off by default, because it usually is not the answer being looked for. |

## Two things to know about the result

**It is not deterministic across implementations, and the reason is ties.** A
mutual-reachability weight is frequently a *core distance* — and one core
distance is the weight of every edge it dominates, so hundreds of edges can share
a value. The minimum spanning tree is then not unique, and different libraries
pick different ones, which changes the dendrogram and can change the cluster
count. ChiSurf orders edges by weight *and then by their endpoints*, which makes
the tree unique and the clustering reproducible; the price is that a run may
differ from another package's on tie-heavy data, in the noise points and
occasionally in a marginal cluster.

**The metric is Euclidean, so the axes must be commensurate.** Distance in a
space whose columns are a FRET efficiency (0 to 1) and a duration in
milliseconds (0 to 20) is dominated by the duration. Standardise the columns
before clustering, or cluster on the axes that share units.

## See also

- Tools in ChiSurf: **ndX** (`chisurf/plugins/ndxplorer/`) offers this clustering
  over any set of columns and writes the labels back as a column.
- {ref}`concept-multidimensional-exploration` — the table these clusters are
  found in, and the projections that make them visible.
- The workflow: {doc}`ndX </guides/46_ndxplorer>`.

## References

- {cite}`campello2013` — hierarchical density estimates, the condensed tree and
  the excess-of-mass selection.
- {cite}`mcinnes2018` — the embedding often used to lay out a many-dimensional
  burst set before clustering it.
