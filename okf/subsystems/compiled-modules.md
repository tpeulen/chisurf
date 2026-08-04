---
type: Subsystem
title: Compiled Modules
description: The sibling packages under modules/ and the build tasks that install them.
resource: modules/
tags: [cpp, extensions, build, swig]
timestamp: '2026-07-05T00:00:00Z'
---

# What lives in `modules/`

| Entry | Kind | How it is provided |
|-------|------|--------------------|
| `tttrlib` | C++/SWIG, **compiled** | `build-tttrlib`, from the source behind a tracked symlink to a sibling checkout |
| `chinet` | pure Python (runtime, schema, [graph layer](/subsystems/graph.md)) | `build-chinet`, editable install |
| `ndxplorer` | pure Python | `build-ndxplorer`, editable install; git submodule (see `.gitmodules`) |
| `quest` | pure Python | `build-quest`, editable install; git submodule |
| `mmfdb` | pure Python | symlink to a sibling checkout; **not** installed by `build-extensions` |
| `imp-tricks` | external modelling framework | symlink to a sibling checkout; **not** installed by `build-extensions` |

`tttrlib` is the only entry that is compiled — the other three that
`build-extensions` installs are plain editable installs. ChiSurf itself compiles
**nothing**: its own C++ was the burbulator simulator beside the acquisition
plugin, which is [retired](../references/burbulator-simulator.md), so `setup.py`
now only freezes the version string.

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
The build needs nothing beyond the environment prefix. It used to inject
macOS `libomp` linker flags, because tttrlib's Python extension compiled with
OpenMP but never linked it — the module's flat-namespace flag let the missing
symbols through, so it built fine and failed at *import* with
`___kmpc_barrier`. That is fixed in tttrlib (the extension now links
`OpenMP::OpenMP_CXX`, as the R and Java modules always did), so a plain
`pip install` of the source produces an importable module. The task still
builds in an isolated `build/tttrlib` tree so it never disturbs the
developer's own tttrlib build dir. See `build_tools/build_tttrlib.py`.

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
