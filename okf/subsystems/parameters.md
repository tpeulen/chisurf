---
type: Subsystem
title: Parameters
description: Scalar Parameter objects, bounds, the link dependency graph, and how free parameters become fitting degrees of freedom.
resource: chisurf/core/parameter.py
tags: [core, parameters, fitting, dependency-graph]
timestamp: '2026-07-05T00:00:00Z'
---

# Parameter

`Parameter` (`chisurf/core/parameter.py`) is a single scalar backed by a
low-level `chinet.Port`. Its `value` can come from three sources, checked in
order: a **link** to another parameter, a Python **callable** (dynamic value), or
the port's stored scalar. Reads clamp to bounds when enabled; writes are ignored
while a callable is the source of truth. `Parameter` supports arithmetic
(`+ - * / ** %`, `__float__`) so expressions read naturally.

| Attribute | Meaning |
|-----------|---------|
| `value` | current scalar (link/callable/port) |
| `bounds`, `bounds_on` | `(lb, ub)` tuple + enforcement flag (on the port) |
| `prior` | prior distribution — bounds are its `UniformPrior` case |
| `fixed` | frozen during optimization |
| `link` / `is_linked` | follows another parameter's port |
| `is_link_master` | UI-only hint: this parameter is a link target |
| `controller` | attached GUI widget, if any |

# Priors (bounds unified)

`Parameter.prior` is the single concept for both hard bounds and soft prior
belief. An active bound surfaces as a
[`UniformPrior`](/subsystems/fitting.md); a smooth prior (Gaussian, log-normal,
…) stores its serialisable spec on the underlying `chinet.Port` (`port.prior`,
so it round-trips through the port JSON/pickle) and mirrors its `support()` onto
the port bounds. A `CallablePrior` (arbitrary `logpdf(x)` callback) is the most
general form and is kept in memory only (runtime-only, not persisted). The
getter prefers the live prior object, else rebuilds from the port spec, else
reports the bound as a uniform prior. Serialisation flows through
`get_state`/`set_state` (project JSON) and the `parameter.set_prior` RPC. Priors
feed the fit objective (MAP residuals) and the sampler (`lnprior`); see
[fitting](/subsystems/fitting.md).

# Links and the dependency graph

Setting `p.link = q` makes `p` a follower whose value tracks `q`. This adds a
directed edge in a shared graph maintained by `chinet` at the `Port` level. The
graph is kept acyclic: `chinet.Port.would_create_cycle` (Kahn's algorithm)
rejects links that would form a cycle, surfaced by the side-effect-free predicate
`Parameter.check_recursive_link(current, target)` and enforced in the `link`
setter (raising `ValueError` on a recursive link). Passing `link = None` unlinks.
Because links live in the port graph, changing a master propagates to all
followers without extra bookkeeping.

# Out-of-fit parameters and the Global View

Every `Base` instance (so every parameter, group, model and fit) self-registers in
a process-global `WeakValueDictionary`, `Base._uuid_index`, resolvable by
`Base.find_by_uuid(uid)` regardless of whether the object sits inside `chisurf.fits`.
This is the identity backbone that lets parameters living **outside** a fit — e.g. a
plugin's working model — be viewed, edited and linked exactly like fit parameters.

Two seams build on it:

- **Enumeration.** `chisurf/core/parameter_group_registry.py` is a process-global,
  weakref-backed registry keyed by a stable `owner_id`. A model-bearing plugin calls
  `register_parameter_group(group, owner_id=…, label=…)` (or the
  `PluginContext.register_working_model` convenience) to expose its group; re-registering
  an id replaces, and unregistering severs inbound/outbound links so no dangling follower
  remains. It is surfaced as `chisurf.registered_parameter_groups()` and on
  `SessionState.registered_parameter_groups`, mirroring `chisurf.fits`.
- **Mutation.** The parameter service (`chisurf/server/services/parameters.py`) resolves a
  parameter by a global `parameter_uid` (plus an `owner_uid` finalisation target) in
  addition to the legacy `fit_index`/`fit_uid` + name path. `parameter_link` accepts a
  `target_parameter_uid`, so any parameter can link to any other across the fit/plugin
  boundary through one RPC path (local/hybrid mode; a pure separate server process cannot
  see GUI-side plugin groups — a documented limitation).

The **Global View** Parameters tab renders all of this: an AutoForm
[`global_parameter_table`](/subsystems/gui-autoform.md) section spanning every fit
parameter plus every registered out-of-fit group, with Owner and cross-owner Link columns.

The seam is what makes a *drawn* quantity a first-class parameter. An ndX overlay
curve — a static FRET line, a Gaussian on E — holds its free parameters in a group
registered as `ndxplorer.curve.<n>`, so its `tau_d0` can follow the donor lifetime of
a real TCSPC fit, and re-fitting that lifetime redraws the line. The same group is
what a fit of the curve to the displayed data optimises: fix/free and bounds are set
once, in the table the user is looking at, and a *linked* parameter is held (its value
belongs to its master) rather than fitted and written over.

The **2-D Gaussians** of ndX's fit panel are the same arrangement applied to a
mixture rather than a curve (`ndxplorer/core/gaussian_parameters.py`, registered
as `ndxplorer.gaussians`). Six parameters per component — `x`, `y`, `sd_x`,
`sd_y`, `rho`, `w` — laid out **component-major**, which is exactly what
`PairedParameterTableWidget` renders one component per row. The constraint the EM
applies inside its M step comes from the parameters (`fixed` *or* `is_linked`),
so a held centre is held *during* the fit and not merely restored after it, and
the covariance the EM works in is reconstructed from the widths and correlation
the table shows. Removing a component renumbers the survivors and breaks the
links into it (`parameter_group_registry.break_links`, the public form of what
unregistering a whole group does), so no follower is left reading a parameter
nothing updates.

# Description registry scoping

When a `Parameter` is constructed without an explicit `description=`, it
falls back to `chisurf.core.settings.parameter_registry`
(`chisurf/core/settings/constants/parameter_registry.json`, generated by
`build_tools/dev_utils/export_fitting_parameters.py` scraping
`FittingParameter(...)` call sites). Two unrelated classes reusing the same
bare parameter name (e.g. FRET's `R0` — the Förster radius — vs. an unrelated
model's own `R0`) must not cross-contaminate: the lookup in
`Parameter.__init__` tries, in order, (1) an explicit `registry_id=` kwarg
(namespaced convention, e.g. `"rics.D"`, `"fcs_mdf.wem"`) against the
generator's `by_qualified_id` index, (2) a class-scoped match derived by
inspecting the constructing frame for the owning `self`
(`"<ClassName>.<name>"`, matching what the generator records as that call
site's "class" context), and only then (3) the legacy bare-name
`parameters[name]` entry — but only when the generator has not flagged it
`"ambiguous"` (more than one class contributing to that bare name). This is
purely a lookup/generator change; the registry's top-level `parameters` shape
is unchanged so existing bare-name consumers (e.g.
`chisurf.core.project.mmfdb_adapter.resolve_parameter_name`, the flrCIF
`flrcif_item_id` mapping) are unaffected.

This three-step resolution is factored into the shared helper
`chisurf.core.settings.describe_parameter(name, owner=None, registry_id=None)`,
which takes the owning class name explicitly (rather than walking the call
stack). `Parameter.__init__` calls it with `owner=_owning_class_name()`; the
AutoForm renderer reuses the same helper (see
[[gui-autoform]]) so a description shown in a fitting widget and one shown on an
AutoForm field are resolved identically.

# Groups

`ParameterGroup` (`parameter.py`) is a Base-backed collection; attribute writes
matching a contained parameter's name are routed to that parameter's `value`
setter, and reads return the scalar. `FittingParameterGroup`
(`chisurf/core/fitting/parameter.py`) is the group models subclass — it
distinguishes:

- `parameters_all` — every parameter (fixed, linked, free).
- `parameters` — **free** parameters only (`not fixed and not is_linked`).
- `parameter_values` / `parameter_bounds` — vectors over the free set.
- `aggregated_parameters` — nested `FittingParameterGroup`s discovered by
  `find_parameters`, enabling hierarchical models.

**Discovery is lazy, and that is a contract.** A group cannot walk itself in
`__init__` — a subclass attaches its parameters after `super().__init__` returns
— so `_parameters` stays `None` until the first read of `parameters_all` runs
`find_parameters`. An empty *list* is a real answer ("this group owns nothing")
and is never re-walked; only `None` means "never looked". Before that guarantee
existed, discovery happened solely as a side effect of `Model.update` and
`FitGroup.run`, and a fit that had been built but not yet updated reported **no
parameters at all** to every reader outside the model — the RPC fit DTOs, and
through them the parameter link menu and the Global View — while its own widgets,
which hold their parameters directly, showed the full set.

# Fitting parameters and degrees of freedom

`FittingParameter(Parameter)` adds fit-specific state: `error_estimate`
(covariance or support-plane), `parameter_scan`/`scan_result` (χ² scans via
`scan` / `adaptive_scan`), and `fit_idx` (which fit uses it, via
`find_fit_idx_of_parameter`). The set of **free** parameters is exactly the
optimizer's degrees of freedom: `Fit.run` (`chisurf/core/fitting/fit.py`) calls
`model.find_parameters(...)` then `leastsqbound(get_wres, model.parameter_values,
bounds=model.parameter_bounds, ...)`. Fixing a parameter or linking it to a
master removes it from `parameters` and therefore from the fit, without deleting
it — the model still reads its value. This is how global fits share one degree of
freedom across datasets.

# Editing a parameter from a GUI

Every parameter editor — the per-parameter row widget, the detail popup and the
AutoForm [parameter tables](/subsystems/gui-autoform.md) — owes an edit the same
three things, and does them through one shared implementation
(`ParameterActionsMixin.apply_value` / `apply_fixed` / `apply_bounds_on` /
`apply_bounds`): a **local write**, an **RPC** to the backend through the fitting
client, and a **provenance-trace entry** so the edit appears in the
[history](/subsystems/history.md) projection. Omitting the local write leaves the
edit lost whenever the RPC server is unreachable (the GUI starts, with a warning,
in that state); omitting the trace drops the edit from the history. A write of the
value a parameter already holds is dropped — an editor refresh re-emits its
editor's signals, and recording those as edits filled the history with no-op
operations.

# Linking a parameter from a GUI

The link menu (`ParameterActionsMixin.build_link_menu`, offered by every
parameter editor) is built from the fit DTOs, not from the object graph, so it
inherits whatever those carry. Each entry addresses its target by **UUID**
(`parameter.link` resolves `target_parameter_uid` first), which is what lets a
name that exists in several fits — `tau1` in every curve of a global analysis —
resolve to the one that was clicked; a name-only menu had to exclude every
same-named parameter and so made the most common global-analysis link
unreachable. A fit group is expanded into its **member fits** when it holds more
than one curve, because `FitGroup.model` answers with the selected member only.
Targets appear twice: grouped as the model presents them
(`aggregated_parameters`, carried per entry as `group`) and flat under "All
parameters". A fit with nothing to offer says so rather than opening an empty
popup.

Every parameter RPC — value, fixed, bounds, link, unlink — is addressed through
one helper (`ParameterActionsMixin._rpc_address`) and carries the parameter's
**UUID** plus its owner's. A name and a fit only resolve for parameters that live
in a fit, so an out-of-fit parameter came back `parameter '<name>' not found`
(unlinking an ndX constant) or, worse, matched a same-named parameter in whichever
fit was asked. Unlinking runs through the same local-echo/RPC/trace path as the
edits (`apply_unlink`), so a host that declares its parameters backend-free
(`remote=False`, ndX's constants) unlinks locally instead of failing.

**A table shows what the fit will move.** A linked follower is drawn *italic* and
its value dimmed; a fixed parameter's value is dimmed. The dim colour comes from
the palette's disabled role, so it follows the theme rather than assuming a
background. The parameter tables and the Global View table share the rule.

The refresh path runs the other way and is **thread-bound**: a server-side change
(a fit run, linked-parameter propagation, any RPC that finalizes a model) reaches
`parameter.controller.finalize()` on the RPC thread, which runs no Qt event loop.
A timer created there never fires and a `dataChanged` emitted there is dropped by
Qt outright, so both editors kept painting superseded numbers; `finalize` now
posts itself to the thread its widgets live on (`QCoreApplication.postEvent`) and
runs the repaint there.

See [fitting](/subsystems/fitting.md), [models](/subsystems/models.md), the
[data model](/subsystems/data-model.md), and the [action layer](/architecture/action-layer.md)
that mediates parameter edits. Parameters reach GUIs/plugins through the
[API facade](/architecture/api-facade.md), not the
[runtime globals](/architecture/runtime-globals.md).
