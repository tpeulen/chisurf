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

## Where to pick this up

1. Measure: **The last allowlist lines.** `python -c "import sys; sys.path.insert(0,'.');
   from test.test_no_input_file_dialogs import allowed_entries; print(len(allowed_entries()))"` — **4**
   (2026-10-27, from 193): `core/legacy_export/gui/app.py` (dialog, drop) and
   `core/metadata_editor/gui/app.py` (dialog) hold another session's uncommitted edits and wait for it;
   `ndxplorer/gui/app.py` (mmfdb) opens an MMFDB burst selection with its provenance — it goes when the shell's
   *Add from MMFDB…* links burst selections (today photons/images only). Two gaps the guard does not see:
   card-based tools still open input files through `card_shell.open_file` (not in the guard's
   `DIALOG_HELPERS`): FRET docking's *Add Files*/FPS JSON, Pair Selection's trajectory/FPS rows, QuEst's *Load
   project*; and the docking/pair-selection cards draw no Input section yet (their `accepts` work through *Open
   in…* and drags). New kinds this round: `table` (5+ named columns, or an `.npz` of 5+ equal 1-D arrays —
   burst and result tables; curves keep 2–4 columns) and `trajectory` (`.dcd/.xtc/.trr/.nc`). Tool presets
   (`chisurf.tool/<plugin>/1`) come back as setup rows for burst_selection, fusion, H2MM, MLE and the burst FCS
   correlator.
2. Open: **Hubs.** alex_suite / burst_analysis take their photons and setup from the workspace and hand the
   later steps a container run (no legacy folder); the hubs still call their own `_to_<role>` adapters
   rather than each step's declared input.
3. Open: **Setups as input.** `with_setup` is implemented (a `setup` row's address travels as `setup`) but no
   plugin declares it yet; intensity_trace still picks detector setups from its own setups store — the
   next photon tool should take its setup from the workspace.
4. Open: **Curves dropped with a file type chosen for another experiment** keep that choice (the user's
   selection wins over `classify.curve_reader`); only an empty selection, or the same experiment, takes
   the sniffed settings (`skiprows`, `x_on`, `dt`, `is_vv_vh`). A PyCorrFit CSV sniffs as FCS-CSV.
5. Measure: **Journeys** (`test/e2e/test_workspace_journeys.py`) are the acceptance proof; run on `ssh home`
   (`build_tools/remote_test.sh`), never on the laptop.
6. Open: **Burst family, on the project model** (§ Burst results live in the project). Migrated (2026-10-26):
   BVA, 2CDE, GS, H2MM (per-photon tables into the run's container), MLE, burst browser, burst FCS
   correlator, burst_selection, burst_background, burst_irf_bg, fret_check, bid_to_analysis,
   burstwise_import (a dropped legacy burstwise folder is classified `burst_folder` and handed to its
   `legacy_folder` hand-off), the burst_analysis hub, **burst_fusion** (a run is fused into a new run
   `<run> fused p<thr>` of the same container -- stored as a burst selection, algorithm
   `recurrence_probability`, with `assembly`/`membership` tables and a `fusion groups` companion on
   the source run; legacy folders still fuse to a folder headless), **mfd_prepare**
   (`prepare_burst_folder` reads a run through the shared run reader; it writes nothing) and
   **alex_suite** (Files step names `alex_suite`'s own `accepts`; titration takes burst runs, many).
   accurate_fret keeps its CSV/NPZ table routes (no workspace kind for a plain table); burst_ebfret
   (trace files: no kind) is open. Container runs written by an import (`import` operation, BID) are
   listed as runs (`classify.BURST_RUN_OPERATIONS`), so they come back after a project reopen. The hub's
   materialized hand-off names its run after the search settings (`_search_run`): an unnamed run lands
   at the container's top level, where ndX lists it as `bi4_bur` while `resolve_run` says `""`, and
   every later step then found no burst table. `.bid`/`.bst` get no data kind on purpose: a BID holds
   photon indices into one TTTR, so it is that stream's companion, found beside it by stem. Blocks: no
   workspace kind for a plain or result table; tool presets (settings JSON) are not classified as
   `setup`, so "Load settings" dialogs remain (fusion, h2mm, MLE, correlator, burst_selection); the
   Datasets view cannot yet show a run's companion tables as view-only children.

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

A small central vocabulary (`chisurf/core/data_kinds.py`), emitted as `kind` on every dataset DTO and row
(beside `experiment`); every registered experiment is mapped there (`Global` deliberately to no kind):

| kind | what | today's source |
| --- | --- | --- |
| `photons` | a single-photon (TTTR) stream | new: `PhotonStreamDataset` |
| `decay` | a fluorescence decay (TCSPC curve) | `DataCurve`, experiment TCSPC |
| `correlation` | an FCS curve | `DataCurve`, experiment FCS |
| `histogram` | PDA / PCH / burst histograms | `DataCurve`, those experiments |
| `trace` | a signal over time (DEER dipolar evolution, stopped flow) | `DataCurve`, DEER / Stopped flow |
| `bursts` | a burst run of a measurement container | `.pto` run (address) |
| `structure` | a molecular structure | existing structure record |
| `image` | an image / CLSM stack | new kind, address of the stack |

Fit-only paths (model choice, "+ Analysis", `build_fit_group`) take the fittable kinds only.

## Experiments for the non-curve data (owner 2026-10-26)

Declared in `experiment_configs.yaml` like the others, without fit models:

* **Single photon counting** (kind `photons`) — TTTR files and photon members of containers. What an
  analysis of it produces (burst runs, their tables, sub-ensemble decays) is a **result of this dataset**,
  embedded in its container and shown as **child rows** of it in the workspace (`m000.pto/<run>[/<table>]`);
  there is no separate burst experiment. Kind `bursts` remains only as what burst consumers declare to take.
* **Imaging** — one experiment, two representations, both supported: **photon images** (photon events
  with position: photon-counting detectors such as EIGER, scanning CLSM from a TTTR stream with markers),
  which keep their photons (linked/embedded like photon streams; the image is built on demand at a chosen
  binning), and **intensity images** (frames/stacks). The reader detects which; a row says which; plugins
  declare which they accept.
* **Instrument setup** (kind `setup`) — detector/channel setups, LUTs, kinetic schemes, IRF/background
  patterns: the inputs a tool reads that are not measurements.

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

**Remote link targets** (owner 2026-10-26): a link may point at a URI instead of a file — first
`mmfdb://artifact/<id>[?server=<host>]` — mmfdb's existing node reference (`mmfdb://<node_type>/<node_id>`,
`queries/artifacts.py`), resolved against the user's configured MMFDB connection unless `server` names
another, fetched with the user's credentials the way the web pages fetch it, later `https://` (e.g. a deposited record). ptolib stays generic: a link target may
be a URI, ptolib keeps a scheme → resolver registry (`register_link_resolver`), resolving fetches into a
local cache and then checks the recorded size + sha256 like any file. Credentials are never stored in the
container or the URI; the mmfdb resolver (mmfdb repo) takes them from the user's MMFDB client
authentication. Because MMFDB's object store is content-addressed, a link with a recorded sha256 can also be
satisfied by any MMFDB store holding that object. ChiSurf registers the resolver at startup; *Locate missing
data* searches MMFDB too.

**One protocol, desktop and web** (owner 2026-10-26): links resolve through the same HTTPS endpoints in the
desktop app and the web release (`python -m chisurf.web`, Pyodide on the page's main thread). MMFDB's web
server already serves `/objects/<uuid>` to a bearer token or its HttpOnly session cookie (with CSRF on
writes). Desktop: bearer token from the OS credential store (sign-in via Switch User). Web: the same
session cookie as the MMFDB web page — the page never sees the token; served from the MMFDB server's own
origin (preferred: no cross-site cookies) or, for another origin, an explicit CORS allowlist with
`credentials` and SameSite=None; Secure cookies. Because the page cannot fetch synchronously, resolution is
two-phase on every host: an asynchronous **prefetch** (when a project opens or a link is added) fills a
cache keyed by sha256 — a per-user folder on desktop, IDBFS in the browser (persists across reloads) — and
ptolib's synchronous resolver only reads that cache, reporting "not fetched yet" otherwise. The mmfdb
client's transport is pluggable: `http.client` on desktop, the browser's fetch under Pyodide.

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

*Status 2026-10-26 (all four built, uncommitted at the time of writing):* links/embedding in
`core/project/links.py` (ptolib path behind `links.ptolib_links()`, JSON/`os.walk` fallback marked
"FALLBACK (2026-10-26)" — delete it at the tttrlib relock); embedded bytes stream into the project at save
(`Project.data_files` → `pto.write_project(files=…)`); the repair model `core/project/link_repair.py`;
the tool `plugins/core/project_data` (File › Project › Make Self-contained… / Locate Missing Data…, opens
itself on a project with unresolved links); Datasets context menu Embed in project / Link to file; the gate
`core/project/export_gate.py`, enforced by the Zenodo deposit (record list, single and batch upload; the
override is logged and written into the deposit notes, which voids the metadata approval). Export Project…
warns (does not block) when the copy still links data. **Open:** the ptolib path is only tested against a
fake `PtoFile` — run `test/core/test_project_links.py` and `test/core/test_link_repair.py` on the relocked
tttrlib (real `add_link`, `find_link_candidates`, `sha256_file`, nested reads of a container embedded whole);
an embedded project is rewritten in full on every save; remote (`mmfdb://`) targets are not started.

**File links in ptolib** (canonical, re-vendored into tttrlib and imp.bff): a first-class object kind, not
an application convention — `add_link(path, …)` records relative path + size + sha256; `stream`/`extract`/
`open_address` follow it; `verify` reports missing/changed targets; `compact` keeps links links (98497f1);
`pack`/`unpack` convert between linked and embedded; `relink(uid, path)` points a link at a new target
(size + sha256 checked, a mismatch refused unless forced) — the repair step of *Locate missing data*. The present `external_payload_path` hook and
tttrlib's `add_sidecar_file` / chisurf's `_mmfdb_sidecar.*` tags map onto it (one mechanism).

## Burst results live in the project (owner 2026-10-26)

* **Each photon dataset has an analysis container in the project**: a measurement container embedded
  as `project.cs.pto/<name>.pto`, holding that dataset's burst runs and every table computed from them
  (`chisurf.core.project.analysis`). While the session runs it is a working file in a private session
  folder (`container_dir(<dataset uid>)`); the project embeds it at save (`project_files`, recorded
  in `Project.extra["analysis_containers"]`) and writes it back on open (`restore`). It links the
  photons (`raw_data="sidecar"`): the photon dataset itself is linked or embedded by the project's
  own choice. Nothing is written beside the vendor file, and the legacy `bi4_bur/` folder is an
  explicit export (Legacy Export), never a by-product of a search.
* **One format, one reader.** The container is written by the existing burst writer
  (`burst_selection.api.io.write_container`, `burst_container.write_per_source`) in exactly the
  format ndX reads; every ChiSurf burst tool reads a run *through* ndX's reader
  (`ndxplorer.io.pto_reader.read_run`, the run with its companions as stored) -- ChiSurf's own
  container table read is gone.
* **Companions are tables of their run**, joined by their declared parent (BVA, 2CDE, lifetimes, H2MM
  states, ...), not workspace rows. The workspace shows the runs as children of the photon dataset,
  **derived** from the containers (`derived_datasets`) on every restore and never stored as datasets;
  consumers declare `bursts` = runs.
* **ndX reads the project's runs**: `ndxplorer.io.project_reader` lists `<name>.pto/<run>` stores of a
  `.cs.pto` and reads them through `pto_reader` (nested member read where tttrlib has
  `split_address`, else extracted to a temporary file -- fallback to delete at the relock); a run
  address `m000.pto/<run>` or `p.cs.pto/<name>.pto/<run>` opens directly in ndX.

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

## Acceptance (owner 2026-10-26: "the user does not open files; one file entry point in the UI")

* **One entry point.** The shell drop (and its one "Add data…" equivalent for keyboard users) is the only
  place the UI asks for an *input* file. Saving/exporting *outputs* keeps its save dialogs.
* **Every input is a workspace item.** Measurements (photons, containers, curves, images, structures) and the
  settings a tool reads (detector/channel setups, LUTs, kinetic schemes, IRF/background patterns) — kind
  `setup` — enter through the drop and live in the project.
* **Results go back into the project.** What a tool writes (burst runs, decays, correlations, maps, fits)
  becomes a workspace item of its kind, so the next step picks it from the workspace, never from disk.
* **Guard.** A test fails on any input file dialog, input drop hook or MMFDB-picker-to-local-path in a
  plugin UI; its allowlist starts as today's inventory and only shrinks, to empty.
* **Proof.** Workspace journeys extend `test/e2e/test_pto_journeys.py`: every file-based workflow of the
  [workflow matrix](pto-workflow-matrix.md) and of the plugin inventory (photon tools, burst chain, FCS,
  decays, imaging, structures) is walked in the real UI from one drop into a `.cs.pto` project; opening an
  input file dialog during the walk fails the test.

## Order of work

1. Kinds + DTO `kind` + rows keep kind/source; the photon dataset; project storage (embedded/referenced).
2. Single drop with kind routing; workspace view (kind column, kind filter, Open in…, drag onto plugins).
3. `from_workspace` declaration, `feed_from_workspace`, the generated Input section.
4. Plugins migrate family by family — TTTR-file tools first, then burst runs, decays, structures,
   images — each losing its FileDialog/DatasetPicker/drop hook in the UI. A shrinking-allowlist guard
   forbids input file dialogs in plugin UIs.
