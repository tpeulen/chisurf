# Architecture

* [The compute/display line](compute-display-line.md) - **The standing rule: computation stays in bff/tttrlib and the data stay with it; only what a human looks at crosses into Python.** The decision procedure, where it is enforced, and the measured distance from it today.
* [Declarative analysis definitions](declarative-analysis-definitions.md) - **General rule: what an analysis computes — inputs, outputs, feature sets — is declared in a settings file beside the code, never hardcoded**, so schemas drift without code changes; one flat declaration per analysis, no framework layers.

* [API Facade](api-facade.md) - `ChiSurfAPI`, the stable local/hybrid/server facade for GUI, macros, plugins, and the console.
* [Action Layer](action-layer.md) - `ActionRegistry`/`ActionDispatcher` mediating all state changes.
* [Runtime Globals](runtime-globals.md) - Legacy process-local globals in `chisurf/__init__.py` and the migration away from them.
* [Server](server.md) - The headless, Qt-free ZMQ/JSON-RPC server under `chisurf/server/`.
* [Plugin System](plugin-system.md) - Manifest-discovered plugins and the plugin infrastructure.
* [GUI Startup](gui-startup.md) - The staged, JSON-declared startup path and the laziness invariants that keep it fast.
* [GUI Layout](gui-layout.md) - **General rule: save space, build compact layouts** (small margins, foldables, hide duplicates when embedded, let plots take the space).
* [MMFDB Metadata Store](mmfdb.md) - SQLite-backed metadata/provenance store generated from mmCIF dictionaries.
