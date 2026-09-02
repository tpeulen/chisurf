---
type: Subsystem
title: Graph Objective
description: The seam in chisurf/core/fitting/minimizer.py that builds the whole fitting objective in C++ when a model can be expressed as an Expression → ChiSquared → Minimizer pipeline, and falls back to a Python-residual director when it cannot.
resource: chisurf/core/fitting/minimizer.py
tags: [core, fitting, optimization, graph, bff]
timestamp: '2026-09-02T00:00:00Z'
---

# What the graph objective is

`graph_objective` (`chisurf/core/fitting/minimizer.py`) builds the entire
fitting objective — model evaluation, residual computation, and
Levenberg–Marquardt minimisation — as a C++ node graph in IMP.bff, so the
per-iteration SWIG boundary crossing drops from 4–5 (parameters, model,
residual) to **one** (`Minimizer.run()`). On a 512-point three-parameter
fit: 0.26 ms per iteration against 0.86 ms for scipy `leastsqbound`.

When the graph **cannot** be built — a prior the engine will not compile, a
subclass that computes its spectrum somewhere else, a mask the C++ side
cannot represent — `graph_objective` returns `None` and the caller falls
back to the **director**: the optimiser is still IMP.bff's C++ LM, but the
objective is a Python callback reached through a SWIG director once per
residual evaluation. One algorithm, two transport paths.

# What builds

## Single model: Expression → ChiSquared → Minimizer

`_single_objective` builds three nodes:

1. **`Expression`** compiles `model.func` (a Python-evaluable string) into a
   C++ expression tree. Variable names come from `_parameters_equation` —
   the model's equation parameters, not its node ports.
2. **`ChiSquared`** holds the data, the fit range, the noise model, and the
   mask. It links the Expression's output as its `model` input and computes
   weighted residuals.
3. **`Minimizer`** holds one `Port` per free parameter, wired to the
   Expression's input ports. It runs bounded LM (sin/sqrt
   reparameterisation) in C++ and writes the solution back through ordinary
   setters.

## Global model: one Expression → ChiSquared per member, JointChiSquared over them

`_group_objective` builds the same pipeline per member and wraps them in a
`JointChiSquared` whose residual is the members' residuals end to end —
exactly what `GlobalFitModel.weighted_residuals` concatenates. Parameters
shared between members are `Port` links, so a group takes one LM step using
every dataset's curvature at once.

## Lifetime / FRET model: producer chain → TcspcDecay → ChiSquared

`_lifetime_objective` builds a producer chain in front of the decay node:

- For a **plain lifetime model**: the `TcspcDecay` node convolves the
  lifetime spectrum with the IRF.
- For a **FRET model**: a `FretSpectrum` or `AnisotropySpectrum` producer
  node generates the donor/acceptor lifetime spectrum, which feeds the
  decay node. The two part company in `_spectrum_chain`.
- For an **anisotropy model**: a rotation link adds a polarised spectrum
  chain (VV/VH).

The producer-node pattern: a C++ node (e.g. `FretSpectrum`,
`AnisotropySpectrum`, `FcsMdfCurve`) generates a spectrum or shape that the
compiled `Expression` reads as a live-linked port rather than a copy. The
node's output port is linked to the Expression's input, so each LM step
re-evaluates the producer without Python involvement.

## FCS MDF model: FcsMdfCurve producer → Expression

`_fcs_mdf_producer` builds an `FcsMdfCurve` C++ node (Enderlein MDF kernel
with Gauss-Hermite quadrature) whose output (`g_mdf`) is linked into the
compiled expression. The model's `_diffusion_expression` returns `"g_mdf"`
for MDF mode instead of the analytical Gaussian, and
`_parameters_equation` returns the equation parameters (N, b, bg, bunching,
anticorr) rather than node ports.

# What refuses — and why each refusal is semantic

| Refusal | Reason |
| --- | --- |
| No free parameters | Nothing to optimise. |
| Informative prior (non-uniform) | The graph produces data residuals only; a prior appends rows the graph does not produce. The sampler asks with `allow_priors=True` because it evaluates priors natively. |
| `_expression` or `_parameters_equation` is `None` | The model is not a parse model — it uses an eval()-only equation. |
| Duplicate equation-variable names | Ambiguous wiring. |
| A variable naming neither a parameter, an axis, nor a producer | The graph cannot supply a value for it. |
| No axis at all (`"x"` not in variables, no `graph_axes()`, no producer) | Not a curve model. |
| A `redundant` or `_callable` parameter | A derived value that the graph has no way to recompute. |
| A mask the C++ side cannot represent | The graph would silently drop it. |
| A free parameter the node does not carry | A subclass adding a term or a nuisance this builder does not know. |
| `_forward_differences_resolved` fails | MINPACK's relative-step Jacobian cannot be trusted at the solution. |

None of these is a limitation of the C++ — each is a case where the graph
would not be evaluating the same objective as the Python path.

# Port and keepalive lifetime rules

The graph is **private to the fit**, and that is the design. Driving the
model's own parameter ports from C++ would bypass the `_frozen_value` cache
that `frozen_structure` maintains during a fit run — a port written from C++
is not seen by the next Python read. A private graph means the only thing
that crosses back is the answer, written through the ordinary setters.

References that must outlive the function return:

- **`_graph`**: `(node, chi2, carried, model_in, keepalive)` — the node
  tree, the ChiSquared, the parameter→port pairs, and the keepalive tuple
  (axes, output ports). The C++ side holds only weak references to Python
  proxies, so these must stay reachable.
- **`_sampler_surface`**: `(chi2, parameter_ports, "chi2")` — what the
  sampler reads to evaluate the objective natively off the ports.
- **`_decay`**: the decay node, for callers that need to inspect what was
  built.

# The graph cache

`_cached_graph` caches a built graph keyed on (`_graph_cache_key`):

- `id(model)`, `id(fit.data)` — object identity
- `model.func` — the equation string (a model may regenerate it)
- `tuple(id(p) for p in free)` — parameter identities
- `fit.xmin`, `fit.xmax` — the fit window

**Deliberately omitted**: the data arrays (`DataCurve.x`/`.y` build a fresh
array on every access, so `id()` is useless). The cache is dropped at the
top of every `Fit.run`. What that leaves uncovered: mutating a data buffer
in place between two analyses of the same finished fit.

# Curvature over the graph

`curvature_over_the_graph` differences the graph at `approx_grad`'s step
rule (`eps * max(|x|, 1)`, an absolute floor) to build the covariance
matrix. Every consumer of a curvature goes through it: the error estimate,
the posterior view, the derived-quantity propagation, both sampler
preconditioners, and `Fit.grad`. A TCSPC `fit.run()` now makes two Python
`update_model()` calls, which is what a parse fit always made.

# Protocols a model can implement

| Protocol | What it does | Where |
| --- | --- | --- |
| `_expression` (str) | The equation string the engine compiles | `model._expression` |
| `_parameters_equation` (list) | Parameters in equation order | `model._parameters_equation` |
| `func` (str) | The compiled expression (regenerated by some models) | `model.func` |
| `graph_axes()` (dict) | Name → flat float array, each data-length | `model.graph_axes()` |
| `fits` (list) | Present on `GlobalFitModel` — triggers group path | `model.fits` |

A model that implements `_expression` and `_parameters_equation` is a parse
model the graph can build. A model that also has `graph_axes()` evaluates
over axes of its own instead of (or beside) the data's `x`. A model whose
`fits` is not `None` triggers the group path.

# Publication path

`_publish_curve` publishes the model's curve after a fit run by writing the
graph's computed output back through the ordinary model setters and calling
`model.update_model()` once. This is why the graph can be private: the answer
crosses back through the same setters a Python fit would use, and the model
recomputes its own curve for display.

# Where to pick this up

- **Code**: `chisurf/core/fitting/minimizer.py` — `graph_objective` is the
  entry point; `_single_objective`, `_lifetime_objective`, `_group_objective`
  are the three builders.
- **C++ nodes**: `imp.bff/include/` — `Expression`, `ChiSquared`,
  `Minimizer`, `TcspcDecay`, `FretSpectrum`, `AnisotropySpectrum`,
  `FcsMdfCurve`, `JointChiSquared`.
- **Tests**: `imp.bff/test/minimizer/census_models.py` — the census that
  asks every model whether it builds a graph **and** whether the graph's
  curve matches `update_model()`.
- **Fallback**: `director_objective` — the SWIG director path for models
  the graph cannot represent. Same LM algorithm, Python-residual transport.
- **Related**: [fitting](/subsystems/fitting.md) for the overall fit
  lifecycle, [PRD-105](/prds/prd-105.md) for the migration plan.
