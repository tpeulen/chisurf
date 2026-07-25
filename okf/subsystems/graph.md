---
type: Subsystem
title: Graph layer (chinet.graph)
description: In-tree graph containers, algorithms, layouts and GraphML I/O shared by the factor graph, the node editor and the global-parameter view.
resource: modules/chinet/chinet/graph/
tags: [graph, chinet, layout, factor-graph, node-editor]
timestamp: '2026-07-26T00:00:00Z'
---

# What it is

`chinet.graph` is the plain graph-theory layer that ships with the application.
chinet already models a *computation* graph (nodes, ports, links, evaluation);
this package sits underneath that vocabulary and provides the ordinary
mathematical object: containers with attributes, the algorithms over them, and
coordinates for drawing them.

It replaced the external graph library the tree used to depend on. Three
subsystems need the same handful of operations, all of them small, and an
external dependency for them meant a package in every environment and recipe
whose *layouts* — the part a user actually sees — were not ours to tune.

| Module | Holds |
|--------|-------|
| `graph.py` | `Graph` (undirected), `DiGraph`, node/edge views, `GraphError`, `CycleError` |
| `algorithms.py` | components, topological sort, DAG test, elementary cycles (Johnson), minimum/maximum spanning forest (Kruskal), all-pairs shortest paths (BFS/Dijkstra), `complete_graph`, `path_graph` |
| `layout.py` | `circular`, `shell`, `spectral`, `spring` (Fruchterman-Reingold), `kamada_kawai` (stress majorization), `arf` |
| `graphml.py` | `read_graphml` / `write_graphml` with typed attribute keys |

# Properties the callers rely on

**Determinism.** Node and edge iteration is insertion order; every algorithm
breaks ties on it, and every layout starts from a fixed configuration (a circle,
or a seeded cloud). The same graph therefore draws the same picture on every
call — a redraw that reshuffles the nodes is unreadable to a human, and the
posterior-graph views assert this.

**Attributes are live.** `G.nodes[n]` and `G[u][v]` return the actual dictionaries,
and an undirected edge shares one dictionary between both directions, so
`tree[a][b]["separator"] = ...` is visible from either end.

**No external dependency.** `numpy` only, and only for the layouts. A guardrail
test (`test/test_no_networkx_import.py`) fails if an import or a packaging
declaration reintroduces an external graph library.

# Layouts

Kamada-Kawai is the readable default for the small sparse graphs this project
draws. It minimises the stress `Σ (‖xᵢ − xⱼ‖ − dᵢⱼ)² / dᵢⱼ²` — drawn distance
against graph distance — by stress majorization (SMACOF), which needs nothing
beyond `numpy` and cannot increase the stress from one iteration to the next.
Edge `weight` is read as a *length*, so a caller can hand it a dissimilarity
(the correlation view passes `1 − |r|`) and let the geometry carry the message.

Nodes in different components have no graph distance; they are given 1.5× the
widest distance that does exist, which separates the components without letting
an "infinite" separation squash every real component to a point.

# Who uses it

* [Fitting engine](/subsystems/fitting.md) — `chisurf/core/fitting/factorgraph.py`
  builds the moralised Markov graph, finds independent components and takes the
  maximum-weight spanning tree of the clique graph as the junction tree;
  `graphview.py` lays out the posterior structure, correlation and junction-tree
  views.
* [GUI & AutoForm](/subsystems/gui-autoform.md) — the node editor's DAG checks,
  cycle highlighting and hierarchical auto-layout.
* The global-parameter view plugin — parameter/fit network, its layout combo box
  (`kamada_kawai`, `spring`, `shell`, `arf`, `spectral`) and its GraphML
  import/export.

# Related

* [Parameters](/subsystems/parameters.md) — parameter links live in chinet's
  *port* graph, which is a different graph from this one and keeps its own
  acyclicity check.
* [PRD-68](/prds/prd-68.md) — the factor graph that motivated promoting these
  primitives in-tree.
