---
type: Development Note
title: ChiSurf Plugin Architecture & Migration Plan
description: Every plugin MUST have a manifest.json in its root package directory.
tags: [development, plugins, plugin, architecture]
audience: developer
---

# ChiSurf Plugin Architecture & Migration Plan

## 1. Current State

### What works well

| Area | Status |
|---|---|
| Burst Selection `api/` package | Clean dataclass models, serialization, pure-algorithm core, JSON-safe I/O — the reference template |
| Burst Selection `gui/tool.py` | Migrated GUI that uses `api/` layer (though still imports it directly) |
| ZMQ JSON-RPC server | Working transport, `ServiceDispatcher`, session state, event bus |
| Core "namespace" RPC methods | `dataset.*`, `fit.*`, `parameter.*`, `project.*`, `session.*`, `model.*`, `graph.*` |
| Plugin discovery | `iter_plugins()` walks `__path__` and parses AST for `name`/`cli_entrypoint` — works well |
| CLI registration | `chisurf/core/cli.py` (since removed) reads `manifest.json` `entrypoints.cli` first and falls back to the AST `cli_entrypoint`; both are scanned without importing plugin code |

### What needs to change

| Problem | Detail |
|---|---|
| **No manifest schema** | Plugins declare `name`, `cli_entrypoint` in `__init__.py` as bare Python variables, not JSON. RPC methods, event topics, state namespaces, schemas are all implicit or duplicated across files. |
| **Manual RPC registration** | `server/app.py` hardcodes `register_burst_selection_services(dispatcher)`. Every new plugin would need the same treatment. Methods are not auto-discoverable. |
| **`SessionState` is not JSON-safe** | Stores real Python objects (`datasets`, `fits` lists). `to_dict()` only returns counts/names, not full state. No plugin namespacing. |
| **GUI imports core directly** | `gui/tool.py` calls `analyze_file()` directly from `api/selection.py`. No client/server boundary. Even with `--no-deps`, this prevents web frontend. |
| **Method naming inconsistency** | Resolved for core methods: `server_methods.json` registers dotted names only (`dataset.list`, `fit.run`); the flat snake_case aliases are gone. Burst Selection uses `burst_selection.analyze_files` (dotted) — consistent with the convention but still not auto-registered. |
| **No state patches** | GUI has no standardized way to learn about state changes. Events exist but aren't used for state sync. |
| **No schema validation** | RPC method params/results have no formal schemas. `METHOD_SCHEMAS` is incomplete. |
| **Duplicate legacy code paths** | `gui/legacy/burst_selector.py` (962 lines) is a full second implementation. |
| **No standard job lifecycle** | Burst Selection's long-running jobs return JSON-RPC results directly. No job_id/progress/cancel contract. |
| **Plugin template is Qt-only** | The cookiecutter template only generates `__init__.py` with `name`, no `manifest.json`, no `api/`, no `backend/`, no RPC methods. |

---

## 2. Target Architecture

### 2.1 Layer diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        GUI (Frontend)                           │
│  PyQt MainWindow, console, Macros, WebUI (future)               │
│                                                                 │
│  Rules:                                                         │
│  • NEVER import api/ or core/ modules for computation           │
│  • NEVER own mutable state — only view state                    │
│  • Communication only through PluginClient (ZMQ JSON-RPC)       │
│  • Existing widgets can be view components but must sync        │
│    through plugin client, not direct function calls             │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        │ ZMQ JSON-RPC (REQ/REP) + Events (PUB/SUB)
                        │
┌───────────────────────▼─────────────────────────────────────────┐
│              TRANSPORT LAYER                                    │
│  ZmqServer / ZmqClient                                          │
│  InProcessClient (dev tests only, same API)                     │
└───────────────────────┬─────────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────────┐
│              BACKEND / SERVER SERVICES                          │
│                                                                 │
│  ServiceDispatcher   ─── routes method → handler                │
│  SessionState        ─── JSON-serializable state (plugin-       │
│                          namespaced, object store for non-JSON)  │
│  JobManager          ─── long-running job lifecycle             │
│  EventBus            ─── standardized state-change events       │
│                                                                 │
│  Per-plugin: backend/services.py  (thin RPC adapters)           │
│  Per-plugin: backend/state.py     (plugin state namespace)      │
│  Per-plugin: backend/jobs.py      (job orchestration)           │
│                                                                 │
│  Rules:                                                         │
│  • NEVER import Qt                                              │
│  • NEVER import gui/ modules                                    │
│  • Accept/return JSON-safe dicts                                │
│  • State only modified through validated state patches          │
└───────────────────────┬─────────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────────┐
│              API LAYER (Public Contract)                        │
│                                                                 │
│  api/models.py       ─── JSON-serializable dataclasses (DTOs)   │
│  api/schemas.py      ─── JSON Schema definitions                │
│  api/serialization   ─── to_jsonable / from_jsonable            │
│                                                                 │
│  Rules:                                                         │
│  • NEVER import Qt, ZMQ, backend, server                       │
│  • Pure Python, dataclasses, Enums                             │
│  • Every DTO is JSON-roundtrippable                            │
│  • Every DTO has a JSON schema                                 │
└───────────────────────┬─────────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────────┐
│              CORE LAYER (Algorithms)                            │
│                                                                 │
│  core/selection.py   ─── Pure computation functions             │
│  core/features.py    ─── Feature extraction, GMM               │
│  core/io.py          ─── File I/O (no network)                 │
│  core/stats.py       ─── Statistics                            │
│                                                                 │
│  Rules:                                                         │
│  • NEVER import Qt, ZMQ, backend, server                       │
│  • Pure deterministic functions                                 │
│  • Accept/return API dataclasses (not raw dicts)               │
│  • Return values are JSON-serializable via API layer           │
│  • No global state                                              │
│  • Fully testable with real data, no infrastructure            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Data flow

```
User clicks "Analyze"
       │
       ▼
GUI: tool.py
   └─ calls self.client.call("burst_selection.jobs.analyze_files", params)
       │
       ▼
ZMQ JSON-RPC REQ
       │
       ▼
Server: ServiceDispatcher.dispatch("burst_selection.jobs.analyze_files", params)
   └─ calls burst_selection.backend.services.analyze_files(params, state, event_bus)
       │
       ├─ deserialize params → AnalysisRequest (API model)
       ├─ create job → job_id returned immediately
       ├─ spawn worker thread
       │    └─ for each file:
       │         ├─ core/io.py: load_tttr(path)
       │         ├─ core/selection.py: apply_photon_filters(...), find_bursts(...)
       │         ├─ core/io.py: write_bur(df, path)
       │         ├─ event_bus.publish("burst_selection.jobs.progress", {...})
       │    └─ state.patch("burst_selection", {"last_job": job_id, ...})
       └─ returns {"ok": True, "job_id": ..., "state_patch": {...}}
       │
       ▼
GUI receives response
   ├─ applies state_patch to local view
   └─ subscribes to burst_selection.jobs.* events for progress/completion
```

---

## 3. Plugin Manifest Standard

### 3.1 `manifest.json` (source of truth)

Every plugin MUST have a `manifest.json` in its root package directory. This replaces the current pattern of declaring `name`, `cli_entrypoint` etc. as Python variables parsed via AST.

```text
{
  "id": "burst_selection",
  "version": "2.0.0",
  "display_name": "Spectroscopy:Single-Molecule:Burst Selection",
  "description": "Burst selection and FRET analysis for single-molecule fluorescence data.",
  "authors": ["Thomas-Otavio Peulen"],
  "categories": ["Spectroscopy", "Single-Molecule"],
  "icon": "icon.png",

  "state_namespace": "burst_selection",
  "state_schema": {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
      "selected_files": {"type": "array", "items": {"type": "string"}},
      "last_job_id": {"type": ["string", "null"]},
      "settings": {"type": "object"}
    }
  },
  "statefulness": {
    "enabled": true,
    "window": {
      "enabled": true,
      "settings_key": null
    }
  },

  "entrypoints": {
    "gui": "chisurf.plugins.burst.burst_selection.gui.tool:BurstSelectionTool",
    "cli": "burst-selection=chisurf.plugins.burst.burst_selection.cli:cli",
    "services": "chisurf.plugins.burst.burst_selection.backend.services:register_services"
  },

  "rpc_methods": [
    {
      "name": "burst_selection.jobs.analyze_files",
      "summary": "Run burst selection analysis over TTTR files.",
      "description": "Detects bursts in the given TTTR files with the configured burst-search settings and writes a .bur result per file. Longer help text: UIs surface it inline — AutoForm.from_rpc_method() maps it (and each parameter's JSON-Schema 'description') to Qt tooltips.",
      "params_schema": {"$ref": "schemas/burst_selection.json#/definitions/AnalyzeFilesParams"},
      "result_schema": {"$ref": "schemas/burst_selection.json#/definitions/AnalyzeFilesResult"},
      "long_running": true,
      "cancelable": true,
      "events": [
        "burst_selection.jobs.progress",
        "burst_selection.jobs.completed",
        "burst_selection.jobs.failed",
        "burst_selection.jobs.cancelled"
      ]
    },
    {
      "name": "burst_selection.results.inspect_bur",
      "summary": "Inspect a saved ChiSurf .bur file.",
      "params_schema": {...},
      "result_schema": {...},
      "long_running": false,
      "cancelable": false
    },
    {
      "name": "burst_selection.gmm.fit",
      "summary": "Fit a GMM to features extracted from a .bur file.",
      "params_schema": {...},
      "result_schema": {...},
      "long_running": false,
      "cancelable": false
    }
  ],

  "events": [
    {
      "topic": "burst_selection.state.*",
      "description": "State patch events for burst selection plugin"
    }
  ]
}
```

When `statefulness.enabled` is `true`, the GUI entrypoint should persist its last window geometry and dock state. `statefulness.window.enabled` defaults to `true`; `settings_key` defaults to `state_namespace`, then `id`.

Global plugin settings can override this behavior through `plugins.statefulness.mode`:
- `plugin_default` lets each manifest decide.
- `enabled` forces window-state persistence for all plugins.
- `disabled` disables plugin window-state persistence globally.

Per-plugin overrides are stored in `plugins.statefulness.per_plugin` and can be edited in the Plugin Manager. A checked per-plugin state means force persistence, unchecked means force no persistence, and the partial/indeterminate state means use the global mode.

### 3.1.1 Maturity flags

A manifest declares how far a tool can be trusted, and the GUI surfaces that
declaration — the flag is written once, in the manifest, never in the hosts that
embed the tool:

| Key | Message key | Surfaced as |
|-----|-------------|-------------|
| `"experimental": true` | `experimental_message` | red banner above the panel, `⚠️` after the navigation entry and after the ribbon entry |
| `"deprecated": true` | `deprecation_message` | amber banner above the panel, `⛔` after the navigation entry and after the ribbon entry |

A tool may carry both; the deprecation banner is drawn first. Without a message
the banner falls back to a generic wording built from the tool name.

The flags reach a host by two routes, and both read the same table
(`chisurf.gui.widgets.navigation.MATURITY_FLAGS`), so a tool is marked the same
way wherever it is opened from:

- **Ribbon entry.** Plugin discovery carries `experimental` / `deprecated` and
  their messages in every record (`chisurf.plugins.iter_plugins()`), so the
  ribbon appends the marker to the button label and prepends the warning to its
  tooltip, above the description.
- **Navigation panel.** A shell built on `NavigationPanelTool` picks the flags up
  by naming the tool's manifest in the panel definition —
  `"manifest": "<path under chisurf/plugins>"` — and passing the panels through
  `apply_manifest_flags()` (a `panels.json` entry may carry the same key;
  `load_panels_json()` applies the flags itself).

Hosts that need the presentation without a panel use
`maturity_markers()` / `maturity_warnings()` from the same module.

### 3.1.2 Demo plugins

`"demo": true` marks a plugin as a demonstration rather than something the
application is for — the built-in games are the only ones in the tree. Unlike a
maturity flag it carries no banner: plugin discovery
(`chisurf.plugins.iter_plugins()`) turns it into `menu_hidden` unless the
`plugins.show_demo_plugins` setting is on, so the demo is absent from the
ribbon, the plugin menu and the ribbon categories at once rather than being
filtered again in each of them. The Plugin Manager and the help browser do not
filter on `menu_hidden`, so a demo stays inspectable and installable there.

Discovery is cached, so flipping the setting takes effect after
`chisurf.plugins.invalidate_plugin_cache()` or a restart.

### 3.1.3 Declaring what a plugin depends on

Plugins depend on each other, and the manifest is where that is written down.
Three fields, easily confused:

| field | means | affects load order |
|---|---|---|
| `dependencies` | **external** distributions — PyPI/conda names, e.g. `{"ruff": ">=0.4"}` | no |
| `requires` | **sibling plugins imported at module import time**, `{plugin_id: specifier}` | **yes** |
| `optional_requires` | sibling plugins reached only after boot — a function-local import, a `try`-guarded import, or a `"chisurf.plugins.x:Class"` string resolved on click | no |

A specifier is either `"*"` (any version — it just has to be installed) or a
PEP 440 bound such as `">=2.0"`. Write `"*"` unless the plugin genuinely needs a
newer sibling: a bound invented without a reason is maintenance on every version
bump and asserts nothing.

```json
{
  "requires": {"mle_common": "*"},
  "optional_requires": {"ndxplorer": "*", "spot_finder": "*"}
}
```

Put an edge in `requires` only if the import runs when the module is imported.
If it runs inside a function, or inside `try`/`except`, it belongs in
`optional_requires` — that distinction is what keeps the dependency graph
acyclic, since several plugin pairs reference each other in opposite directions.

Two more fields exist for packages that are not ordinary tools:

- `"library": true` — shared code other plugins import, not something a user
  runs (`imaging_common`, `mle_common`). It carries an id so edges can name it,
  offers no entrypoint, and never reaches a menu.
- `"entrypoints": {"script": "wizard.py"}` — for the older tools the menu
  *executes* rather than imports. Without it such a plugin is treated as
  CLI-only and disappears from every menu.

You do not have to work the edges out by hand:

```bash
python -c "from chisurf.core.plugin.edges import collect_edges; \
  [print(e.source, '->', e.target, e.kind, e.where) for e in collect_edges()]"
```

`test/test_plugin_dependencies.py` compares that derived graph against the
manifests and fails on any disagreement, in either direction — an undeclared
coupling *or* a declaration the code no longer backs up.

At startup `chisurf/core/plugin/dependencies.py` resolves `requires` into a load
order so a dependency is registered before its dependants. It never raises: a
missing target, an unsatisfied bound or a cycle each produce a warning and the
application still starts. Problems are listed per plugin in the **Plugin Check**
tool.

### 3.2 Schema files

Plugin schemas live under `schemas/` and are JSON Schema draft-07 files referenced from the manifest:

```
burst_selection/
  manifest.json
  schemas/
    burst_selection.json    # contains all definitions
    common.json             # shared types (reusable across plugins)
```

### 3.3 Backward compatibility

`PluginRegistry` reads `manifest.json` first and falls back to AST parsing of `__init__.py` only if no manifest exists. That fallback reads exactly four module-level variables — `name`, `cli_entrypoint`, `cli_only`, `menu_hidden` — plus the module docstring as the description; no deprecation warning is emitted for using them.

The maturity flags (`experimental` / `deprecated`) are **manifest-only**: a module-level `deprecated` / `deprecation_message` in `__init__.py` is read by nothing and surfaced nowhere, so a manifest-less plugin cannot declare itself deprecated. Declare the flag in `manifest.json`, and let the module read the wording back from the manifest (`load_manifest`) rather than restating it.

---

## 4. Standard Plugin Directory Layout

```text
chisurf/plugins/<plugin_id>/
  manifest.json                  ← PLUGIN MANIFEST (source of truth)
  __init__.py                    ← shallow imports, re-exports for backward compat
  icon.png                       ← plugin icon
  icon.svg                       ← vector source (optional)

  api/
    __init__.py                  ← public re-exports
    models.py                    ← DTO dataclasses
    schemas.py                   ← JSON schemas (or schemas/ dir)
    serialization.py             ← to_jsonable / from_jsonable helpers
    enums.py                     ← shared enums (optional)

  core/
    __init__.py
    selection.py                 ← pure algorithms
    features.py                  ← feature extraction
    io.py                        ← file I/O
    stats.py                     ← statistics

  backend/
    __init__.py
    services.py                  ← RPC handler registration
    state.py                     ← plugin state DTO + state_patch helpers
    jobs.py                      ← long-running job orchestration

  server/
    __init__.py                  ← compatibility re-exports for old imports
    client.py                    ← ZMQ client wrapper (optional, for tests)

  gui/
    __init__.py
    tool.py                      ← main GUI widget (uses PluginClient)
    help.md                      ← REQUIRED: what the ? button shows
    guide.json                   ← REQUIRED: the guided tour (Guide button)
    <plugin>.view.json           ← AutoForm view spec (when the tool is one)
    dialogs/                     ← sub-dialogs
    assets/                      ← UI files, icons

  cli/
    __init__.py
    main.py                      ← Click CLI

  tests/
    test_api.py
    test_core.py
    test_backend.py
    test_gui.py
    test_contract.py             ← RPC contract tests
    data/                        ← test data files

  docs/
    README.md
```

### `help.md` and `guide.json` are not optional

A modern plugin ships both, beside the module its `entrypoints.gui` names. They
answer different questions — `?` says what a control *means*, **Guide** says
which control to touch **first** — and a dense panel of well-documented settings
is unusable without the second.

Neither needs any code. `ChisurfDockTool` and `NavigationPanelTool` both mix in
`HelpGuideMixin` and look for the two files themselves, so the buttons appear the
moment the files exist. A tool built on a plain `QWidget`/`QDialog` makes one
call instead:

```python
from chisurf.gui.widgets.tools.help_guide import attach_help_and_guide

attach_help_and_guide(self, self.toolbar, title="My tool — help", model=self)
```

A tour is a list of steps, each pointing at one **real** widget — by view-spec
`attr`/`key`/`title`, by toolbar `action`, by `objectName` (`name`), by dock
`tab`, or by a navigation-shell `panel`. Steps that ask the user to do something
carry `"await"`, and the tour never presses a button on the user's behalf:
someone who watched a button being pressed has not learned where it is.

A step whose target does not resolve is **shown centred rather than skipped**, so
a wrong target never fails loudly — it quietly turns the tour into a slideshow.
Always walk a new tour headlessly and confirm every step resolves.
{src}`test/test_plugin_help_guide_seam.py` enforces all of this against a **shrinking**
allow-list; adding your plugin to that list is never the fix.

---

## 5. State Contract

### 5.1 Server-side `SessionState`

`SessionState` stores only JSON-serializable data. Non-serializable objects (TTTR readers, NumPy arrays) live in a private `_object_store: dict[str, Any]` referenced by UID:

```python
@dataclass
class SessionState:
    # JSON-serializable public state
    datasets: list[dict]           # DatasetSummary DTOs
    fits: list[dict]               # FitSummary DTOs
    experiments: dict[str, Any]    # JSON-safe experiment configs
    current_experiment: str | None
    current_setup: str | None
    current_fit_uid: str | None

    # Plugin-namespaced state (JSON-serializable)
    plugins: dict[str, Any]        # e.g. {"burst_selection": {...}, "fcs": {...}}

    # Private object store (not JSON-serialized)
    _object_store: dict[str, Any] = field(default_factory=dict, repr=False)
```

### 5.2 Plugin state namespace

Each plugin owns a subtree under `state.plugins[plugin_id]`. State is modified only through state patches:

```json
{
  "burst_selection": {
    "selected_files": ["/data/m000.spc"],
    "last_job_id": "job_abc123",
    "settings": {
      "photon_filter": {
        "channels": [0, 1],
        "filter_active": true
      },
      "burst_detection": {
        "min_photons": 60
      }
    }
  }
}
```

### 5.3 State patch

Every RPC response that modifies state includes a `state_patch` dict:

```json
{
  "ok": true,
  "result": {
    "job_id": "job_abc123"
  },
  "state_patch": {
    "burst_selection": {
      "last_job_id": "job_abc123",
      "selected_files": ["/data/m000.spc"]
    }
  }
}
```

GUI updates from `state_patch` — never from direct mutation.

### 5.4 State change events

Events published when state changes:

```
burst_selection.state.changed
payload: { "state_patch": {...}, "timestamp": "..." }
```

---

## 6. RPC Contract

### 6.1 Method naming

```
<plugin_id>.<scope>.<action>

Examples:
  burst_selection.jobs.analyze_files
  burst_selection.results.inspect_bur
  burst_selection.gmm.fit
  fcs.acf.compute
  fcs.fcs2d.compute
  detector.setups.list
  detector.setups.save
  lifetime.mle.run
  lifetime.irf.fit
```

No snake_case legacy names in new code. Old names kept as deprecated aliases during migration.

### 6.2 Request envelope (JSON-RPC 2.0)

```json
{
  "jsonrpc": "2.0",
  "method": "burst_selection.jobs.analyze_files",
  "params": {
    "files": ["/data/m000.spc"],
    "settings": {
      "photon_filter": {
        "channels": [0, 1, 8, 9],
        "filter_active": true
      }
    }
  },
  "id": 42
}
```

### 6.3 Success response (immediate)

```json
{
  "jsonrpc": "2.0",
  "result": {
    "ok": true,
    "result": {
      "job_id": "job_abc123"
    },
    "state_patch": {
      "burst_selection": {
        "last_job_id": "job_abc123"
      }
    }
  },
  "id": 42
}
```

### 6.4 Success response (completed work)

```text
{
  "jsonrpc": "2.0",
  "result": {
    "ok": true,
    "result": {
      "analysis_summary": {
        "n_files": 1,
        "n_bursts": 120,
        "output_files": ["/output/m000.bur"]
      }
    },
    "state_patch": {
      "burst_selection": {
        "last_job_id": null,
        "last_result_summary": {...}
      }
    }
  },
  "id": 42
}
```

### 6.5 Error response

```json
{
  "jsonrpc": "2.0",
  "result": {
    "ok": false,
    "error": {
      "code": "INVALID_INPUT",
      "message": "channels must be a list of integers",
      "data": {
        "field": "settings.photon_filter.channels"
      }
    }
  },
  "id": 42
}
```

### 6.6 Job lifecycle events (PUB socket)

Standard payload:

```json
{
  "topic": "burst_selection.jobs.abc123.progress",
  "payload": {
    "job_id": "abc123",
    "plugin_id": "burst_selection",
    "phase": "processing",
    "progress": 0.45,
    "current": 45,
    "total": 100,
    "unit": "files",
    "message": "Processing m000.spc"
  }
}
```

Standard event topics:

```
<plugin_id>.jobs.<job_id>.created
<plugin_id>.jobs.<job_id>.progress
<plugin_id>.jobs.<job_id>.completed
<plugin_id>.jobs.<job_id>.failed
<plugin_id>.jobs.<job_id>.cancelled
```

---

## 7. PluginClient Interface

```python
class PluginClient(Protocol):
    """The only way GUI talks to backend."""

    def call(
        self,
        method: str,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        """Execute an RPC method and return the parsed response.

        Raises RemoteError on transport/protocol failures.
        """
        ...

    def subscribe(
        self,
        topic: str,
        callback: Callable[[dict], None],
    ) -> str:
        """Subscribe to event topic glob (e.g. 'burst_selection.jobs.*').

        Returns a subscription token for unsubscribe().
        """
        ...

    def unsubscribe(self, token: str) -> None:
        """Remove a subscription."""
        ...

    @property
    def is_connected(self) -> bool:
        """Whether the transport is connected to a server."""
        ...
```

### 7.1 ZmqClient (production)

Uses ZMQ REQ/REP for `call()` and ZMQ SUB for events. Connects to `ChiSurfServer`.

### 7.2 InProcessClient (development/tests only)

Wraps `ServiceDispatcher` directly — no network. Same API, same semantics. Used for plugin development and contract tests. Must be explicitly enabled; never used in production.

### 7.3 What GUI must NOT do

```python
# ❌ BAD: GUI imports core directly
from chisurf.plugins.burst.burst_selection.api.selection import analyze_file
result = analyze_file(path, settings)

# ❌ BAD: GUI mutates state directly
state.plugins["burst_selection"]["selected_files"] = [...]

# ✅ GOOD: GUI calls through PluginClient
client.call("burst_selection.jobs.analyze_files", {"files": [...], "settings": ...})
```

---

## 8. PluginRegistry

A new `PluginRegistry` replaces the ad-hoc AST-parsing discovery:

```python
class PluginRegistry:
    """Loads plugins from manifest.json files and provides discovery + registration."""

    def discover(self) -> list[PluginManifest]:
        """Walk all plugin directories, load manifest.json, return manifests."""

    def register_services(self, dispatcher: ServiceDispatcher) -> None:
        """Call each plugin's entrypoints.services(dispatcher)."""

    def register_cli(self, main_group: click.Group) -> None:
        """Attach each plugin's CLI subcommand."""

    def register_gui(self, menu: QMenu) -> None:
        """Build plugin menu from manifests."""
```

The registry lives at {src}`chisurf/core/plugin/registry.py`. It reads manifest.json (preferred) or falls back to AST parsing of `__init__.py` for backward compatibility.

---

## 9. Migration Phases

### Phase 0 — Foundation (docs + contracts)

1. [x] Write this architecture plan
2. [ ] Create {src}`chisurf/core/plugin/manifest.py` with `PluginManifest` dataclass + schema validation
3. [ ] Create {src}`chisurf/core/plugin/registry.py` with `PluginRegistry`
4. [ ] Add `manifest.json` validation tests
5. [ ] Add `PluginClient` protocol and `InProcessClient` implementation
6. [ ] Add state patch helpers to `SessionState`

### Phase 1 — Burst Selection cleanup (pilot)

1. [ ] Add `manifest.json` to burst_selection (remove `name`, `cli_entrypoint` from `__init__.py` once manifest is read)
2. [ ] Move `server/` → `backend/` (keep `server/` as compat re-export)
3. [ ] Add `backend/services.py` (thin RPC adapters using `ServiceResult`)
4. [ ] Add `backend/state.py` (plugin state DTO)
5. [ ] Add `backend/jobs.py` (job lifecycle)
6. [ ] Add `PluginClient` usage in `gui/tool.py` — GUI calls through client, not direct imports
7. [ ] Add `InProcessClient` for tests
8. [ ] Add contract tests (`test_contract.py`)
9. [ ] Remove legacy git history: `gui/legacy/burst_selector.py`, old `wizard.py` dependencies
10. [ ] Clean up `server_methods.json` — burst selection methods should be registered via manifest, not hardcoded

### Phase 2 — PluginRegistry + auto-registration

1. [ ] Register all plugins through `PluginRegistry` (not `app.py` manual imports)
2. [x] `ChiSurfServer.__init__` calls `registry.register_services(dispatcher)`
3. [x] CLI discovery reads `manifest.json` — **but not via `registry.register_cli`**
   (see below)
4. [ ] GUI menu builds from `registry.register_gui(menu)`
5. [x] Manifest is the primary discovery path for the CLI; AST parsing of
   `__init__.py` remains the documented fallback

**Why the CLI does not call `registry.register_cli`.** That method imports every
plugin's CLI object to attach it to the Click group, which would make `csc --help`
import the whole plugin tree — Qt, tttrlib and all. `chisurf/core/cli.py` (since removed) instead
reads `entrypoints.cli` during the same filesystem+AST scan it already performs,
registers a thin forwarding command per plugin, and imports the target module only
when that command is actually invoked. `PluginRegistry.register_cli` remains for
in-process callers that have already paid the import cost (it is what the registry
unit tests exercise); it is not the production path.

The same trade-off applies to `register_gui`: the navigation menus are built from
manifest metadata alone, without importing plugin code, so item 4 stays open by
design rather than by neglect.

**Mistyped subcommands.** A plugin CLI that is a group declares
`cls=DidYouMeanGroup`:

```python
from chisurf.core.cli.support import DidYouMeanGroup

@click.group(cls=DidYouMeanGroup)
def cli():
    """Lifetime fitter command-line interface."""
```

`csc` itself inherits it (`PluginCLI`), so `csc burst-backgroud` lists the
closest registered plugin commands instead of only saying the command does not
exist. The class is `difflib.get_close_matches` over the group's own command
names — it replaces the `click-didyoumean` package, and the three tools that
previously reached for the same feature by monkey-patching `click.Context.fail`
with a method click does not have (turning every usage error in those tools into
an `AttributeError`).

### Phase 3 — State serialization

1. [ ] Make `SessionState.datasets` and `.fits` hold JSON-safe dicts (DTOs) only
2. [ ] Move live objects to `_object_store`
3. [ ] Add plugin namespace support to `state.plugins`
4. [ ] Add state patch machinery (apply patches, emit events)
5. [ ] `to_dict()` serializes full state (not just counts)

### Phase 4 — Other plugin migrations

Apply the burst_selection pattern to each plugin in priority order:

1. **Detector definition** (`setup_channel_definition`) — list/validate/save detector setups
2. **FCS** — compute ACF/CCF, fit, export
3. **Lifetime MLE** — run fit with MLE estimator
4. **PCH** — photon counting histogram analysis
5. **Kappa2 distribution** — orientation factor analysis
6. **Quenching estimator (QuEst)** — diffusion simulation
7. **Remaining plugins** — calculator, misc, traj, tttr, etc.

Each migration follows the same checklist:

- [ ] Add `manifest.json`
- [ ] Create `api/models.py` with DTOs
- [ ] Create `core/` with pure algorithms
- [ ] Create `backend/services.py` with RPC handlers
- [ ] Create `gui/tool.py` using `PluginClient`
- [ ] Update `cli/main.py` to use core
- [ ] Add contract tests
- [ ] Remove direct core imports from GUI

### Phase 5 — WebUI

Once all GUI interactions go through `PluginClient`:

1. [ ] Build web UI prototype for one plugin (burst_selection)
2. [ ] Reuse same RPC contract
3. [ ] WebSocket transport adapter (optional, adds to ZMQ)
4. [ ] Electron shell (optional, for standalone desktop distribution)

---

## 10. Cleanup Checklist Per Plugin

When migrating a plugin, verify:

- [ ] `manifest.json` exists and is valid
- [ ] `__init__.py` only re-exports public symbols (no Qt imports, no logic)
- [ ] `api/models.py` has all DTOs with `to_dict()`/`from_dict()`
- [ ] `api/serialization.py` has roundtrip serialization
- [ ] `core/` has no Qt/ZMQ imports
- [ ] `backend/services.py` registers RPC handlers with `ServiceDispatcher`
- [ ] `backend/state.py` defines plugin state namespace
- [ ] `backend/jobs.py` handles long-running jobs
- [ ] `gui/tool.py` uses `PluginClient` (not direct imports)
- [ ] `cli/main.py` uses core (can import directly — CLI is local-only)
- [ ] Contract tests cover all RPC methods
- [ ] `server_methods.json` is updated (or methods registered automatically via manifest)
- [ ] `server/app.py` no longer imports plugin directly

---

## 11. Acceptance Criteria

The migration is complete when:

1. **No plugin GUI imports `api/` or `core/` directly** — all communication goes through ZMQ (or `InProcessClient` in dev mode)
2. **Every plugin has a `manifest.json`** as its sole metadata source
3. **All RPC methods are registered automatically** from manifests, not hardcoded in `server/app.py`
4. **`SessionState` is fully JSON-serializable** — `to_dict()` roundtrips through JSON without loss
5. **State patches are the only way GUI learns about state changes**
6. **Every plugin has contract tests** that prove the RPC boundary
7. **WebUI can be built** without changing the backend — the same RPC contract serves both desktop and web
8. **`test/server/` passes** and `import chisurf.server` succeeds without Qt
