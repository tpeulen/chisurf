# ChiSurf Client-Server Next Steps

This is the short handoff for future work. For architecture details, read:

1. [`architecture_client_server.md`](architecture_client_server.md)
2. [`client_server_migration_plan.md`](client_server_migration_plan.md)
3. `CLEANUP.md`

## Current State

- Transport is ZMQ REQ/REP for commands plus ZMQ PUB/SUB for events.
- Wire protocol is JSON-RPC 2.0.
- `chisurf.server.protocol.PROTOCOL_VERSION` is `"1.0"`.
- `meta.ping`, `meta.methods`, and `meta.protocol` are implemented.
- `ChisurfClient` lives in `chisurf.core.api._client`.
- `ChiSurfAPI` and `PluginContext` live in `chisurf.core.api`.
- RPC server methods are registered from {src}`chisurf/server/server_methods.json`.
- Client wrapper methods are generated from {src}`chisurf/server/client_methods.json`.
- GUI/local-object compatibility remains for many workflows.
- Transparent proxies are not part of the normal GUI startup path.
- Service failures use structured metadata through `service_error()` where migrated.

## Hard Constraints

- Keep `chisurf.server` Qt-free.
- Use only ZMQ and JSON-RPC for process communication.
- Do not reintroduce FastMCP, HTTP, SSE, or alternate server protocols.
- Do not install transparent Python object proxies in normal GUI startup.
- Prefer additive RPC/client/facade APIs before removing old local paths.
- Keep tests passing after every change.
- Update docs when source behavior changes.

## Immediate TODOs

### 1. Continue `meta.protocol` Schemas

`METHOD_CATALOGUE` is generated from `server_methods.json`, so every registered
method is already discoverable and its event topics are taken from the registry.
What still has to be written by hand is the parameter/result half:
`METHOD_PARAM_SCHEMAS` should continue to grow until each public namespaced
method declares its required and optional parameters and its result type
(50 of 93 methods so far).

Priority namespaces:

1. `parameter.*`
2. `project.*`
3. `session.*`
4. `model.*`
5. `graph.*`

Verification:

```bash
python -m pytest test/server/test_protocol.py test/server/test_integration.py::TestMetaProtocol --tb=line -q --no-cov
```

### 2. Continue Facade Migration

Goal: reduce direct mutation of `chisurf.fits` and `chisurf.imported_datasets`.

Pattern:

1. Pick one workflow.
2. Ensure the server endpoint exists.
3. Ensure the `ChisurfClient` method exists.
4. Ensure the `ChiSurfAPI` method exists.
5. Route server mode through the facade.
6. Preserve local/hybrid behavior until dependent GUI paths are migrated.
7. Add tests.

Do not migrate multiple unrelated widgets/plugins in one change.

### 3. Add GUI Startup Smoke Coverage If Feasible

Potential tests:

- Start `python -m chisurf.server`, ping `meta.ping`, then terminate.
- Assert proxy installation is disabled or absent by default.
- Keep full Qt GUI imports out of unit tests unless the environment supports them.

Verification:

```bash
python -m pytest test/server/ --tb=line -q --no-cov
python -c "import chisurf.server; print('server import OK')"
python -c "import chisurf.gui; print('gui import OK')"
```

## Stop Conditions

Stop and ask before continuing if:

- A change requires Qt imports in `chisurf.server`.
- A change would install proxies during default GUI startup.
- A migration would rewrite multiple unrelated widgets/plugins at once.
- A change removes a legacy RPC alias without proving all callers are migrated.
- Tests fail for reasons unrelated to the current change.
