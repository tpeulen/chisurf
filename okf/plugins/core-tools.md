---
type: Plugin Group
title: Core tools plugins
description: Infrastructure plugins — settings, onboarding, plugin/model management, MMFDB admin and user management, project browsing, updates, acquisition and batch analysis.
resource: chisurf/plugins/core/
tags: [plugins, infrastructure]
timestamp: '2026-07-05T00:00:00Z'
---

Core tools are the host-side infrastructure: configuration, onboarding, database and
user administration, project I/O, updates, data acquisition, and batch runs. They live
under `chisurf/plugins/core/` and follow the same manifest contract as feature plugins,
so ChiSurf's own plumbing is packaged as plugins too.

## Where to pick this up

Two open fronts: the **PTO inspector**'s operation index, and **Global View**
(see [below](#global-view-the-parameter-network) for what it now is).

### PTO inspector

1. **Four shipped operations have no tool claiming them**, so ▶ Open tool is
   correctly but unhelpfully dark on a lot of real containers:
   `tcspc_histogram_computation`, `tcspc_fitting`, `fcs_correlation` and
   `population_selection` (the last is claimed by `ndxplorer`, the first three by
   nobody). Re-derive the list with
   `python -c "from chisurf.core.plugin.operations import operation_index; print(sorted(operation_index()))"`
   and diff it against the writers:
   `grep -rn 'operation_type=' chisurf/ --include=*.py | grep -v /test`.
   The **trap** is that the first three are not written by a plugin at all — they
   come from `chisurf/core/experiments/**/reader.py` and the fit machinery, which
   have no manifest to declare `operation_types` in. Deciding where a
   non-plugin step declares itself is the actual blocker, and it blocks more than
   this button: it is the same question as "which tool owns a fit window".
2. **`bid_to_analysis` and `fcs_correlator` have no `manifest.json`** (legacy
   AST-metadata plugins), so they cannot declare an operation either. Both write
   one (`import`, `fcs_correlation`).
3. **The graph is laid out by insertion order within a layer**, so edges cross
   more than they need to on a container with a dozen artifacts. A barycentre
   pass over `provenance_graph()` would fix it and is self-contained — the
   layering (longest-path) is already right and must not change.
4. *Not tried:* rendering the `.pto`'s README and mmCIF metadata payloads. The
   view model already reads them (`payload_text`), but no section shows them; an
   `info` section bound to it is the whole change.

### Global View

The window is one emtk surface since 2026-09-23 (below). Open, in order:

1. **Batch the GraphML load.** `GlobalViewModel.apply_graph` still writes values
   and fixed flags one RPC call at a time -- two per node, one per edge. Fine for
   the fits anyone has open today, not for a saved network of a few hundred
   parameters; a batched `set_parameters` on the fitting client is the shape of
   the fix.
2. **The legend can cover a node.** The key is drawn over the top-left corner
   and the editor's fit-to-content does not know about it; visible in
   `docs/guides/figures/globalview_factor_graph.png`. Reserve the key's box in
   the fit, rather than moving the key, which is where people look for it.
3. **Per-column filters.** The Qt table had a filter row per column; the emtk
   table has one filter box matching any cell (`DataTable.column_filters`
   exists, with no UI). Recorded as a deliberate difference in the parity pair;
   add the UI to emtk if someone misses it.
4. **The fits come from `FittingClient.get_fit_objects()`**, which is
   deprecated. The window needs the live objects (links are between them), so
   the replacement is an in-process accessor that says so, not the RPC list.
5. *Tried and reverted (August):* a plain drag on a parameter moves it and
   Shift-drag links. It breaks every user's muscle memory for the plugin's one
   purpose; drag = link stays.

| Plugin dir | Display name | What it does |
| --- | --- | --- |
| `core/setup` | Setup:Settings | Unified Settings dialog that hosts several config panels. |
| `core/boarding` | Help:Boarding Wizard | First-run onboarding wizard (rebuilt as a `boarding.view.json` directed stepper). |
| `core/plugin_manager` | Setup:Plugins | Enable/disable and inspect installed plugins. |
| `core/plugin_check` | Tools:Miscellaneous:Plugin-Check | Startup-error test harness across all plugins; reports pass/fail/skip. |
| `core/model_manager` | Setup:Models | Manage fitting models. |
| `core/mmfdb_admin` | Tools:MMFDB Admin | Manage the Multiparametric Fluorescence Database: samples, experiments, setups, data, provenance, project archives, fluorophore curation. |
| `core/user_editor` | Setup:User Editor | Manage users registered in the MMFDB. |
| `core/switch_user` | Setup:Switch User | Switch the active MMFDB user for the session. |
| `core/database_connector` | Core:Database Connector | Source/user DB resolution, migration, backup/reset, FLR CIF import/export. |
| `core/project_browser` | Tools:Open Project | Browse, save, restore, export/import projects via MMFDB with version control. |
| `core/updater` | Setup:Updates & Packages | Update checker/installer and conda package manager (panels inside Settings). |
| `core/acq` | Main:Tools:Acquisition | Single-molecule acquisition from TCSPC hardware or the built-in tttrlib photon simulator — push-based, see [below](#acquisition-is-a-stream). |
| `core/batch_analysis` | Main:Tools:Batch-Analysis | Apply one template fit to many datasets/files and export consolidated results. |
| `core/globalview` | Main:Tools:Global View | Interactive network graph of parameter relationships across fits — see [below](#global-view-the-parameter-network). |
| `core/help` | Help:Documentation | Documentation browser and editor (Markdown + the reStructuredText user manual), with human-review sign-off tracking. |
| `core/lightpath_simulator` | Spectroscopy:Light Path Simulator | Compute crosstalk and R₀ overlap integrals for an optical path. |
| `core/pto_inspector` | TTTR:PTO Inspector (`menu_hidden`, in the `filetools` hub) | Reads a `.pto` back: every object with its kind/operation/grain, the payload as a chitable or a chiplot curve, the recorded settings, and the provenance **DAG** rendered through the node-editor viewer. **▶ Open tool** resolves an artifact's `operation_type` to the plugin that performs it (see [the operation index](#which-tool-performs-which-step)) and opens it on the same file. Headless: `csg_pto_inspect`. |
| `sample_database` | Legacy:Sample Database | Retired prerelease MMFDB surface; active work belongs in `core/mmfdb_admin`. |
| `ai_settings` | Tools:AI Settings | Root-level AI provider/backend configuration tool. |

Every tool is discovered by `manifest.json`, activated with a `PluginContext`, and
renders declaratively ([plugin system](/architecture/plugin-system.md),
[Plugins target](/specs/plugins.md), [GUI & AutoForm](/subsystems/gui-autoform.md)).
The database-facing tools (`mmfdb_admin`, `user_editor`, `switch_user`,
`project_browser`, `database_connector`) are front-ends over the provenance store —
see [MMFDB](/architecture/mmfdb.md) and [PRD-02b](/prds/prd-02b.md). Acquisition tracks
[PRD-32](/prds/prd-32.md)/[PRD-33](/prds/prd-33.md). Because this plumbing is itself
plugins, it exercises the same discovery/lifecycle rules the [Plugins target](/specs/plugins.md)
demands of feature code.

## Acquisition is a stream

`core/acq` drives every device through one seam — `read_fifo(max_words)` returns
raw `uint32` records — and everything that happens to a photon after that lives
in **one Qt-free object**, `acq/pipeline.py`:

```
device words → PhotonDecoder → [ PhotonSink, live consumers ] → snapshot()
```

Three properties are the point, and each replaced something that looked like it
worked:

- **One decoder.** `PhotonDecoder` wraps the photon library's `decode_records`
  with a carried decode state, and the device says which record format it emits
  (`record_type_for_device`, a device attribute or the device-type table). An
  unknown device raises rather than defaulting to B&H. There was a second,
  hand-rolled numpy bit-field decoder that PicoQuant fell through to; a guard
  test fails on any `np.right_shift` returning to the plugin.
- **Nothing downstream keeps the photons.** The decay is a
  `StreamingDecayHistogram`, each correlation curve a `StreamingCorrelator`, the
  MCS a `StreamingIntensityTrace` with a rolling window, and the count-rate and
  inter-photon buffers are bounded deques. `snapshot()` — the only thing that
  crosses to the GUI thread — is display state sized by the configuration, not
  by run length. What this replaced concatenated three growing arrays per chunk
  and re-ran the *batch* correlator over the full history every five chunks.
- **A chunk crosses into C++ once.** The consumers' `push_np` takes a whole
  chunk. Pushing photon by photon costs 1.13 µs each, which does not fail — it
  simply stops keeping up with a card.

The theory is in [Streaming analysis](/docs/concepts/live_streaming_analysis.md)
and the workflow in [Live acquisition](/docs/guides/65_live_acquisition.md).
`PhotonSink` is the seam for writing the stream to a `.pto` *during* the
measurement; it is a `NullSink` today and tracked in [PRD-98](/prds/prd-98.md)
against the container work.

## Documentation review gating

Much of the user manual was machine-drafted, so `core/help` doubles as the review
tool that keeps unchecked prose out of a release. Pages under a tracked directory
(`docs/manual`, listed in `api/review.TRACKED_DIRS`) carry one of three states:
**reviewed**, **stale** or **unreviewed**.

State lives in a per-directory sidecar `review_status.json` rather than in the
pages, so the reStructuredText stays clean and a whole directory's review state
diffs as one file. The registry stores a **content hash** alongside each sign-off,
which is what makes *stale* possible: editing a page after it was approved
invalidates the approval automatically, so a page cannot be signed off once and
then quietly rewritten. The sidecar is safe from regeneration because
`docs-manual` is retired — the manual RST is hand-maintained.

Three surfaces share one Qt-free core (`api/review.py`):

- **GUI** — the browser badges every manual page (✅ / ⚠️ / ⬜), banners the open
  page with its state, offers *Mark reviewed*, and filters the tree by status.
  Saving an edit re-checks the hash, so a page visibly turns stale as you edit it.
- **CLI** — `help review-check` (the gate, exit 1 on any blocking page),
  `help review-list`, `help review-set`.
- **RPC** — `help.review.status` / `.set` / `.check`.

Enforcement is split deliberately. `docs-html` still builds unreviewed pages —
dropping them would hole the toctree and break cross-references — but a Sphinx
extension (`docs/_ext/review_banner.py`) stamps each with a visible warning. The
hard gate is the separate `docs-check-reviewed` task, which `docs-release`
depends on, so a production build refuses to publish human-unchecked prose.

Reading the manual at all is new: discovery previously globbed `*.md` only, so
the 79 `.rst` pages were invisible. `api/rst.py` renders them through bare
docutils (a Sphinx build is far too slow for interactive browsing), registering
no-op fallbacks for Sphinx-only roles such as `:doc:`/`:ref:` so cross-references
degrade to readable labels instead of error markers.

## Global View: the parameter network

`core/globalview` is where a global analysis is *assembled*: it draws every open
fit, every parameter in it, and every link between parameters, and lets those
links be made and broken by hand. The theory it serves is in
[`docs/concepts/global_analysis.md`](../../docs/concepts/global_analysis.md) and
the workflow in
[`docs/guides/60_global_analysis.md`](../../docs/guides/60_global_analysis.md);
the linking machinery itself belongs to [parameters](/subsystems/parameters.md).

### One emtk surface

Since 2026-09-23 the whole window is **one emtk control** in a Qt host, on the
same pattern as ndXplorer:

| file | is |
| --- | --- |
| `gui/globalview.view.json` | every control: the toolbar, **View**, **Selection** and **Parameters** panels -- the tables are `data_table` sections |
| `gui/model.py` | `GlobalViewModel`, Qt-free: the settings the spec binds, the graph document, the table records, the selection, one method per button |
| `gui/surface.py` | `GlobalViewSurface` (`emtk.app.ImApp`): the toolbar form, an `emtk.docking.DockManager` (Network + Parameters, Selection + View), the status line |
| `gui/emtk_view.py` | what a node and an edge look like: kinds, colours, disc or square, the legend |
| `gui/tool.py` | `GraphWizard`: the Qt host -- file dialogs, warnings, help, the guided tour, fit events |

It replaced four hand-built Qt panels around the emtk network (a
`QToolBar`, a `QFormLayout`, a scroll area of per-parameter editor widgets, and
an AutoForm-hosted Qt table). The before/after pair is in
`chisurf/plugins/core/globalview/tests/renders/` with both control inventories;
re-take the after-half with `test/gui/globalview_parity_capture.py`. Deliberate
differences: glyph buttons became words (the emtk atlas has no emoji); the
Selection panel's per-parameter editors became one table with a *Role* column;
the Qt table's per-column filter row became one filter box.

The guided tour spotlights emtk controls through a host hook added to
`chisurf/gui/widgets/tools/guided_tour.py`: a host may define
`tour_target(target) -> (widget, rect)` and a `tour_used(name)` signal, and
`GraphWizard` answers from the surface's `FormState.rects`.

### One enumeration: rows, network, factor graph

`chisurf/core/fitting/parameter_network.py` enumerates the session's owners
(`session_owners`: fits, a `FitGroup` by its local fits, registered groups;
never the aggregate global model) and builds all three views from them:
`parameter_rows`, `build_parameter_network` (edge kinds explicit: ownership,
link, base) and `build_session_factor_graph` (one likelihood per owner over its
parameters' link **roots**, as a `factorgraph.FactorGraph`). The plugin's
`api/graph.py`, its RPC backend, the server's `graph.build` service and the Qt
`global_parameter_table` section all read it; before, there were three network
builders and a fourth row enumeration, and they had drifted (the server had no
group nodes; the table descended into fit groups and the network did not).

### Two representations

**Parameter network** (default): owners as large discs, parameters as small
ones, and three edge kinds that are three claims:

| edge | drawn | means |
| --- | --- | --- |
| ownership | thin grey, no head | this parameter belongs to that fit or group |
| link | cyan, arrowhead at the **master** | this parameter follows that one |
| base (*Connect base*) | dim | these owners are things links can run between |

**Factor graph**: each owner is a likelihood (a square, `emtk.nodes.NodeShape.SQUARE`)
joined by *scope* edges to the variables it reads, links resolved. A variable
two or more likelihoods read is *shared* (gold): the thing a global fit is
global through. A follower hangs off its root by its link arrow; a held
parameter is *evidence* on its likelihood. The status line names the shared
variables and counts the independent blocks (`FactorGraph.connected_components`),
which is how "I linked it" is checked against "it is coupled": the guide's own
screenshot session has a second FRET-low curve whose `t0` was never linked, and
the old network never drew that curve at all.

### Refreshing without cost

`fit.`/`parameter.` events arrive once per fit iteration; the host coalesces
them (`REFRESH_DEBOUNCE_MS`) and skips them while hidden. The model re-reads
the fits but re-runs the layout only when the picture's structure signature
(ids, kinds, labels, edges) changed -- values moving is not a reason to move a
node. *Refresh* always lays out again; with *auto* off the status line says
when the picture is stale.

### Traps this area has already sprung

- **A link edge resolved by name** matched every same-named parameter in the
  session, so three fits with a `tau1` turned one link into three arrows. The
  master is resolved by UUID, the name only for a master that has none.
- **Link direction in the editor was reversed** until 2026-09-23. The editor
  reports a drawn link as (dragged-from, dropped-on) and the old host made the
  *dropped-on* parameter follow -- the opposite of the arrow drawn and of what
  the guide said. Breaking an arrow passed its master, so the follower stayed
  linked. Both pinned in `tests/test_model.py`.
- **Node ids are not array indices.** Nodes are named `owner:<n>` and
  `param:<uid>`; the old window's positional arrays put an edge on the wrong
  parameter whenever *Include fixed* dropped a node.
- **`chisurf.core.graph` edges are undirected**: the graph is used for layout
  only, and edges carry their direction and kind separately.
- **emtk's `set_cursor_pos` is in frame coordinates**, not window-relative: the
  status line was drawn under the toolbar until the surface said so.

## Reading a `.pto` back

`core/pto_inspector` is the read side of [the photon container](/specs/pto-mfdb.md).
The writer records the artifact list, the grains, the operations, the complete
settings and the derivation edges; until this tool nothing read any of it back
for a person.

It is a thin plugin by construction: `core.py` is Qt-free (open, list, read a
payload, build the graph), `gui/view_model.py` holds the selection, and
`gui/pto.view.json` is an AutoForm spec over two new **general** sections. The
tool contributes no widget code of its own.

### The provenance view is a graph, and had to be

An indented tree cannot draw a container's provenance without lying about it: a
burst-wise lifetime fit is derived from the bursts **and** from the background,
so a tree must either repeat a node or drop an edge — and a node reached by two
paths is the interesting one, because that is what "the background correction was
used here as well" looks like.

`provenance_graph()` therefore emits the [node-editor](/subsystems/graph.md)
JSON schema and the read-only viewer draws it. Two details are load-bearing:

- **Layers are longest-path, not shortest.** A node drawn beside its nearer
  parent has an edge running backwards. Pinned by
  `test_a_node_is_drawn_right_of_every_parent`.
- **A root has no input port.** A drawn-but-unconnected port reads as a missing
  parent.
- **Nodes are circles, not boxes** (`"shape": "circle"`, added to the node editor
  for this). These nodes hold nothing — they name a thing and its connections —
  and a page of titled boxes reads as a form where a page of circles reads as a
  network. It is also what makes a twelve-artifact chain fit without scrolling:
  a box is 210x80, a circle 42.

### Which tool performs which step

A `.pto` records the `operation_type` and deliberately never names the program —
a term naming a ChiSurf plugin would defeat the tool-agnostic vocabulary. The
inverse lives in the manifests: `operation_types` (new manifest field) is a
plugin's declaration of the steps it performs, and
`chisurf.core.plugin.operations` builds `{operation_type: [manifest]}` by reading
manifests — no import, no Qt, and no list maintained anywhere but in the plugins.
25 operations are claimed today; the mapping is many-to-many on purpose (several
tools legitimately produce a `model_fitting` result).

A guardrail asserts every declared term is a real
`_mmfdb_operation.operation_type`: an invented one would sit in the index
unreachable, and the symptom would be a button that never lights up.

### Traps this area has already sprung

- **Rebuilding the graph on selection.** The model reports the current selection
  through `meta.focus`, so the graph dict differs on every click; reloading on
  that reset the zoom and recentred the view each time the user selected
  anything. The section compares `(nodes, edges)` only, and `select()` uses
  `ensureVisible`, not `centerOn`.
- **A store's units were dropped by every table.** A column states its unit
  (`column.attribute("units")`) and `DataStoreSource` built `label=name`, so a
  duration in milliseconds and a lifetime in nanoseconds looked alike. Fixed in
  the shared table, so every chitable over a store gained it at once.
- **`"spectral"` was the node editor's default `port_type`** — a name from one
  graph's domain — and it was *drawn* beside every port of every untyped graph.
  The untyped sentinel is now `""`; compatibility is unchanged.
- **A hub swallowed the `?` and the Guide.** `embed_mainwindow` rebuilt the
  button row from toolbar actions and skipped any action with no text — which is
  exactly what `toolbar.addWidget` produces. Every aggregated tool had lost both.
  Widget-actions are re-hosted now, and shown *after* the row is installed,
  because the reparent carries Qt's hidden state with it.
