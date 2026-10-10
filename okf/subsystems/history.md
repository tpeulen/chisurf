---
type: Subsystem
title: Operation History
description: Append-only recording of user/scripted actions with headless replay, projected durably into the MMFDB provenance store.
resource: chisurf/history/
tags: [history, core, provenance]
timestamp: '2026-07-05T00:00:00Z'
---

# Scope

`chisurf/history/` records every traceable state change as an ordered event log
and can reconstruct the scientific state at any cursor position (undo/replay),
independently of Qt.

| Module | Role |
| --- | --- |
| `core.py` | `OperationHistory` — append-only log, subscribers, checkpoints |
| `projection.py` | `DomainState`, `build_target_state` — pure replay projection |
| `replay.py` | `reconstruct_*_state` / `capture_domain_snapshot` deltas |

The package name doubles as the process-wide singleton `cs.history` (a shim in
`__init__.py` reconciles the collision).

# Recording

State changes call `record_action(...)`
(`chisurf/core/actions/_infra.py`), which forwards to `cs.history.record(...)`.
So macros, the [action layer](/architecture/action-layer.md), and GUI clicks all
produce identical events `{action_type, summary, payload, source_uid,
target_uid}`. `suppress_recording()` guards re-entrant replay; the log
auto-compacts past ~5000 events.

# Replay / projection

- Periodic **checkpoints** (`DEFAULT_CHECKPOINT_INTERVAL = 50`, capped at 20
  in-memory snapshots) are full-domain deep copies; evicted ones are rebuildable
  from the log.
- `build_target_state(checkpoint, events_to_replay)` seeds from the nearest
  snapshot and merges deltas from `replay.py`
  (`reconstruct_navigation_state`, `reconstruct_parameter_state`,
  `reconstruct_fit_range_state`, `reconstruct_setup_state`,
  `reconstruct_model_state`) into a plain-dict `DomainState`.
- Projection is deliberately **GUI-free** so it is headless-testable and reusable
  server-side; applying the state to live widgets is the GUI adapter's job
  (`chisurf/gui/main_helper.py`).

# Audit contracts

`test/history/test_action_history_audit.py` pins three rules:

- **Catalogue consistency** — a `side_effect_class == "state"` action is replayable; a
  non-replayable one is `execution` or `diagnostic`. (`fit.mask_set` was state but
  non-replayable; it is replayable now.)
- **Recorded names resolve** — every action-type literal reaching `record_action` at the
  direct call sites (including through a same-module wrapper such as `_record_history`)
  names a registered action via `cs.action_registry.resolve_name`. This registered
  `fit.group_auto_link` and `parameter.prior.set` (both added to the MMFDB
  `_mmfdb_event_log.action_type` enumeration) and moved the agent's `set_parameter` from
  the unregistered `agent.parameter.set` to `parameter.bounds.set` / `parameter.value` /
  `parameter.fixed` rows.
- **Navigable cursor** — with science bound, after `apply_edit` and an audit
  `record("fit.run.finish")` the cursor `can_navigate`. Assert `can_navigate`, not
  `len(events)`: an unchanged-science `record` at a historical cursor *inserts* a row.

`test/project/test_e2e_undo_redo_save_reload.py` runs add fit → edit → fit → undo → redo
→ `storage.save_file` → `load_file` on the real owner and requires equal
`snapshot_fingerprint`.

# Where to pick this up

1. Measure: `pixi run -e test python -m pytest test/history/test_action_history_audit.py
   test/history/test_vocabulary.py -q -p no:cacheprovider` (8 passed 2026-10-10). The
   vocabulary test needs the MMFDB dictionary rows for any new `@action`.
2. Open: the audit reads only the eight `RECORD_SITES` modules; a new direct
   `record_action` caller elsewhere is not audited until it is added there.
3. Open: `record_action` writes the action type verbatim (`fit_mask_set`,
   `parameter_prior_set`); it resolves, but the stored row is not the dotted canonical
   name. Normalising at `record_action` would change persisted rows — decide with the
   history browser/MMFDB projection owners.

# Durable projection into MMFDB ([PRD-43](/prds/prd-43.md))

The in-memory list is authoritative for the live session; each event is also
**best-effort** persisted to the [MMFDB](/architecture/mmfdb.md) durable event log:

- `OperationHistory._persist_event` → `chisurf.core.mmfdb.event_log.append_event`
  (into `mmfdb_event_log`). This is a no-op without a database, so history works
  identically offline (local mode).
- `list_events(source="mmfdb")` reads the durable log back; `source="memory"`
  (default) returns the live view. `action_type` values use the dotted MMFDB
  vocabulary, normalized in `replay.py`.

Per [PRD-43](/prds/prd-43.md) the GUI history browser is a **projection over
MMFDB** rather than a parallel store, aligning session history with the
provenance DAG.

See also: [overview](/overview.md), [Core](/subsystems/core.md),
[macros & CLI](/subsystems/macros-cli.md), [server](/architecture/server.md).
