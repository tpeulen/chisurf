# Review and Updated PRD: chinet MMFDB Transparent Backend

Date: 2026-06-13

Status: Request changes

Scope reviewed:

- `modules/chinet/chinet/*`
- `modules/chinet/test/*`
- `chisurf/core/mmfdb/chinet_adapter.py`
- `chisurf/core/mmfdb/api.py`
- `chisurf/plugins/core/mmfdb_admin/*`
- `test/fio/test_mmfdb_chinet_adapter.py`
- `test/fio/test_mmfdb_chinet_fit_archive.py`

Out of scope for this review:

- The current working tree includes broad unrelated changes in plugins, server code,
  icons, node editor GUI, AI settings, and other areas. Those should be reviewed
  separately.

## Executive Summary

The implementation is closer than the previous review. The old C++/SWIG chinet
tree has been removed, the README now describes a Python runtime, MMFDB storage
has transaction coverage, `store_node_artifacts=False` now skips node artifacts,
and fit archiving no longer reuses live parameter ports.

It is still not ready to merge as the final "transparent MMFDB replacement" for
the old MongoDB path. The current transparent backend only works correctly for
session-level writes through one calling convention. Standalone node/port writes
return success without durable MMFDB writes, URI-style MMFDB connection support is
advertised but broken, MMFDB session restore clears the global chinet registry,
and fit archives overwrite chinet parameter metadata with fit-state metadata
while duplicating dependency edges.

## Review Findings

### P1 - Standalone node and port writes silently no-op under MMFDB

Location:

- `modules/chinet/chinet/base.py:87`
- `chisurf/core/mmfdb/chinet_adapter.py:668`

Problem:

`BaseObject.write_to_db()` delegates to the configured backend for all chinet
objects. `MMFDBChinetBackend.write_object()` only persists an object when it is a
`Session` or belongs to a registered `Session`. For standalone `Node` or `Port`
objects, it only registers the object in memory and returns `True`.

Evidence:

```text
port connect True
port write True
artifact_count 0
parameter_count 0
```

Risk:

This violates the transparent persistence contract. Callers can receive success
while MMFDB contains no session artifact, node artifact, parameter row, or link
edge. The old MongoDB path behaved like object persistence; the MMFDB replacement
must not silently drop object writes.

Required fix:

- Either reject standalone `Node`/`Port` writes with a clear `False`/exception,
  or persist them by wrapping them in a synthetic session artifact.
- The preferred behavior for compatibility is:
  - `Session.write_to_db()` persists the full graph.
  - `Node.write_to_db()` persists the owning session if one exists.
  - `Port.write_to_db()` persists the owning session if one exists.
  - Standalone `Node`/`Port` writes create a small synthetic session only when
    explicitly enabled, for example `allow_synthetic_session=True`.
- Add tests for standalone `Port` and `Node` writes so a success return always
  corresponds to durable MMFDB rows.

### P1 - `uri_string="mmfdb://..."` connection path is broken

Location:

- `modules/chinet/chinet/base.py:7`
- `modules/chinet/chinet/base.py:25`
- `modules/chinet/chinet/base.py:46`

Problem:

`_is_mmfdb_request()` treats `uri_string` values starting with `mmfdb:` or
`mmfdb://` as requests for the MMFDB backend. `_configure_backend_from_request()`
then forwards the original `kwargs` to `configure_mmfdb_backend(**kwargs)`, but
`configure_mmfdb_backend()` does not accept `uri_string`.

Evidence:

```text
TypeError configure_mmfdb_backend() got an unexpected keyword argument 'uri_string'
```

Risk:

The compatibility-style connection surface looks supported but fails at runtime.
This is especially important because the old MongoDB API commonly used
`uri_string`, and the new backend is supposed to be a transparent replacement.

Required fix:

- Parse `uri_string` into `db_path`.
- Accept at least:
  - `connect_to_db("mmfdb", db_path="...")`
  - `connect_to_db(backend="mmfdb", db_path="...")`
  - `connect_to_db(uri_string="mmfdb:///absolute/path.sqlite")`
  - `connect_to_db(uri_string="mmfdb://relative/path.sqlite")`
- Unknown legacy MongoDB kwargs may be ignored only after emitting a clear
  compatibility warning or documenting the behavior.
- Add tests for all supported connection forms.

### P1 - Restoring one MMFDB session clears unrelated in-memory chinet objects

Location:

- `modules/chinet/chinet/schema.py:223`
- `modules/chinet/chinet/schema.py:247`
- `chisurf/core/mmfdb/chinet_adapter.py:650`

Problem:

`session_from_schema()` calls `DB.clear()` before reconstructing the session.
Transparent MMFDB reads call `load_chinet_session()`, which calls
`session_from_schema()`. That means restoring one MMFDB session clears every
other object and session in the process-local chinet registry.

Evidence:

```text
before_has_s2 True
loaded True
after_has_s2 False
```

Risk:

This is unsafe for transparent backend behavior. A user restoring one fit or
analysis graph can silently remove unrelated live sessions from the in-memory
registry. It also makes multi-fit workflows brittle.

Required fix:

- Add a non-destructive schema restore mode:
  - `session_from_schema(payload, clear_registry: bool = False)` or equivalent.
  - JSONL legacy load may still clear if required for backward compatibility.
- `MMFDBChinetBackend.read_object()` must use the non-destructive mode.
- Add a regression test with two live sessions where restoring one does not
  delete the other from `chinet.DB`.

### P1 - Fit archive overwrites chinet parameter metadata and duplicates link edges

Location:

- `chisurf/core/mmfdb/chinet_adapter.py:905`
- `chisurf/core/mmfdb/chinet_adapter.py:1113`
- `chisurf/core/mmfdb/chinet_adapter.py:1181`
- `chisurf/core/mmfdb/chinet_adapter.py:1254`

Problem:

For fit archives, `_session_from_fit_state_payload()` creates chinet ports with
the fit parameter UID as the port OID. `store_chinet_session()` then writes
`mmfdb_parameter` rows with chinet metadata. `_store_fit_state_parameters()` writes
the same `parameter_uuid` again, so `record_parameter()` updates the row and
replaces the metadata with `chisurf.fit_state.v1`. Link edges are written once
from the chinet session and again from the fit state.

Evidence:

```text
row_count 2 result_parameter_count 2 fit_parameter_count 2
<uuid> p0 chisurf.fit_state.v1 None <uuid>
<uuid> p1 chisurf.fit_state.v1 None <uuid>
edge_count 2
```

`chinet_port_id` is `None` in the final parameter metadata, and the linked
parameter relation appears twice.

Risk:

MMFDB loses the queryable bridge from parameter rows back to chinet ports in fit
archives, despite the requirement that nodes, links, and parameters be stored in
MMFDB. Duplicate dependency edges can also distort graph traversal and provenance
views.

Required fix:

- Use one canonical `mmfdb_parameter` row per logical fit/chinet parameter.
- Preserve both metadata namespaces in the same row, for example:
  - `metadata.schema_name = "chisurf.fit_parameter.v1"`
  - `metadata.chinet = {... chinet_port_id, chinet_node_id, chinet_session_id ...}`
  - `metadata.fit_state = {... fit_parameter_uid, model path, link target ...}`
- Write each dependency edge once.
- Add tests asserting:
  - no duplicate `parameter_depends_on` edges for one fit link.
  - each archived fit parameter retains `metadata.chinet.chinet_port_id`.

### P2 - Public compatibility contract is unresolved after removing Mongo aliases

Location:

- `modules/chinet/chinet/__init__.py:22`
- `modules/chinet/test/test_mongo_object.py` deleted

Problem:

The old public names `MongoObject`, `DatabaseObject`, and `MemoryObject` are no
longer exported, and the old Mongo object tests were deleted. This may be fine
as an intentional cleanup, but it is not recorded as a compatibility decision.

Risk:

Existing ChiSurf plugins or notebooks may still import these names. Removing
them in the same change as the MMFDB migration makes it hard to tell whether a
future breakage is intentional cleanup or accidental API loss.

Required fix:

- Decide explicitly:
  - If the names are intentionally removed, add a migration note and a test that
    the new supported API is documented.
  - If compatibility is required, keep aliases to `BaseObject` with deprecation
    warnings and tests.

### P2 - MMFDB backend is process-global and lacks scoped lifecycle controls

Location:

- `modules/chinet/chinet/db.py:11`
- `modules/chinet/chinet/db.py:35`
- `chisurf/core/mmfdb/chinet_adapter.py:689`
- `chisurf/core/mmfdb/chinet_adapter.py:738`

Problem:

The transparent backend is stored as one global `chinet.DB._backend`. This can
work for simple workflows, but it is easy to leak the backend across tests,
independent fits, or unrelated sessions.

Risk:

One workflow can accidentally write another workflow's session into the wrong
operation or database. The tests use `clear_mmfdb_backend(close=True)` manually,
but production code needs an ergonomic safe path.

Required fix:

- Add a context manager, for example:

```python
with mmfdb_chinet_backend(db_path, operation_id=..., store_node_artifacts=False):
    session.write_to_db()
```

- The context manager must restore the previous backend on exit, even on error.
- Add nested-backend and exception-path tests.

## Positive Changes

- C++/SWIG chinet code and old build files are removed from the working tree.
- `modules/chinet/README.md` now documents the Python runtime and MMFDB storage.
- `store_node_artifacts=False` is now implemented and tested.
- MMFDB writes are wrapped in transaction contexts and rollback tests exist.
- Fit archive now builds chinet archive sessions from fit-state payloads instead
  of reparenting live parameter ports.
- Focused tests pass for the currently covered paths.

## Verification Performed

Focused test run:

```text
python -m pytest modules/chinet/test test/fio/test_mmfdb_chinet_adapter.py test/fio/test_mmfdb_chinet_fit_archive.py
34 passed, 4 warnings in 59.06s
```

Additional manual probes:

- `store_node_artifacts=False` path is covered by tests and now works.
- Standalone `Port.write_to_db()` under MMFDB returns `True` but writes zero rows.
- `connect_to_db(uri_string="mmfdb://...")` raises `TypeError`.
- `session_from_schema()` clears unrelated registered sessions.
- Fit archive overwrites chinet parameter metadata and writes duplicate
  dependency edges for one fit-state link.

## Updated PRD

### Product Goal

Replace the old C++/MongoDB-backed chinet persistence story with a pure-Python
chinet runtime that can persist sessions, nodes, links, and parameters into MMFDB
through both explicit archive APIs and transparent chinet object APIs.

The default user experience should remain simple:

```python
session.connect_to_db("mmfdb", db_path="analysis.sqlite", operation_id="fit-001")
session.write_to_db()
restored = chinet.Session()
restored.connect_to_db("mmfdb", db_path="analysis.sqlite")
restored.read_from_db(session.oid)
```

The fast path should be the default for transparent persistence:

- one embedded `chinet_session` artifact containing the full canonical graph.
- queryable `mmfdb_parameter` rows for scalar fit/analysis parameters.
- queryable `parameter_depends_on` edges for links.
- no per-node artifacts unless `store_node_artifacts=True`.

### Users

- ChiSurf users fitting fluorescence data.
- Developers building model/fit workflows on chinet parameters.
- MMFDB plugin users browsing provenance, fits, parameters, and dependency
  graphs.
- Future agents maintaining chinet after C++ removal.

### Non-Goals

- Reintroducing C++, SWIG, RTTR, or MongoDB.
- Adding a new database dependency.
- Rebuilding the chinet computation engine.
- Storing high-volume raw photon/curve data inside `mmfdb_parameter`.

### Functional Requirements

#### FR1: Pure Python chinet package

- The package ships only Python chinet runtime code.
- No C++/SWIG/CMake build path remains active.
- README and packaging describe Python installation and runtime behavior only.
- If old public compatibility aliases are kept, they are Python aliases with
  deprecation warnings, not C++ wrappers.

Acceptance criteria:

- `find modules/chinet -name '*.cpp' -o -name '*.h' -o -name '*.i'` returns no
  active source files.
- `python -m pytest modules/chinet/test` passes.
- README does not instruct users to build C++ chinet.

#### FR2: Canonical chinet session schema

- `chinet.session.v1` stores:
  - session id.
  - nodes.
  - ports.
  - port values, bounds, fixed flags, reactive flags, directions.
  - links as `parameter_depends_on`.
  - fit references.
  - non-executable callback metadata.
- The schema round-trips scalar and vector ports.
- Restore must support non-destructive mode for MMFDB reads.

Acceptance criteria:

- Schema round-trip tests preserve ids, values, bounds, directions, and links.
- Loading one session from MMFDB does not clear unrelated registered sessions.

#### FR3: Explicit MMFDB session storage

- `store_chinet_session()` writes:
  - one `chinet_session` artifact.
  - optional `chinet_node` artifacts.
  - `mmfdb_parameter` rows for queryable parameters.
  - `parameter_depends_on` edges for port links.
  - operation and operation-artifact rows.
- `load_chinet_session()` reconstructs a session from the session artifact.
- All writes for one session are atomic.

Acceptance criteria:

- Failure during operation, artifact, parameter, or edge write leaves no partial
  rows for that operation.
- `store_node_artifacts=False` writes zero `chinet_node` artifacts.
- `store_node_artifacts=True` writes one node artifact per session node.

#### FR4: Transparent MMFDB backend

- `connect_to_db()` supports MMFDB without requiring callers to use MMFDB adapter
  functions directly.
- Supported connection forms:
  - `session.connect_to_db("mmfdb", db_path=...)`
  - `session.connect_to_db(backend="mmfdb", db_path=...)`
  - `session.connect_to_db(uri_string="mmfdb:///absolute/path.sqlite")`
  - `session.connect_to_db(uri_string="mmfdb://relative/path.sqlite")`
- `Session.write_to_db()` persists the full session graph.
- `Node.write_to_db()` and `Port.write_to_db()` persist their owning session
  when ownership exists.
- Standalone `Node` and `Port` writes must not silently no-op.

Acceptance criteria:

- Every successful transparent `write_to_db()` creates durable MMFDB rows.
- Every unsupported transparent write returns `False` or raises a documented
  exception.
- Tests cover session, node, port, URI, and backend keyword connection paths.

#### FR5: Fast transparent storage mode

- `store_node_artifacts=False` is the default recommended mode for repeated fit
  persistence.
- Fast mode stores the full graph once in the session artifact and uses indexed
  rows only for query/filter/traversal needs.
- Optional node artifacts are used only for debugging or rich provenance browse
  modes.

Acceptance criteria:

- Fast mode writes one session artifact, zero node artifacts, expected parameter
  rows, and expected dependency edges.
- Fast mode remains correct for at least 100 nodes and 1000 ports in a benchmark
  smoke test.
- Repeated writes to the same operation/session are idempotent or documented as
  versioned snapshots.

#### FR6: Fit archive integration

- `archive_fit_to_mmfdb()` stores:
  - fit-state artifact.
  - chinet session artifact.
  - input dataset artifacts/links.
  - one canonical parameter row per logical fit parameter.
  - one dependency edge per parameter link.
- It must not mutate live fit parameter ports or node ownership.
- It must preserve both chinet and fit-state metadata for queryable parameters.

Acceptance criteria:

- Live port owners are unchanged after archive.
- Each fit parameter row contains both fit-state uid and chinet port id.
- One logical link yields one `parameter_depends_on` edge.
- A failure while writing fit-state rows rolls back the whole archive operation.

#### FR7: MMFDB plugin and API access

- MMFDB plugin exposes versioned methods for saving, listing, getting, and
  restoring chinet sessions.
- API payloads use the canonical `chinet.session.v1` schema.
- Plugin and backend method manifests remain in sync.

Acceptance criteria:

- Manifest validator reports no missing `mmfdb.v1.chinet.sessions.*` methods.
- `save/get/list/restore` tests cover the service dispatcher path.

### Data Model

Required MMFDB records:

- `mmfdb_artifact`
  - `artifact_kind = chinet_session`
  - optional `artifact_kind = chinet_node`
  - `artifact_kind = fit_result`
- `mmfdb_operation`
  - one operation per archive/save action.
- `mmfdb_operation_artifact`
  - input data links.
  - output session links.
  - output fit-state links.
- `mmfdb_parameter`
  - one row per queryable scalar model/fit parameter.
  - metadata preserves both chinet and fit-state provenance where available.
- `mmfdb_edge`
  - non-operation relationships only.
  - `parameter_depends_on` for parameter links.

Parameter metadata target:

```json
{
  "schema_name": "chisurf.fit_parameter.v1",
  "chinet": {
    "schema_name": "chinet.parameter_ref.v1",
    "chinet_session_id": "...",
    "chinet_node_id": "...",
    "chinet_port_id": "...",
    "port_name": "...",
    "port_direction": "input"
  },
  "fit_state": {
    "schema_name": "chisurf.fit_state.v1",
    "fit_parameter_uid": "...",
    "link_target": "..."
  }
}
```

### Test Plan

Required tests before merge:

- `modules/chinet/test/test_session_schema.py`
  - destructive and non-destructive restore modes.
  - scalar/vector round trips.
- `test/fio/test_mmfdb_chinet_adapter.py`
  - explicit session save/load.
  - fast mode skips node artifacts.
  - transaction rollback on operation/artifact/parameter/edge failure.
  - transparent session write/read.
  - transparent node/port owned-session writes.
  - standalone node/port unsupported behavior.
  - all connection forms, including `uri_string`.
  - backend context manager cleanup and nested restore.
- `test/fio/test_mmfdb_chinet_fit_archive.py`
  - no live port mutation.
  - one parameter row per logical fit parameter.
  - both chinet and fit metadata retained.
  - one edge per logical link.
  - rollback after fit-state failure.
- Plugin tests:
  - service dispatcher save/get/list/restore.
  - manifest and service registry consistency.

### Implementation Notes

- Keep MMFDB backend integration in `chisurf.core.mmfdb.chinet_adapter`; do not
  make `modules/chinet` import MMFDB except inside lazy connection paths.
- Avoid global backend leaks by adding a scoped backend context manager.
- Do not hide write failures behind `True`.
- Treat `mmfdb_parameter.value` as scalar. Store vector values in the session
  artifact and optional metadata, not as lossy scalar rows unless explicitly
  documented.
- Do not store `input_to` or `produced` in `mmfdb_edge`; keep operation input and
  output relationships in `mmfdb_operation_artifact`.

### Merge Gate

The coder is done only when:

- All P1 findings above are fixed.
- Focused chinet/MMFDB tests pass.
- New regression tests cover the fixed paths.
- The public compatibility decision for old Mongo-style names is documented.
- The final implementation can be explained as:
  "MMFDB transparently persists chinet sessions quickly by default, with optional
  rich node artifacts, and every success return corresponds to durable MMFDB
  state."
