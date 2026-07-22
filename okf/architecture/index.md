# Architecture

* [API Facade](api-facade.md) - `ChiSurfAPI`, the stable local/hybrid/server facade for GUI, macros, plugins, and the console.
* [Action Layer](action-layer.md) - `ActionRegistry`/`ActionDispatcher` mediating all state changes.
* [Runtime Globals](runtime-globals.md) - Legacy process-local globals in `chisurf/__init__.py` and the migration away from them.
* [Server](server.md) - The headless, Qt-free ZMQ/JSON-RPC server under `chisurf/server/`.
* [Plugin System](plugin-system.md) - Manifest-discovered plugins and the plugin infrastructure.
* [GUI Startup](gui-startup.md) - The staged, JSON-declared startup path and the laziness invariants that keep it fast.
* [GUI Layout](gui-layout.md) - **General rule: save space, build compact layouts** (small margins, foldables, hide duplicates when embedded, let plots take the space).
* [MMFDB Metadata Store](mmfdb.md) - SQLite-backed metadata/provenance store generated from mmCIF dictionaries.
