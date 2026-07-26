---
type: Architecture
title: Action Layer
description: ActionRegistry/ActionDispatcher mediating all state-change actions.
resource: chisurf/core/actions/
tags: [actions, state, dispatcher]
timestamp: '2026-07-05T00:00:00Z'
---

# Purpose

State changes are mediated by the action layer under `chisurf/core/actions/`.
It is exposed lazily via `chisurf.__getattr__` as `chisurf.action_dispatcher`,
`chisurf.action_registry`, `chisurf.action_catalog`, and
`chisurf.action_execute`. Action names may be canonical internal names or
dotted aliases, depending on the registered `ActionSpec`.

There is exactly **one** dispatcher per process, and
`chisurf.action_registry is chisurf.action_dispatcher.registry` always holds.
Resolving either attribute imports `chisurf.core.actions`, whose `@action`
decorators read `chisurf.action_registry` and so re-enter `chisurf.__getattr__`;
the lazy branches therefore hand back the already-cached instance instead of
building a second dispatcher whose registry would be empty.

# Layout

| File | Role |
|------|------|
| `_infra.py` | `ActionSpec`, `ActionRegistry`, `ActionDispatcher`, default dispatcher helpers |
| `_decorator.py` | Action registration decorator support |
| `dataset_actions.py` | Dataset state-change actions |
| `fit_actions.py` | Fit state-change actions |
| `model_actions.py` | Model actions |
| `parameter_actions.py` | Parameter actions |
| `project_actions.py` | Project actions |

The [API facade](/architecture/api-facade.md) and the
[server](/architecture/server.md) both route mutations through this layer.

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
