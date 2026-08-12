---
okf_version: "0.1"
---

# ChiSurf Knowledge Bundle

An [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog)
bundle describing the ChiSurf codebase — its architecture, subsystems,
data stores, and developer workflows. Authored for agents and humans who
need durable context on how the repository is organized.

# Agent message board

* [agent-board.md](agent-board.md) - **read this before starting work**. Shared coordination channel for agents across tttrlib and chisurf. The board lives in `tttrlib/okf/agent-board.md` and is symlinked here so both projects see one board. Claim work, post blockers, hand off.

# Concepts

* [Overview](overview.md) - What ChiSurf is and how the source tree is laid out.

# Subdirectories

* [architecture](architecture/index.md) - The hybrid local/server design: API facade, action layer, runtime globals, plugin system, and the MMFDB metadata store.
* [subsystems](subsystems/index.md) - The major code areas: core domain, GUI/AutoForm, headless server, and the plugin ecosystem.
* [plugins](plugins/index.md) - Plugin group pages, documentation standards, worklists, and high-priority plugin profiles.
* [workflows](workflows/index.md) - Developer workflows: environment/build with pixi, and running the test suites.
* [specs](specs/index.md) - Target ("north star") architecture specifications and the cleanup backlog tracking where today's code diverges from them.
* [prds](prds/index.md) - Product-requirement / design notes (PRD-NN) driving current work — one self-contained concept per PRD with persistent number and status; the retired top-level `overhaul/` folder now lives here.
* [usecases](usecases/index.md) - What a ChiSurf user actually does, one workflow per file — discovered and kept current by the headless GUI-tester job, doubling as manual test scripts.
* [reviews](reviews/index.md) - The automated code-review ↔ fix findings queue.
* [references](references/index.md) - Pointers to maintained design docs and roadmap material.
