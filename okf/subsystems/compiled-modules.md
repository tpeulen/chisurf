---
type: Subsystem
title: Compiled Modules
description: C++ extensions in modules/ that must be built before tests.
resource: modules/
tags: [cpp, extensions, build, swig]
timestamp: '2026-07-05T00:00:00Z'
---

# Extensions

The compiled extensions in `modules/` — `chinet`, `ndxplorer`, `clsmview`,
`quest` — plus the burbulator C++ library must be built before the test
suites run. `ndxplorer` and `quest` are git submodules (see `.gitmodules`).

# Building

Run `pixi run build-extensions` if imports of those modules fail. The `test*`
[pixi tasks](/workflows/build-and-env.md) already `depends-on`
`build-extensions`, and so does the `chisurf` launch task, so a plain
`pixi run test` / `pixi run chisurf` builds them first.

The related `tttrlib` package (used for photon/TTTR data) is pinned as a conda
dependency (a portable baseline for CI and fresh installs), but that published
package can lag the local development tree — for example the photon-simulation
subsystem (`tttrlib.SimEngine`, used by the Lifetime-FCS simulator) lands in the
unreleased source before it reaches the conda channel. The `build-tttrlib` task
(part of `build-extensions`) therefore builds the local tttrlib source *over*
the conda package so pixi always uses the most recent build. It is a no-op when
the developer-local, gitignored `modules/tttrlib` symlink (pointing at the
tttrlib checkout) is absent, so CI keeps the conda package. On macOS the task
links the env's `libomp` into the SWIG module (otherwise it loads with a
flat-namespace `___kmpc_barrier` error) and builds in an isolated
`build/tttrlib` tree so it never disturbs the developer's own tttrlib build dir.
See `build_tools/build_tttrlib.py`.

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
