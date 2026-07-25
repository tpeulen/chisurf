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

`tttrlib` (photon/TTTR data) is **built from source and is not a conda
dependency**. The published packages lag the source by enough to be wrong rather
than merely old: they predate the photon-simulation subsystem
(`tttrlib.SimEngine`, used by the Lifetime-FCS simulator) and still carry a
`compute_ics` defect that segfaults any image correlation using a frame lag.
Depending on them meant a fresh environment silently got a broken correlator, so
the dependency was removed rather than overridden.

The `build-tttrlib` task (part of `build-extensions`) is therefore tttrlib's only
provider. It builds the source reached through the **tracked** `modules/tttrlib`
symlink, which points at a sibling checkout — the same arrangement as
`modules/mmfdb`, and CI clones the sibling repo the same way. With no package
behind it the task **fails loudly** when the symlink does not resolve, printing
the clone command, rather than leaving the environment with no tttrlib at all.
On macOS it links the env's `libomp` into the SWIG module (otherwise it loads
with a flat-namespace `___kmpc_barrier` error) and builds in an isolated
`build/tttrlib` tree so it never disturbs the developer's own tttrlib build dir.
See `build_tools/build_tttrlib.py`.

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
