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

The open front here is **Global View** (see
[below](#global-view-the-parameter-network) for what it now is).

1. **Delete the server's copy of the graph builder.** Two implementations of one
   contract: `chisurf/plugins/core/globalview/api/graph.py` and
   `chisurf/server/services/graph.py`. Measure the drift by running the same
   fits through both and diffing the node/edge sets — today the server's has no
   `group` node type at all, so a network fetched over RPC silently omits every
   registered plugin parameter group, and the link-by-name defect had to be
   fixed twice. The blocker is unproven: `api/graph.py` looks Qt-free (its only
   import, `GlobalFitModel`, is function-local) but that has not been checked
   against the server's import path — check it, and if it holds the deletion is
   the whole fix. Recorded in [known issues](/references/known-issues.md).
2. **`GraphWizard.link()` still writes values and fixed flags one RPC call at a
   time** when a GraphML file is loaded — two calls per node, plus one per edge.
   Fine for the fits anyone has open today; it will not be for a saved network
   of a few hundred parameters. A batched `set_parameters` on the fitting client
   is the shape of the fix.
3. **The Selection panel rebuilds every editor on every click.** Cheap now
   (`clear_layout` + `make_fitting_parameter_widget` for at most two nodes) but
   it is the reason `clear_layout` had to be fixed to unparent — worth
   remembering before the selection limit is raised past two.
4. *Tried and reverted:* making a plain drag on a parameter **move** the node
   and Shift-drag create the link. It is the better default in the abstract and
   it breaks every existing user's muscle memory for the plugin's one purpose;
   the gesture is left as it was (drag = link, Shift-drag = move) and both are
   in the tooltip and the help.

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
| `core/acq` | Main:Tools:Acquisition | Single-molecule acquisition from TCSPC hardware or the built-in tttrlib photon simulator. |
| `core/batch_analysis` | Main:Tools:Batch-Analysis | Apply one template fit to many datasets/files and export consolidated results. |
| `core/globalview` | Main:Tools:Global View | Interactive network graph of parameter relationships across fits — see [below](#global-view-the-parameter-network). |
| `core/help` | Help:Documentation | Documentation browser and editor (Markdown + the reStructuredText user manual), with human-review sign-off tracking. |
| `core/lightpath_simulator` | Spectroscopy:Light Path Simulator | Compute crosstalk and R₀ overlap integrals for an optical path. |
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

Four dock panels over a `DockArea`, like every other tool: **Network** (the
graph), **Parameters** (the same content as a table, the shared
`global_parameter_table` AutoForm section), **Selection** (an editor per
selected node, captioned with its owner — two fits of one model name their
parameters identically), and **View** (layout, node size, spread, *Connect
base*, *Include fixed*).

### Drawing

The graph is painted directly, on the shared node-link marks in
`chisurf/gui/widgets/graph_canvas.py` — the same dark grid, radial-gradient
discs and curved arrows the [state-scheme diagram](/subsystems/gui-autoform.md)
uses, so ChiSurf's two graphs read as one idea. That module is the seam: node
palette, backdrop, `ZoomPan`, cubic edge routing, arrowheads, badges, legend.

It replaced a `pyqtgraph.GraphItem`, which sized nodes in **data** coordinates —
so label offsets, arrow lengths and node radii all scaled with the layout, and a
graph was either unreadable dots or a few huge blobs. The layout is now fitted
to the panel (re-fitted on resize and on show, until the user drags a node), and
*spread* scales it past the panel edges instead of being an invisible layout
argument.

Three edge kinds, and they are different claims:

| edge | drawn | means |
| --- | --- | --- |
| ownership | thin grey, no head | this parameter belongs to that fit or group |
| link | cyan, arrowhead at the **master** | this parameter follows that one |
| base (*Connect base*) | dashed, dim | these owners are things links can run between |

*Connect base* connects every **owner** — fits *and* registered parameter groups
— not fits only, so a plugin's working model (an ndX selection, a calculator)
appears with the fits it exists to be linked against.

### Refreshing without cost

The tool subscribes to `fit.`/`parameter.` events, which during a fit arrive once
per iteration. Answering each one meant re-running a layout algorithm hundreds of
times for a graph whose shape never changed. Now the events are coalesced into
one wake-up (`REFRESH_DEBOUNCE_MS`), the rebuild is skipped entirely while the
window is hidden, and the layout only re-runs when a **structure signature**
(node names, node kinds, edges) differs from what is drawn — values moving is not
a reason to move a node. An explicit **⟳ Refresh** always redraws, and *auto* can
be switched off, in which case the status bar says when the picture is stale.

### Traps this area has already sprung

- **A link edge resolved by name** matched *every* same-named parameter in the
  session, so three fits with a `tau1` turned one link into three arrows. Both
  builders (`plugins/core/globalview/api/graph.py` and the server's
  `server/services/graph.py`) now resolve the master by UUID, with the name only
  as a fallback.
- **`chinet.graph` edges are undirected** and come back renumbered low-to-high,
  so a link's follower → master direction is destroyed by a round trip through
  the graph container. The graph is used for *layout only*; the directed edges
  are carried out of the builder separately.
- **Node ids are not canvas indices.** They diverge the moment `include_fixed`
  drops a node, and an un-reindexed edge then joins two unrelated parameters.
- **A dock layout saved before the window is shown** records every split as
  ~48/48 and, being persisted, beats the authored default on every later launch.
  Saving waits for the first real show.
- **Two graph builders exist** — the plugin's and the server's `graph.build`
  service — and they have already drifted once. Fixes must land in both until
  they are unified; see [known issues](/references/known-issues.md).
