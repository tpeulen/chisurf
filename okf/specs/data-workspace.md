---
type: Spec
title: Data workspace — one way in, one place to pick data
description: Design for PRD-154 item 14 — photon datasets in the .cs.pto project, a single file drop, a typed and filterable Datasets workspace, and plugins fed from it through one declared input; file paths stay in the API and CLI only.
tags: [specs, data, workspace, pto, plugins, ux]
timestamp: '2026-10-26T00:00:00Z'
---

# Data workspace — one way in, one place to pick data

Owner directive 2026-10-26 ([PRD-154](../prds/prd-154.md) item 14): data enters the UI through **one
file drop**, lives in the **Datasets workspace** (typed, filterable), and **plugins are fed from the
workspace** instead of opening files. File interfaces stay in the **API and CLI** (paths and addresses in —
scripts and the agent need them); in the UI they degrade the UX and go.

## Where it stands (recon 2026-10-26)

* No photon dataset kind: TTTR readers histogram photons into a `DataCurve` and keep only
  `meta_data["tttr_header_json"]` (`core/experiments/tcspc/tttr_reader.py`).
* The Datasets view (`chisurf/emtk/views/datasets.view.json`, `DatasetsModel` in `emtk/fit_docks.py`) shows
  `#`, name and experiment; rows drop the DTO's `type` and `filename`; no type filter (emtk has a free-text
  table filter and `DataTable.column_filters`, the latter not exposed in the spec dialect).
* The project (`core/project/session.py` `_curve_record`) stores curves inline as JSON and the source file
  as a bare path — no size, no sha256; any dataset that is not a curve or structure is refused.
* The only declared plugin input is the manifest `accepts` hand-off (`core/plugin/handoff.py`, seven
  manifests, path payloads). About 85 plugins take files — ~105 FileDialog sites, ~75 drop handlers,
  ~33 MMFDB-picker uses, ~60 Load-example actions — by data kind: photon streams ~40 plugins, burst
  tables/folders ~17, curves ~13, structures 4 families, images 7, config JSON ~15. Six read the shell's
  datasets or fits (batch_analysis, maxent_decay, irf_estimator, fret_line, f_test, globalview), each its
  own way; nine push results into the workspace. The shell drop reads only the first path with the
  selected reader.
* Dragging a workspace row only reaches fit windows (`DataDocks.dataset_dragged`).

## Addressing

One string names any data: a file path, or a path into a container — `project.cs.pto/<dataset>`,
`measurement.pto/<run>[/<table>]`, composable, `@<uid>` for a stable project dataset. The container is the
shortest leading prefix that is an existing regular file. Conformance table:
`ptolib/tests/data/address_cases.json`, run by ptolib (C++/Python), tttrlib and chisurf
(`chisurf/core/fio/address.py`). The old `path|member` selector is removed.

## Data kinds

A small central vocabulary, emitted as `kind` on every dataset DTO and row (beside `experiment`):

| kind | what | today's source |
| --- | --- | --- |
| `photons` | a single-photon (TTTR) stream | new: `PhotonStreamDataset` |
| `decay` | a fluorescence decay (TCSPC curve) | `DataCurve`, experiment TCSPC |
| `correlation` | an FCS curve | `DataCurve`, experiment FCS |
| `histogram` | PDA / PCH / burst histograms | `DataCurve`, those experiments |
| `bursts` | a burst run of a measurement container | `.pto` run (address) |
| `structure` | a molecular structure | existing structure record |
| `image` | an image / CLSM stack | new kind, address of the stack |

Fit-only paths (model choice, "+ Analysis", `build_fit_group`) take the fittable kinds only.

## Photon datasets in the project

`PhotonStreamDataset(ExperimentalData)` (`core/data.py`): `address`, `size_bytes`, `sha256`, the header
JSON, the routing channels; the photons open lazily through `staging.open_tttr(address)`. In the `.cs.pto`:

* **linked** (default — owner 2026-10-26: the project stays slim and never duplicates measurements when
  many TTTR files are processed): a ptolib **file link** object — the target's path relative to the
  container, its size and sha256 (and the tttr header for listing without opening). The dataset's address
  is `project.cs.pto/<dataset>`; resolution follows the link transparently. A missing or changed target is
  reported on open (size/hash mismatch), never silently re-read; a moved project re-finds targets by the
  relative path, then by name beside the project.
* **embedded** (explicit "Pack project", for sharing or a deposit): the target's bytes streamed into the
  container in place of the link (ptolib `add_file`), never through JSON or `ResourceContext.sources`.
  Unpack writes them back out and restores the links.

Autosave never re-hashes link targets or packed photon objects (immutable once recorded); hashing happens
once, at import.

**The user decides, in the UI** (owner 2026-10-26):

* *Embed or link* — a project setting (default: link) and a choice at import (the drop offers "Link" /
  "Embed" for the batch, remembering the last answer); a dataset's context menu switches it later
  ("Embed in project" / "Link to file").
* *Make project self-contained* — one tool (File › Project › Make self-contained…) embeds every link. Before
  it starts it checks every target; unresolved ones go to the next tool first.
* *Locate missing data* — lists every link that does not resolve or no longer matches (missing, size or hash
  changed), with where it was. "Search in folder…" walks a folder the user picks and proposes candidates by
  name, then confirms by size and sha256; "Replace with…" lets the user point at a file explicitly (a moved
  or renamed original). A replacement whose hash differs is shown as a different file and needs an explicit
  "Use anyway", which records the new hash. The tool also opens on its own when a project opens with
  unresolved links.
* *Export gate* — any export that leaves the machine (Zenodo deposit first; also project export/share)
  checks the project: linked data and unresolved links are flagged with a warning that names them. The
  Zenodo export is refused while the project is not self-contained unless the user gives an explicit
  override (a deliberate checkbox naming the consequence, then a confirm); the override is recorded in the
  deposit's metadata. "Make self-contained" is offered right there.

**File links in ptolib** (canonical, re-vendored into tttrlib and imp.bff): a first-class object kind, not
an application convention — `add_link(path, …)` records relative path + size + sha256; `stream`/`extract`/
`open_address` follow it; `verify` reports missing/changed targets; `compact` keeps links links (98497f1);
`pack`/`unpack` convert between linked and embedded; `relink(uid, path)` points a link at a new target
(size + sha256 checked, a mismatch refused unless forced) — the repair step of *Locate missing data*. The present `external_payload_path` hook and
tttrlib's `add_sidecar_file` / chisurf's `_mmfdb_sidecar.*` tags map onto it (one mechanism).

## One way in

The shell's drop (`main_app.on_files_dropped` → `DataDocks.drop`) classifies each dropped path by kind
(TTTR by extension/header, `.pto` by profile, curve files by reader, structures, images) and adds it to the
workspace (and the project). A drop on a plugin window adds to the workspace too, then feeds that plugin
(below). The per-plugin drop hooks and Open/Add-files buttons go from the UI; their file-path code stays
behind the API/CLI.

## The workspace view

* Columns: name, **kind** (icon + word), experiment, source (address, file name shown), size / photons.
* A **kind filter** above the table (All · Photons · Decays · Correlations · Histograms · Bursts ·
  Structures · Images) plus the free-text filter; both pinned above the list (gui-autoform rule "a filter
  stays above its list"). emtk gets a `column_filter` spec key exposing `DataTable.column_filters`.
* Context menu **Open in…** lists the plugins that accept the row's kind; dragging a row onto any plugin
  feeds it (not only fit windows).

## Plugins fed from the workspace

Declared, not coded: a manifest `accepts` entry gains `from_workspace`:

```json
{"name": "tttr_files", "receive": "...:receive_files", "required": ["files"],
 "from_workspace": {"kinds": ["photons"], "many": true, "key": "files", "with_setup": true}}
```

The shell resolves it once (`EmtkShellApp.feed_from_workspace(plugin_id, rows)` beside `hand_off`): it
builds the payload from the rows' **addresses** (plus the shared setup when `with_setup`) and calls the
existing receive hook — plugins need no new entry point. The plugin's form gets one generated **Input**
section (a choice or table of workspace rows of the declared kinds, from a shell-provided source — the
`RUN_PICKER_SECTION` / `with_run_picker` pattern generalised), so the plugin never draws its own file
buttons. Hubs feed steps from their context by declared kind instead of hand-written `_to_<role>` adapters.

## Order of work

1. Kinds + DTO `kind` + rows keep kind/source; the photon dataset; project storage (embedded/referenced).
2. Single drop with kind routing; workspace view (kind column, kind filter, Open in…, drag onto plugins).
3. `from_workspace` declaration, `feed_from_workspace`, the generated Input section.
4. Plugins migrate family by family — TTTR-file tools first, then burst runs, decays, structures,
   images — each losing its FileDialog/DatasetPicker/drop hook in the UI. A shrinking-allowlist guard
   forbids input file dialogs in plugin UIs.
