---
type: Architecture
title: Headless Server
description: The Qt-free ZMQ/JSON-RPC 2.0 server under chisurf/server/.
resource: chisurf/server/
tags: [server, zmq, jsonrpc, headless]
timestamp: '2026-07-05T00:00:00Z'
---

# Purpose

ChiSurf includes a headless server based on ZMQ and JSON-RPC 2.0. It is
Qt-free and lives under `chisurf/server/`. In `server` mode the
[API facade](/architecture/api-facade.md) routes calls to it through
`ChisurfClient`.

# Layout

| Path | Role |
|------|------|
| `app.py` | `ChiSurfServer`, server wiring and lifecycle |
| `__main__.py` | `python -m chisurf.server` entry point |
| `startup.py` | Subprocess startup/termination helpers |
| `dispatcher.py` | `ServiceDispatcher`, method registration and invocation |
| `server_methods.json` | Declarative server RPC registry |

Run it headlessly with `python -m chisurf.server`.

# Addressing a fit

Service calls address a fit by `fit_uid` (identity) or `fit_index` (position),
resolved by the single `services._resolve_fit` helper.

`state.fits` holds **fit groups**, and a group's member fits carry their own
distinct uids — the GUI addresses the member it is showing, not the group. A
uid is therefore matched against the top-level fits *and* group members; a
member resolves to the member itself, paired with the index of its group.

A **non-empty `fit_uid` that matches nothing is an error**, never a fall back to
`fit_index` — the caller named a specific fit, so retargeting the operation at
another one would apply it to the wrong fit. An empty or absent uid means
"unspecified" and uses the index. Clients must therefore omit a uid they cannot
determine rather than sending `""`.

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
