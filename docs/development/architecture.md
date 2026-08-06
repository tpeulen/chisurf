---
type: Development Note
title: ChiSurf Software Architecture
description: This document describes the current source layout and runtime architecture of ChiSurf.
tags: [development, architecture]
audience: developer
---

# ChiSurf Software Architecture

This document describes the current source layout and runtime architecture of
ChiSurf. It is intentionally implementation-oriented: if this file disagrees
with `chisurf/`, the source tree wins and this document should be fixed.

## Source Layout

| Path | Role |
|------|------|
| {src}`chisurf/__init__.py` | Runtime globals, lazy accessors, logging setup, compatibility shims |
| {src}`chisurf/__main__.py` | GUI application entry point for `python -m chisurf` |
| `chisurf/core/` | Domain objects, fitting, data, models, math, settings, actions, API facade |
| `chisurf/core/actions/` | Action registry, dispatcher, and state-change action implementations |
| `chisurf/core/api/` | Hybrid API facade, plugin context, remote client wrapper, optional proxies |
| `chisurf/gui/` | Qt application, widgets, plots, resources, and GUI startup helpers |
| `chisurf/history/` | Operation-history recording and replay support |
| `chisurf/macros/` | Scriptable convenience entry points used by GUI, console, and plugins |
| `chisurf/plugins/` | Built-in plugin packages and plugin utilities |
| `chisurf/server/` | Headless ZMQ/JSON-RPC server, session state, dispatcher, services, transport |

## Runtime Layers

```text
Presentation
  chisurf.gui, chisurf.plugins, chisurf.macros, scripts/CLI
      |
      v
Facade and Action Routing
  chisurf.core.api.ChiSurfAPI
  chisurf.core.api.PluginContext
  chisurf.core.actions.ActionDispatcher / ActionRegistry
      |
      v
Service and Transport
  chisurf.server.app.ChiSurfServer
  chisurf.server.dispatcher.ServiceDispatcher
  chisurf.server.transport.zmq.ZmqServer / ZmqClient
      |
      v
Domain and Session State
  chisurf.core data/model/fitting objects
  chisurf.server.session.SessionState
  runtime globals: chisurf.fits, chisurf.imported_datasets, chisurf.cs
```

## Important Runtime Globals

{src}`chisurf/__init__.py` still exposes several process-local globals. These are
part of the current hybrid architecture and remain important for GUI and legacy
macro compatibility.

| Global | Meaning |
|--------|---------|
| `chisurf.fits` | Process-local list of current fit groups |
| `chisurf.imported_datasets` | Process-local list of imported datasets |
| `chisurf.cs` | Current Qt main window instance in the GUI process |
| `chisurf.experiment` | Registered experiment objects keyed by name |
| `chisurf.working_path` | Current working path used by GUI and macros |
| `chisurf.action_dispatcher` | Lazily created `ActionDispatcher` |
| `chisurf.action_registry` | Dispatcher registry for action metadata |
| `chisurf.action_catalog` | Callable returning action catalogue metadata |
| `chisurf.action_execute` | Callable for action execution by canonical or dotted name |

These globals are not the target architecture for server-owned state. New code
that needs datasets, fits, parameters, project state, or server communication
should prefer `chisurf.core.api.ChiSurfAPI` or `chisurf.core.api.PluginContext`.

## Action Layer

The action layer lives under `chisurf/core/actions/`.

| File | Role |
|------|------|
| `_infra.py` | `ActionSpec`, `ActionRegistry`, `ActionDispatcher`, default dispatcher helpers |
| `_decorator.py` | Action registration decorator support |
| `dataset_actions.py` | Dataset state-change actions |
| `fit_actions.py` | Fit state-change actions |
| `model_actions.py` | Model actions |
| `parameter_actions.py` | Parameter actions |
| `project_actions.py` | Project actions |

`chisurf.__getattr__` lazily exposes `action_dispatcher`, `action_registry`,
`action_catalog`, and `action_execute`. Action names may be canonical internal
names or dotted aliases, depending on the registered action spec.

## API Facade

`chisurf.core.api.ChiSurfAPI` is the stable facade for GUI, macros, plugins, and
the console.

Modes:

| Mode | Behavior |
|------|----------|
| `local` | Read and mutate current in-process objects for legacy workflows |
| `hybrid` | Preserve local behavior while allowing migrated server paths |
| `server` | Route operations through `ChisurfClient` RPC calls |

Related classes and modules:

| Symbol | Path | Role |
|--------|------|------|
| `ChiSurfAPI` | `chisurf.core.api` | Dataset, fit, parameter, project, session facade |
| `PluginContext` | `chisurf.core.api.context` | API/client/main-window context passed to migrated plugins |
| `ChisurfClient` | `chisurf.core.api._client` | High-level client over ZMQ JSON-RPC transport |
| `RemoteError` | `chisurf.core.api._client` | Client-side structured RPC error exception |

## Server Architecture

ChiSurf includes a headless server based on ZMQ and JSON-RPC 2.0. The server is
Qt-free and lives under `chisurf/server/`.

| Path | Role |
|------|------|
| `app.py` | `ChiSurfServer`, server wiring and lifecycle |
| `__main__.py` | `python -m chisurf.server` entry point |
| `startup.py` | Subprocess startup/termination helpers |
| `dispatcher.py` | `ServiceDispatcher`, method registration and invocation |
| `server_methods.json` | Declarative server RPC registry |
| `client_methods.json` | Declarative client wrapper method registry |
| `protocol.py` | JSON-RPC encode/decode helpers and protocol metadata |
| `session.py` | `SessionState`, server-side runtime state container |
| `eventbus.py` | In-process event bus feeding ZMQ PUB/SUB events |
| `jobs.py` | Job lifecycle helpers for long-running work |
| `rpc_logging.py` | `RpcLogWriter`, ships log records to the server over JSON-RPC (`log.write`), with local logging as fallback |
| `services/` | Handler modules: datasets, fits, parameters, models, model_svc, projects, session_svc, graph, plot_svc, detector_setups, flr, code_editor, log_svc, agent |
| `transport/zmq.py` | ZMQ REP/PUB server and REQ/SUB client transport |

Services receive a `SessionState` and return `ServiceResult` dictionaries with
`{"ok": bool, ...}`. Failures should use `chisurf.server.services.service_error()`
so callers can inspect `error_code`, `jsonrpc_code`, and optional
`exception_type` fields.

## RPC Namespaces

The authoritative method registry is {src}`chisurf/server/server_methods.json`.
`meta.protocol` returns the namespace catalogue from `chisurf.server.protocol`.

| Namespace | Methods |
|-----------|---------|
| `meta` | `meta.ping`, `meta.methods`, `meta.protocol` |
| `dataset` | `dataset.list`, `dataset.get`, `dataset.curve_data`, `dataset.load`, `dataset.rename`, `dataset.group`, `dataset.ungroup`, `dataset.remove`, `dataset.clear` |
| `fit` | `fit.list`, `fit.get`, `fit.create`, `fit.add`, `fit.run`, `fit.update`, `fit.save`, `fit.curve_data`, `fit.select`, `fit.reorder`, `fit.set_dataset`, `fit.set_result_idx`, `fit.set_fit_range`, `fit.range.auto`, `fit.mask.set`, `fit.remove`, `fit.clear`, `fit.diagnostics`, `fit.posterior`, `fit.reweight_prior`, `fit.parameter_snapshot`, `fit.restore_parameters`, `fit.sample.start`, `fit.sample.cancel`, `fit.sample.status`, `fit.parameter_scan.start`, `fit.parameter_scan.cancel`, `fit.parameter_scan.result`, `fit.group.select_member`, `fit.group.add_member`, `fit.group.remove_member`, `fit.group.link_parameters_by_name` |
| `parameter` | `parameter.get`, `parameter.set_value`, `parameter.set_fixed`, `parameter.set_bounds`, `parameter.set_bounds_on`, `parameter.set_prior`, `parameter.link`, `parameter.unlink` |
| `model` | `model.finalize`, `model.set_parse_function`, `model.component.add`, `model.component.remove`, `model.state.get`, `model.state.set` |
| `project` | `project.info`, `project.save`, `project.load` |
| `session` | `session.describe`, `session.clear`, `session.snapshot`, `session.restore` |
| `graph` | `graph.build`, `graph.build_fits` |
| `plot` | `plot.fit_data` |
| `detector_setups` | `detector_setups.list`, `detector_setups.get`, `detector_setups.save`, `detector_setups.current`, `detector_setups.set_current` |
| `flr` | `flr.metadata.get`, `flr.metadata.set`, `flr.metadata.add`, `flr.metadata.delete`, `flr.analysis.update`, `flr.photon_stream.add`, `flr.photon_stream.list`, `flr.export`, `flr.probe_types`, `flr.probes` |
| `editor` | `editor.document.list`, `editor.document.get`, `editor.document.set`, `editor.document.apply_edits`, `editor.document.ruff_check`, `editor.document.ruff_fix` |
| `log` | `log.write` |

Plugins add further namespaces at runtime: `PluginRegistry.register_services()`
calls each plugin's `services` entrypoint with the dispatcher, and the methods it
registers are declared in the `rpc_methods` block of the plugin's
`manifest.json`. Those are not part of the core registry above.

Every method is registered under exactly one, namespaced name. The former flat
aliases (`list_datasets`, `get_fit_info`, `run_fit`, `save_project`, `ping`, …)
were removed; call `dataset.list`, `fit.get`, `fit.run`, `project.save` and
`meta.ping` instead. `list_methods` is the single deliberate exception, kept as
a protocol-version-independent health probe.

## DTO Policy

Service handlers return plain JSON-safe dictionaries; there is no dataclass
layer. The former `chisurf/server/dto.py` (`DatasetSummary`, `FitSummary`,
`FitDetail`, `ParameterDTO`, `SetupDTO`, `ProjectInfoDTO`, `ActionResultDTO`) was
removed because nothing constructed it — it documented shapes the handlers built
by hand. Each handler module owns the shape it returns (`services/fits.py::_fit_dto`
for fits, for example); `chisurf/server/protocol.py::METHOD_SCHEMAS` names the
expected params and result type per method, and the long-term intent is to make a
JSON Schema the single contract authority.

Payloads must not contain Qt objects or arbitrary Python domain objects. Stable IDs
should be exposed as `uid` strings where possible. GUI code should compare DTOs
by `uid`, not by Python object identity.

## Plugin System

Built-in plugins live under `chisurf/plugins/`. User plugins live under
`~/.chisurf/plugins/`.

A plugin package normally contains an `__init__.py` with a `name` variable:

```python
name = "Category:Plugin Name"
```

The category before `:` controls the plugin-menu grouping. Plugin entry code is
usually guarded by `if __name__ == "plugin":` so regular imports do not launch
widgets.

Migrated plugins should use `PluginContext` or `ChiSurfAPI` for datasets, fits,
parameters, project state, and server-owned state. They may continue to use Qt
objects locally for UI work.

## Project Persistence

Project save/load is implemented in the core project/fitting code and exposed
through `project.save`, `project.load`, and `project.info` RPC methods. Project
files bundle fit configurations, model parameters, data references, history
metadata, and plugin/action catalogue extras where supported.

## Design Constraints

| Constraint | Rationale |
|------------|-----------|
| Curve sample arrays are write-locked; edit in place only inside `with curve.unlocked(...)` | A curve is shared by a fit, a plot and any number of plugins at once, so an in-place write changes everyone else's result silently |
| `chisurf.server` must not import Qt or `chisurf.gui` | Server must run headless and in subprocesses |
| Use ZMQ plus JSON-RPC 2.0 only for server communication | Keeps one transport/protocol contract |
| Do not install transparent object proxies in normal GUI startup | The GUI still expects real Python objects in many paths |
| Use explicit DTOs and commands for server-owned state | JSON cannot preserve Python identity, `isinstance`, or deep mutation semantics |
| Prefer additive migration steps | The GUI and plugins must keep working during the hybrid period |
| Keep documentation source-aligned | Wrong docs are worse than missing docs |
