---
type: Architecture
title: Headless Server
description: The Qt-free ZMQ/JSON-RPC 2.0 server under chisurf/server/.
resource: chisurf/server/
tags: [server, zmq, jsonrpc, headless]
timestamp: '2026-07-05T00:00:00Z'
---

# Where to pick this up

*Left 2026-08-05, after `abe89a55d`.* The server can now build and run fits; the
work that remains is making `test/server` trustworthy.

1. **Fix the test isolation before chasing any assertion.**
   `test/server/test_integration_lifecycle.py` shares one module-scoped server
   and client (`_client()`) and resets only datasets and fits between tests
   (`reset_state` → `fit__clear` / `dataset__clear`). Everything else a test
   leaves behind is inherited. The measurement that proves it:
   `TestErrorBoundary` passes **12/12 run alone** and fails **3** in the full
   file; `TestProxyRpcErrorHandling` passes 6/6 alone and fails 6 in it. So a
   per-test failure here may be the previous test's residue, and **a fix
   verified on one class is not verified**. This blocks the other items: until
   it is fixed, nobody can tell a real defect from a leak.
2. **Port the rest of the file to the raising error contract.** A failing call
   raises `RemoteError` — service errors travel in the JSON-RPC `error` member
   (SV-04) — while these tests still assert `not result.get("ok")`. That never
   described the contract: it also passes on *success*, because a result payload
   has no `"ok"` key either. Three classes are already ported and pass in
   isolation (`TestErrorBoundary`, `TestProxyRpcErrorHandling`,
   `TestChisurfRunPattern`); use `pytest.raises(RemoteError)`, and where a test
   only means "the server must survive this", assert that with a following
   `meta__ping`. State: **43 failed / 31 passed**, from 51/23.
3. **Audit the remaining service signatures against the dispatcher.** Two were
   found by accident — `fit_set_dataset` did not accept `fit_uid` while the
   dispatcher passes it, and `fit_set_result_idx` made `fit_index` a required
   positional — so *addressing a fit by uid*, the documented way, raised
   `TypeError` inside the dispatcher. Both are one-line signature mismatches
   that no test covered; there is no reason to think they are the only two. A
   contract test over `server_methods.json` versus the service signatures would
   retire the whole class.

**Traps in measuring any of this.** The whole file takes **13.5 minutes** — run
one class at a time while working. A collection error under `pytest -q --tb=no`
is reported only as `1 error during collection`, with no cause. And a process
blocked in `zmq_ctx_destroy` looks exactly like a hung suite: it was real while
fits could not be created, but the file now runs to completion, and its
slowness is repeated client timeouts rather than a deadlock. Check CPU time
before concluding "hang".

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
