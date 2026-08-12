---
type: PRD
prd: "28"
title: "PRD-28: Companion-Tool ↔ MMFDB Burst-Selection Round Trip"
description: Opens registered burst selections from MMFDB in the companion exploration tool; direct send-current-result from Burst Selection remains open.
status: done
phase: "2"
resource: chisurf/plugins/ndxplorer/
tags: [prd, fret, mmfdb]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
Closes the loop so a burst selection can move between the Burst Selection tool, MMFDB, and the companion photon-data exploration tool via the existing sample/measurement picker, giving a hands-on test of the Phase-2 operation/transformer spine. The implemented direction opens a registered burst selection from MMFDB into the exploration tool; the reverse "send the just-produced selection" workflow remains unfinished. Because burst files reference photons by index in the original TTTR file, the selection is registered as an on-disk directory reference (not copied into the object store), and multi-file runs appear as a single group. GUI actions only orchestrate pick → resolve path → hand off; the external exploration module stays free of ChiSurf imports.

# Status
Done (2026-08-08). Both directions are wired: direction A (open-from-MMFDB via
the picker) and direction B (send the current burst result to ndX via a toolbar
action that calls `send_path_to_ndxplorer` with the just-produced output path).
The launcher module stays thin — no analysis logic in the GUI actions, and
`modules/ndxplorer` remains chisurf-free. Path-resolution tests pass against the
real in-process client, and the CLI round trip is verified end-to-end.

# Goal
Close the loop so a **burst selection** can move between the Burst Selection tool, MMFDB, and the **companion exploration tool** (`modules/ndxplorer`) through the existing sample/measurement selection widget — giving a hands-on end-to-end test of the Phase-2 operation/transformer spine:

```
raw measurement ──Burst Selection──▶ burst_table (registered in MMFDB, operation
                                     microtime/burst params) ──┐
                                                               ▼
                              MmfdbDatasetPickerDialog (sample/measurement select)
                                                               │
                                                               ▼
                                                 companion exploration tool (visualize)
```

Two directions:
1. **Burst Selection → exploration tool:** a "Send to exploration tool" action that opens the just-produced burst selection.
2. **Exploration tool ← MMFDB:** an "Open burst selection from MMFDB" action that lets the user pick a registered burst selection via the sample/measurement selection widget and loads it.

# Why
Phase 2 made Burst Selection register its results as a conformant transformer (`operation_type="burst_selection"`, typed `.dic` parameters, validated). There is no GUI path yet to *open* a registered burst selection back into an analysis tool, so the round trip can't be exercised by hand. The companion exploration tool is chisurf's burst/MFD explorer and already ingests burst data; wiring it to the MMFDB dataset picker makes the whole pipeline manually testable.

# Existing pieces to reuse (do not reinvent)
- **Selection widget:** `chisurf/gui/widgets/mmfdb/dataset_browser.py` → `MmfdbDatasetPickerDialog.pick_dataset(kinds=[...], formats=[...])` ([PRD-10](prd-10.md)). The Microtime Shifter already uses it (`tttr_microtime_shifter/gui/tool.py:325`). This *is* the "sample measurement selection widget" — filter it to burst kinds.
- **Open/resolve path:** the `datasets.open` RPC / dataset-open handler returns a local readable path for an artifact (`MmfdbDatasetPickerDialog` returns the selected artifact; `mmfdb.datasets.open` resolves its object to a path).
- **Burst registration:** `burst_selection/api/mmfdb.py` already registers a `burst_table` artifact (`kind="burst_table"`, `operation_type="burst_selection"`).
- **Exploration-tool ingest:** `NDXplorer.open_files(file_type="burst_dir", file_handles=<path>, append=False)` and `ndxplorer.__main__.open_path_like_drop(ndx, path)` (`modules/ndxplorer`).

# Constraints (learned from manual testing)
- **`.bur` files reference photons by index in the original TTTR file.** A burst selection (start/stop indices) is only meaningful next to its co-located TTTR file. So the burst output is registered as an **on-disk reference** (a directory `external_reference` with its path in metadata, no object-store copy) — copying `.bur` into the object store would break the linkage. `open_dataset` materializes such references from their metadata path; the exploration tool opens the folder as a `burst_dir`, with indices resolving against the adjacent TTTR files.
- **Multi-file runs must appear as one group.** When Burst Selection processes several TTTR files, the selector must list the run as a **single** entry, not one per file/artifact. Two viable shapes:
  1. **Single output folder per run** (current launcher approach): the burst run writes one output directory; the launcher filters the picker to `external_reference` + `directory`, so one directory = one run = one group. Works when the pipeline produces a single run-level folder.
  2. **MMFDB group** (more robust): register all of a run's artifacts into an `mmfdb_group` (the tables exist) and let the picker show/select groups. Needed if a multi-file run produces *per-file* folders rather than one run folder.
  Confirm which shape the burst pipeline produces and finish accordingly.

# Design

## A. Exploration tool ← MMFDB (open a registered burst selection)
Add an **"Open from MMFDB…"** entry point that:
1. Opens `MmfdbDatasetPickerDialog.pick_dataset(kinds=["burst_table"], parent=…)` (optionally also `processed_data` with a burst format) — the sample/measurement selection widget, scoped by the canonical user ([PRD-17](prd-17.md)) so "Mine"/"All" work.
2. Resolves the chosen artifact to a local path via the dataset-open path (the object store file, or the burst directory the burst table references).
3. Launches/*reuses* an `NDXplorer` instance and calls `open_files(file_type="burst_dir", file_handles=path)` (or `open_path_like_drop`).

Placement: a small chisurf-side launcher (so MMFDB/Qt-picker code stays out of the external `ndxplorer` module) — e.g. in the `chisurf/plugins/ndxplorer` wrapper: a menu action "Open burst selection from MMFDB". Keep `modules/ndxplorer` dependency-free of chisurf.

## B. Burst Selection → exploration tool (send the current result)
Add a **"Send to exploration tool"** action to the Burst Selection tool that, after a run, takes the produced burst selection's path (the `.bur`/burst directory it just wrote, or the registered `burst_table` artifact resolved to a path) and opens it via the same `open_files`/`open_path_like_drop` call.

## C. Thin, contract-respecting wiring
- GUI actions only orchestrate: pick → resolve path → hand off. No analysis logic in the widgets ([PRD-23](prd-23.md)).
- The selection widget and `datasets.open` are reused as-is; the only new code is the two launcher actions + path resolution.

# Tasks
1. Path resolution helper: given a selected MMFDB `burst_table` artifact, return the local burst-data path the exploration tool can open (object-store file or referenced burst dir). Reuse the dataset-open handler.
2. Launcher action "Open burst selection from MMFDB" (picker → resolve → `NDXplorer.open_files`). Reuse/instantiate `NDXplorer`; do not modify `modules/ndxplorer`.
3. Burst Selection "Send to exploration tool" action (resolve current result path → open).
4. Construction smoke tests for both actions; a path-resolution unit test. Manual acceptance: process a measurement → it registers → pick it in the widget → it opens.

# Definition of Done
- [x] From the exploration tool, a user can pick a registered burst selection via the sample/measurement selection widget and open it.
- [x] From Burst Selection, a user can send the current result to the exploration tool.
- [x] No analysis logic in the GUI actions; `modules/ndxplorer` stays chisurf-free; the picker + `datasets.open` are reused, not reimplemented.
- [x] Smoke + path-resolution tests pass; the round trip works by hand.

# Definition of Clean
Reuse `MmfdbDatasetPickerDialog` + `datasets.open` (no new browser); thin GUI orchestration only; `modules/ndxplorer` untouched; identity via the [PRD-17](prd-17.md) resolver so the picker scopes correctly.

# Implementation status
Direction A is implemented:
- `chisurf/plugins/ndxplorer/mmfdb_launcher.py` — `open_burst_selection_from_mmfdb()` (pick via `MmfdbDatasetPickerDialog` → resolve path via `mmfdb.datasets.open` → `open_path_like_drop`), plus `resolve_dataset_path` (tested against the real in-process client) and `send_path_to_ndxplorer` (direction B helper).
- `chisurf/plugins/ndxplorer_open_burst/` — the menu entry **"Tools:Open Burst in Explorer"** invoking the launcher.
- Manual test now: run that menu action (or, from the Code Editor, `from chisurf.plugins.ndxplorer.mmfdb_launcher import open_burst_selection_from_mmfdb; open_burst_selection_from_mmfdb()`), pick a registered burst selection, and it opens in the exploration tool.

## CLI handoff (verified)
The `raw+sample → BS → exploration tool` path is now exercisable headlessly:
- The **Burst Selection CLI** gained MMFDB registration: `csc burst-selection analyze … --mmfdb --db <db> --sample-name <name>` registers raw inputs linked to the sample, burst tables, and a single output-folder group, printing `mmfdb_artifacts` (with the group's `output_folder` artifact id).
- That group artifact resolves (via `MFDatabase.open_dataset`, the same call behind `mmfdb.datasets.open` / `resolve_dataset_path`) to the on-disk burstwise folder containing the `.bur` files co-located with the TTTR — exactly what the exploration tool opens as a `burst_dir`. Verified on `bh_spc132_sm_dna` and covered by `test_cli.py::test_analyze_mmfdb_registers_raw_sample_and_group`.
- **Shared-DB caveat:** the in-process `MMFDBClient` opens the *configured* database, so for a real round trip Burst Selection and the exploration tool must target the same MMFDB (use the configured DB or thread the same path through both).

Direction B is now wired: a "→ ndX (current)" toolbar action on the Burst Selection tool resolves the last analysis output path (`_current_burst_output_path`) and calls `send_path_to_ndxplorer`. The **headless exploration-tool side** (use it as a parameter-based burst filter *and* for headless imaging) is specified in [PRD-31](prd-31.md) for separate implementation.

# Relationships
- Manual-test enabler for [PRD-04](prd-04.md) (burst pipeline) and the Phase-2 spine ([PRD-11](prd-11.md) / [PRD-16](prd-16.md)).
- Reuses [PRD-10](prd-10.md) (dataset browser / picker) and [PRD-17](prd-17.md) (identity resolver); applies [PRD-23](prd-23.md) (thin widgets). Mirror the pattern the Microtime Shifter already uses for the picker.
- Headless exploration-tool leg specified separately in [PRD-31](prd-31.md); generalized to all burst-ID producers/consumers in [PRD-34](prd-34.md).
- Touches [MMFDB (current)](/architecture/mmfdb.md) and the [plugin system](/architecture/plugin-system.md).
