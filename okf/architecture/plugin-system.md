---
type: Architecture
title: Plugin System
description: Manifest-discovered plugins and the plugin infrastructure under chisurf/core/plugin/.
resource: chisurf/core/plugin/
tags: [plugins, manifest, extensibility]
timestamp: '2026-07-05T00:00:00Z'
---

# Where to pick this up

1. **The two pre-existing failures this change did not touch.** `fps_json_editor`
   and `fret_docking` entrypoints fail to import with `No module named
   'IMP.bff.fret'` -- an environment/migration gap, not a manifest one. Re-derive
   with `pytest "test/plugins/test_all_plugins.py::test_plugin_entrypoints_import[fret]"`.
   They are listed in [known issues](/references/known-issues.md).
2. **The RPC-namespace allow-list is the worklist.** `mmfdb_admin` declares
   `ndxplorer.load_burst_product` and `ndxplorer.record_analysis` -- methods that
   read as `ndxplorer`'s API and would collide the moment `ndxplorer` registers
   its own. Either move them to `ndxplorer` or rename them into a domain
   namespace, then strike the lines from
   `test/plugin_dependency_allowlist.txt`. The end state is an empty file.
3. **Bounds are all `*` today.** Every seeded edge says "must exist"; no real
   PEP 440 bound is in the tree yet. Write one only when a plugin genuinely needs
   a newer sibling -- a bound invented without evidence is maintenance on every
   version bump and asserts nothing.
4. **Three other Kahn sorts exist** (`chisurf/startup/services.py`,
   `chisurf/core/pipeline/model.py`, `chinet.graph.algorithms`). Consolidating
   them was deliberately *not* done here: this resolver needs version bounds, two
   edge classes and non-raising degradation, and `chinet.graph` is only reachable
   through `chinet/__init__.py`, which drags in `base/node/port/schema/session`
   onto the `csc --help` path. Anyone consolidating must measure that import cost
   first.
5. **The plugin manager's own leftovers.** Its `manifest.json` still has no
   `docs/concepts` page or numbered `docs/guides/NN_*.md` (the house rule wants
   both for a substantially changed plugin); only `help.md` + `guide.json` +
   the reference page exist. And `read_module_docstring` is still defined three
   times in the tree (`chisurf/gui/__init__.py`, `chisurf/gui/main.py`, and now
   `plugin_manager/api/records.py`) -- the other two were left alone because
   those files carry another instance's uncommitted work.
6. **The trap when re-deriving the graph.** `collect_edges()` deliberately skips
   `test`/`tests` directories: a test importing the plugin it exercises is not a
   runtime dependency, and counting it invents cycles that do not exist
   (`fret_docking` -> `fps_json_editor` is test-only, and its reverse is a real
   top-level import). Also note nine plugins have a directory name that differs
   from their id, so never infer an id from a path.

# Discovery

Plugins live under `chisurf/plugins/` and are discovered via `manifest.json`
files; the plugin infrastructure lives in `chisurf/core/plugin/`. Migrated
plugins receive a `PluginContext` (API + client + main window) rather than
reaching for [runtime globals](/architecture/runtime-globals.md).

# Scale

The tree ships ~86 plugin manifests, grouped by domain — e.g. `burst/`
(smFRET burst analysis), `fcs/` (correlation), `fluorescence_decay/`
(TCSPC lifetime), `modelling/` (FRET/HydroPro/FPS), and `core/`
(infrastructure tools like `mmfdb_admin`, `setup`, `plugin_manager`,
`user_editor`).

A cookiecutter template for new plugins lives at
`chisurf/plugins/cookiecutter-chisurf-plugin/`.

# Dependencies and boot order

Plugins depend on each other -- shared base classes, hub tools that embed a
dozen panels, backend services that build on a sibling's. Two manifest maps
declare it, both `{plugin_id: specifier}` where the specifier is `*` ("any
version, it just has to be there") or a PEP 440 bound:

- **`requires`** -- the sibling is imported at *module import time*. The target
  must exist, and it constrains load order.
- **`optional_requires`** -- the sibling is reached only after boot: a
  function-local import, a `try`-guarded import, or a
  `"chisurf.plugins.x:Class"` string a hub resolves when the user clicks. Real
  coupling, but it imposes no ordering.

Splitting the two is what makes the graph resolvable. Several plugin pairs point
at each other (`mmfdb_admin` <-> `project_browser`, `fps_json_editor` <->
`fret_docking`), but never twice in the hard direction, so the ordering graph is
acyclic while the full coupling is still recorded.

`dependencies` is a different field and keeps its meaning: **external
distributions** (PyPI/conda names), not plugin ids.

`chisurf/core/plugin/dependencies.py` resolves `requires` into a boot order
(Kahn, ties broken by id so the result is reproducible) and reports what does
not add up: missing targets, unsatisfied bounds, cycles, unknown optional
targets. It **never raises** -- a desktop app must start even when a plugin in
`~/.chisurf/plugins` is wrong, so problems become one warning each and the boot
continues. Enforcement lives in `test/test_plugin_dependencies.py`.

The order is applied at the seams that actually import things:

- `chisurf/plugins/__init__.py` -- where `_PLUGIN_CACHE` is filled, so all nine
  GUI/help/docs consumers agree without touching a single call site;
- `PluginRegistry.discover()` -- so `register_services`, `register_cli`,
  `register_gui` and the operation index inherit it;
- `chisurf/core/cli.py` -- sorted scan, so the first-wins command-name tiebreak
  stops depending on `os.scandir` order.

Menus are *not* reordered: they keep sorting by `(plugin_order, name)`, because
a user expects an alphabetical menu, not a topological one.

`chisurf/core/plugin/edges.py` derives the true graph from the tree -- AST
imports, AST string constants, and JSON string values (`panels.json`,
`view.json`, manifest entrypoints) -- under one rule: a `chisurf.plugins.<...>`
dotted name resolving to another plugin is an edge. That is what the guardrail
test compares the manifests against, so a declaration cannot drift from the code.

# The plugin manager

`chisurf/plugins/core/plugin_manager/` is the panel users see this through, and
it follows the house layering rather than being one widget:

- `api/records.py` -- one `PluginRow` per plugin, built from the discovery
  record alone (it imports no plugin code) and carrying the dependency graph in
  **both** directions. `required_by` is the one that matters in a UI: it names
  what breaks before you switch something off.
- `api/settings_io.py` -- a working copy of the `plugins:` settings block.
  Edits are invisible until `apply()`, and only the keys this tool owns are
  written.
- `api/install.py` -- install from a folder or a `.zip` into
  `~/.chisurf/plugins`, validating the manifest first and refusing archive
  members that escape the destination.
- `api/icons.py` -- the AI icon client, as plain functions over an `IconConfig`.
- `gui/` -- `view_model.py` + `plugins.view.json` rendered by AutoForm, plus a
  toolbar, `guide.json` and `help.md`.

The table is the `data_table` custom section over `ChiTableWidget`, so search,
sort, column-picking and CSV export come for free.

# Discovery cost

`iter_plugins()` walks the whole tree and parses every plugin `__init__.py` and
`manifest.json`, so its result is memoized; mutating the plugin set requires
`invalidate_plugin_cache()`. Menus are built from manifest metadata and on-disk
icons **without importing plugin code** — see
[GUI Startup](/architecture/gui-startup.md) for why both matter.

# Command line

Plugin CLIs reach the `csc` command line through the **manifest**:
`entrypoints.cli` (`"alias=module:attr"`) is the authoritative declaration, read
by `chisurf/core/cli.py` in the same filesystem+AST scan that finds plugin names —
still without importing any plugin. The older module-level `cli_entrypoint`
assignment remains a fallback for plugins without a manifest, and when a plugin
carries both they must agree (a guardrail test enforces it).

Two consequences worth knowing: a manifest whose entry omits the `alias=` prefix
registers under the plugin id instead of being dropped, and a plugin's command is
imported only when it is actually invoked, so a broken plugin CLI cannot slow —
or break — `csc --help`.

# AutoForm

GUI plugins increasingly declare their UI as data — a `*.view.json` scheme
rendered by the AutoForm framework (see the [GUI subsystem](/subsystems/gui-autoform.md))
instead of hand-built Qt widgets.

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
