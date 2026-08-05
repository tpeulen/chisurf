---
type: Architecture
title: API Facade (ChiSurfAPI)
description: The stable local/hybrid/server facade for GUI, macros, plugins, and the console.
resource: chisurf/core/api/
tags: [api, facade, hybrid, rpc]
timestamp: '2026-07-05T00:00:00Z'
---

# Purpose

`chisurf.core.api.ChiSurfAPI` is the stable facade through which the GUI,
macros, plugins, and the console read and mutate datasets, fits,
parameters, project, and session state. New code should go through this
facade (or [PluginContext](/architecture/plugin-system.md)) rather than the
legacy [runtime globals](/architecture/runtime-globals.md).

# Modes

| Mode | Behavior |
|------|----------|
| `local` | Read and mutate current in-process objects for legacy workflows |
| `hybrid` | Preserve local behavior while allowing migrated server paths |
| `server` | Route operations through `ChisurfClient` RPC calls |

In `server` mode calls are routed to the Qt-free
[server](/architecture/server.md) over a ZMQ/JSON-RPC transport.

# Addressing a fit or dataset

Every mode addresses an object by uid (identity) or index (position), and the
local branch obeys the same rule as the server's `services._resolve_fit`
(see [server](/architecture/server.md)): a **non-empty uid that matches nothing
is an error**, never a fall back to the index — the caller named a specific fit
or dataset, so retargeting the call at another one would mutate the wrong
object. An empty or absent uid means "unspecified" and uses the index. The
local helper is `chisurf.core.api._resolve_indexed`.

# Key symbols

| Symbol | Path | Role |
|--------|------|------|
| `ChiSurfAPI` | `chisurf.core.api` | Dataset, fit, parameter, project, session facade |
| `PluginContext` | `chisurf.core.api.context` | API/client/main-window context passed to migrated plugins |
| `ChisurfClient` | `chisurf.core.api._client` | High-level client over the ZMQ JSON-RPC transport |
| `RemoteError` | `chisurf.core.api._client` | Client-side structured RPC error exception |

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
