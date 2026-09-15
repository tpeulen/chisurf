---
type: Development Note
title: ChiSurf Client-Server Architecture
description: This is the current architecture reference for ChiSurf's headless server and hybrid GUI/server migration.
tags: [development, headless, gui]
audience: developer
---

# ChiSurf Client-Server Architecture

This is the current architecture reference for ChiSurf's headless server and
hybrid GUI/server migration. The implementation source of truth is
`chisurf/server/`, `chisurf/core/api/`, and `chisurf/core/actions/`.

## Goals

- Keep GUI startup stable while server-owned workflows are added incrementally.
- Use only ZMQ and JSON-RPC 2.0 for process communication.
- Keep `chisurf.server` Qt-free.
- Make server contracts explicit through namespaced RPC methods and JSON-safe DTO shapes.
- Move computation and authoritative runtime state toward the server over time.
- Preserve plugin and macro compatibility during migration.

## Current Hybrid State

- The GUI process still owns real Python objects for many workflows through `chisurf.fits` and `chisurf.imported_datasets`.
- `chisurf.server` can run as a headless JSON-RPC server with its own `SessionState`.
- `chisurf.core.api.ChiSurfAPI` provides `local`, `hybrid`, and `server` modes.
- `chisurf.core.api._client.ChisurfClient` wraps ZMQ RPC calls and installs typed methods from {src}`chisurf/server/client_methods.json`.
- The server registers methods from {src}`chisurf/server/server_methods.json`.
- Transparent proxies exist under `chisurf.core.api._proxies`, but normal GUI startup must not install them by default.

## Process Model

```text
GUI Process                                      Server Process
-----------                                      --------------
Qt widgets                                       ChiSurfServer
Plugins                                         ServiceDispatcher
Macros / console                                SessionState
ChiSurfAPI                                      Service modules
ChisurfClient  -- ZMQ REQ/REP JSON-RPC ------>  ZmqServer command socket
ZMQ subscriber <-- ZMQ PUB/SUB events --------  EventBus
```

## Key Components

| Component | Path | Responsibility |
|-----------|------|----------------|
| `ChiSurfAPI` | {src}`chisurf/core/api/__init__.py` | Stable facade for local, hybrid, and server-mode operations |
| `PluginContext` | {src}`chisurf/core/api/context.py` | Context object for migrated plugins |
| `ChisurfClient` | {src}`chisurf/core/api/_client.py` | High-level client over ZMQ JSON-RPC |
| `ChiSurfServer` | {src}`chisurf/server/app.py` | Server lifecycle and component wiring |
| `ServiceDispatcher` | {src}`chisurf/server/dispatcher.py` | RPC method lookup and service invocation |
| `SessionState` | {src}`chisurf/server/session.py` | Server-side datasets, fits, experiments, project/session snapshots |
| `ServiceResult` | {src}`chisurf/server/services/__init__.py` | Standard `{"ok": bool, ...}` service return shape |
| `service_error()` | {src}`chisurf/server/services/__init__.py` | Structured service error helper |
| Protocol metadata | {src}`chisurf/server/protocol.py` | JSON-RPC helpers, protocol version, method catalogue, schemas |

## Server Responsibilities

- Own a `SessionState` instance.
- Execute RPC service handlers without importing Qt or `chisurf.gui`.
- Return JSON-safe dictionaries.
- Publish state-change events through ZMQ PUB/SUB where handlers are wired with `event_bus`.
- Expose protocol and method metadata through `meta.protocol` and `meta.methods`.

## GUI Responsibilities

- Own Qt widgets, windows, plots, and view state.
- Keep `chisurf.cs` as the local main-window object.
- Use `ChiSurfAPI`, `PluginContext`, or `ChisurfClient` for server-facing operations.
- Avoid installing transparent Python object proxies by default.
- During migration, continue to support local objects where workflows have not yet moved to server mode.

## RPC Method Registry

The authoritative registry is {src}`chisurf/server/server_methods.json`. The client
method wrappers are generated from {src}`chisurf/server/client_methods.json`.

| Namespace | Methods |
|-----------|---------|
| `meta` | `meta.ping`, `meta.methods`, `meta.protocol` |
| `dataset` | `dataset.list`, `dataset.get`, `dataset.curve_data`, `dataset.load`, `dataset.rename`, `dataset.group`, `dataset.ungroup`, `dataset.remove`, `dataset.clear` |
| `fit` | `fit.list`, `fit.get`, `fit.create`, `fit.add`, `fit.run`, `fit.update`, `fit.save`, `fit.curve_data`, `fit.select`, `fit.reorder`, `fit.set_dataset`, `fit.set_result_idx`, `fit.set_fit_range`, `fit.range.auto`, `fit.mask.set`, `fit.remove`, `fit.clear`, `fit.diagnostics`, `fit.posterior`, `fit.reweight_prior`, `fit.parameter_snapshot`, `fit.restore_parameters`, `fit.sample.*`, `fit.parameter_scan.*`, `fit.group.*` |
| `parameter` | `parameter.get`, `parameter.set_value`, `parameter.set_fixed`, `parameter.set_bounds`, `parameter.set_bounds_on`, `parameter.set_prior`, `parameter.link`, `parameter.unlink` |
| `project` | `project.info`, `project.save`, `project.load` |
| `session` | `session.describe`, `session.clear`, `session.snapshot`, `session.restore` |
| `model` | `model.finalize`, `model.set_parse_function`, `model.component.add`, `model.component.remove`, `model.state.get`, `model.state.set` |
| `graph` | `graph.build`, `graph.build_fits` |
| `plot` | `plot.fit_data` |
| `detector_setups` | `detector_setups.list`, `detector_setups.get`, `detector_setups.save`, `detector_setups.current`, `detector_setups.set_current` |
| `flr` | `flr.metadata.*`, `flr.analysis.update`, `flr.photon_stream.*`, `flr.export`, `flr.probe_types`, `flr.probes` |
| `editor` | `editor.document.list`, `editor.document.get`, `editor.document.set`, `editor.document.apply_edits`, `editor.document.ruff_check`, `editor.document.ruff_fix` |
| `log` | `log.write` |

The flat aliases (`ping`, `list_datasets`, `get_dataset_info`, `list_fits`,
`get_fit_info`, `run_fit`, `get_parameter`, `set_parameter_value`,
`save_project`, `load_project`, …) were removed — each method answers to its
namespaced name only. `list_methods` is kept as a version-independent health
probe. `ChisurfClient` still offers the short Python spellings
(`client.list_datasets()`, `client.ping()`); they are convenience wrappers that
send the namespaced method over the wire.

## Payload Principles

- Every payload must be JSON-serializable.
- Payloads must not contain Qt objects or arbitrary Python domain objects.
- Payloads should include stable `uid` strings wherever possible.
- GUI and plugin code should compare server-owned objects by `uid`, not Python identity.
- There is no dataclass layer: handlers build the dicts directly, each handler
  module owning its own shape (`chisurf/server/services/fits.py::_fit_dto` for fits).

Example fit summary, as returned by `fit.list` (`_fit_dto`):

```json
{
  "index": 0,
  "uid": "fit-uuid",
  "name": "Fit 1",
  "type": "FitGroup",
  "chi2": 1.23,
  "chi2r": 1.05,
  "n_points": 1024,
  "n_free": 5,
  "dataset_name": "sample.ptu",
  "dataset_uid": "dataset-uuid",
  "model_name": "Lifetime",
  "parameter_count": 12,
  "data": {},
  "model": {},
  "parameters": []
}
```

## Error Model

There are two layers of errors:

- Transport/protocol failures use JSON-RPC error envelopes.
- Service-level failures usually return `{"ok": false, "error": "...", "error_code": "...", "jsonrpc_code": ...}` inside a JSON-RPC `result` for compatibility.

Client transport failures and server-side JSON-RPC errors are represented by
`chisurf.core.api._client.RemoteError`.

## Event Model

State-changing services that are registered with `event_bus` publish events on
the server event bus and ZMQ PUB socket. Event payloads should contain enough
IDs for the GUI to refresh only affected views.

Important topics include session, dataset, fit, parameter, project, and job
changes. Exact emitted topics should be checked in the service implementation
when extending a workflow.

## Why Not Transparent Proxies By Default?

Existing GUI and plugin code often relies on real Python behavior:

- object identity with `is` and `id()`
- `isinstance(...)`
- direct method calls such as `fit.run()` and `fit.update()`
- deep mutation such as `p.link = parameter`
- mutable object graphs such as `fit.model.parameters_all_dict`

JSON-backed proxies cannot preserve those semantics reliably. The migration
therefore uses explicit RPC methods, DTOs, and facade methods. Proxies may be
used only for explicit headless experiments, not normal GUI startup.

## Acceptance Criteria For Clean Architecture

The migration is complete when:

- The GUI can start without constructing authoritative datasets/fits locally.
- Fit execution, dataset loading, parameter mutation, and project load/save happen through server RPC for migrated workflows.
- Main GUI views render DTO snapshots rather than real server-owned objects.
- Plugins use `PluginContext` or `ChiSurfAPI` for server-owned state.
- `chisurf.fits` and `chisurf.imported_datasets` are no longer authoritative in the GUI process.
- `chisurf.server` imports and runs without Qt installed.
- Multiple GUI instances spawn or connect to independent server sessions without port or state collisions.
- Server integration tests cover the main workflows.
