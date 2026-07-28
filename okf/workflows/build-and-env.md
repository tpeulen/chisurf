---
type: Playbook
title: Environment & Build
description: Pixi is the canonical environment/build manager; build compiled extensions before tests.
resource: pixi.toml
tags: [pixi, build, environment]
timestamp: '2026-07-05T00:00:00Z'
---

# Environment

Pixi is the **single** environment/build tool — for dev, tests, and release
packaging alike (all three CI workflows drive `pixi run`). Run everything through
`pixi run <task>`. Python must run inside the project environment — never the
conda `base` env — because the Qt stack and the
[compiled extensions](/subsystems/compiled-modules.md) are not present there.
Python is pinned to 3.12.

There is no separate `environment.yml` — the former `chisurf-env.yaml` was
removed; `pixi.toml` is the one source of truth (PyPI-only deps such as
`latexify-py` live under `[pypi-dependencies]`). Three dependency lists remain,
each for a distinct consumer and kept in sync by cross-referencing comments:
`pixi.toml [dependencies]` (dev env), `pyproject.toml [project.dependencies]`
(installable-wheel metadata, PyPI names), and `rattler-recipe/recipe.yaml` `run:`
(the released conda package). The runtime is numpy 2.x (the canonical pixi env
resolves numpy 2.4), so numpy is unpinned across all three.

A dependency has to earn its place in those three lists. When the whole of what a
package provides is a few lines — a decorator, a `difflib` call, a terminal
progress bar — it is **reimplemented in the tree** and the dependency dropped;
what stays is code we could not sensibly write ourselves (the numerical, Qt and
file-format stacks). Retired so far: the deprecation-decorator package
(`chisurf.core.decorators.deprecated`), the click *did-you-mean* extension
(`chisurf.core.cli_support.DidYouMeanGroup`), the terminal progress bar
(`chisurf.core.progress`), the in-tree graph layer's predecessor
(`chinet.graph`), the Gaussian-HMM package (`chisurf.core.math.hmm`), the
ensemble sampler (`chisurf.core.fitting.ensemble`) and the third-party GUI
toolkit (the `chitable` widget family). Declared-but-never-imported packages went
with them. `test/test_no_retired_dependency_imports.py` fails on any import or
packaging declaration that brings one back — a re-added import would work on a
developer machine, where the package is usually still installed transitively, and
fail only in a packaged install.

The mirror image of an undeclared *dependency* is an undeclared *import*, and it
fails the same way: on a developer machine the package is there transitively, in
a packaged install the plugin does not load. `test/test_declared_dependencies.py`
holds the line — every **module-level** import under `chisurf/` must resolve to a
declared distribution, the standard library, or a sibling project. An import
inside a `try`, a function or an `if` is an optional feature the code is expected
to survive without, and is deliberately not policed. So a package that is genuinely
optional gets one of two homes: a guarded import (`psutil` for the system
watermark), or a `pyproject.toml` extra when a whole file needs it — `api` for the
FRET plugin's HTTP surface, `scrape` for the spectra scrapers, neither installed
by default.

Pixi environments are **detached** from the source tree: with
`detached-environments = true` set in the global pixi config, the multi-GB solved
env lives under the central pixi cache instead of `<repo>/.pixi/envs`, so the repo
folder stays clean. Set it once per machine with
`pixi config set --global detached-environments true`.

# Common commands

```bash
pixi run chisurf            # launch the GUI (builds extensions first, == python -m chisurf)
pixi run build-extensions   # install modules/ (chinet, ndxplorer, quest) + build tttrlib
pixi run lint               # ruff check + ruff format --check
pixi run fmt                # ruff format + ruff check --fix
pixi run typecheck          # mypy chisurf/
```

`build-extensions` also runs `build-tttrlib`. `tttrlib` is **not** a conda
dependency — the published package lags the source by enough to be wrong, not
merely old — so this task is its only provider. It builds the source reached
through the tracked `modules/tttrlib` symlink, which points at a **sibling
checkout** next to the ChiSurf repository (the same arrangement as
`modules/mmfdb`; CI clones it the same way). Clone it once with:

```bash
git clone https://github.com/Fluorescence-Tools/tttrlib.git ../tttrlib
```

The task fails loudly if that source is missing, since there is no package to
fall back on. See [compiled modules](/subsystems/compiled-modules.md).

# Installer bundles

`build_tools/build_installer.py` assembles a slimmed runtime env under `dist/`
and wraps it per platform (macOS `.app` + DMG, Linux AppImage, Windows Inno
Setup). The env is created against a build-time prefix, so the bundle is only
usable elsewhere if every absolute reference to that prefix is removed before
wrapping.

`relocate_scripts(bin_dir, build_prefix)` handles the console scripts:
micromamba and pip write the build prefix into the shebang of `chisurf`,
`csc` and every `csg_*` entry point, in either the plain form
(`#!<prefix>/bin/python3.12`) or setuptools' long-shebang form (`#!/bin/sh`
followed by `'''exec' "<prefix>/bin/python3.12" …`). Both are replaced by an
interpreter resolved from the script's own directory. It runs for the macOS
bundle and the AppImage — AppImages mount at a fresh path on every launch, so
the baked prefix is wrong there too. The `.app` launcher itself invokes
`Contents/bin/python -m chisurf` and was never affected; the entry points on
`PATH` were.

# Installer smoke tests

The `Build and Release` workflow (`.github/workflows/pixi-ci.yml`) builds the
conda package + installer through a single pixi step
(`pixi run -e build build-installer`, which chains `build-pkg` → rattler-build →
`build-extensions`), then launches each freshly built installable app on its
runner OS and asserts it reaches the main window. A headless self-test mode in `chisurf/gui/__init__.py` drives this: when
`CHISURF_SMOKE_TEST` is truthy, `get_app()` skips the interactive MMFDB login,
lets the window paint, then (after `CHISURF_SMOKE_DELAY_MS`, default 5000 ms)
optionally writes the `CHISURF_SMOKE_SENTINEL` file and quits so the process
exits 0. macOS launches the `.app` bundle with `open -W` and confirms via the
sentinel (`open` does not propagate the app exit code); Linux runs the AppImage
under `xvfb-run` and Windows silently installs the Inno Setup `.exe` then runs
the installed `python.exe -m chisurf` — both also rely on the exit code. Each has
a watchdog so a hung launch fails the job fast instead of hitting the job
timeout.

# Style

ruff (line length 100, py310 target, NumPy-style docstrings) and mypy.

# Citations

[1] [Project instructions (CLAUDE.md)](/references/claude-md.md)
