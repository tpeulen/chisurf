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
(`chisurf.core.progress`), the HTTP client (`chisurf.core.http`, a
``urllib.request`` wrapper for the JSON round trips the model providers and the
plugin registry need), the in-tree graph layer's predecessor
(`chinet.graph`), the Gaussian-HMM package (`chisurf.core.math.hmm`), the
ensemble sampler (`chisurf.core.fitting.ensemble`) and the third-party GUI
toolkit (the `chitable` widget family). Declared-but-never-imported packages went
with them. `test/test_no_retired_dependency_imports.py` fails on any import or
packaging declaration that brings one back — a re-added import would work on a
developer machine, where the package is usually still installed transitively, and
fail only in a packaged install.

**Decide with a solve, not an opinion.** What a dependency costs is its
*transitive* closure, and that is only knowable by asking the solver:
`conda create --dry-run --json --override-channels -c conda-forge -n probe <specs>`
and counting `actions.LINK`, then again without the candidate. Measured
2026-07-28 against the recipe's `run:` list (**301 packages** in total):
`notebook` **59** (the Jupyter server stack; kept — the GUI starts it), `pyarrow-core`
**37** (libarrow's AWS/Azure/GCS/gRPC/ORC stack; kept), `scikit-image` **20**,
`boost-cpp` **8**, `python-docx` 3, `mdtraj` 2, `hdbscan`/`micromamba`/
`boost-histogram` 1, and **`pytables` 0** — mdtraj required it, so it was already
paid for, and swapping it for a different HDF5 binding would only have *added*
packages.

> That last reading is worth keeping as a caution. A dependency measured at
> **0** is not free — it is *masked*, and the number says nothing about what it
> costs once the thing masking it leaves. `mdtraj` was retired
> ([PRD-80](/prds/prd-80.md)) and `pytables` went from 0 to the whole HDF5
> binding, taking `numexpr` with it. Measure the candidate *and* what would
> still hold it if the candidate went.
Two results were counter-intuitive and are the reason for measuring: removing
`boost-cpp` **grew** the closure by 8 net, because its `xz` pin was holding the
solve on a branch where Pillow needs no font/cairo stack; and declaring the eight
runtime packages the tree imports but the recipe had left to arrive transitively
(`pyzmq`, `sqlalchemy`, `numexpr`, `packaging`, `imageio`, `tifffile`,
`imagecodecs`, `pillow`) cost **+2**, since only SQLAlchemy and its greenlet were
genuinely absent. Four of those eight were retired again in August 2026 —
`imageio`, `tifffile` and `imagecodecs` once TIFF I/O moved to the bundled
libtiff already inside the TTTR library (see
[fio/image](../subsystems/image-io.md)), and `numexpr` once its one expression
became a Numba kernel. `pyarrow`/`boost-histogram` went the same month, on
ndxplorer's account rather than ChiSurf's.

**A pin is not a reason to keep a library.** `boost-cpp` was removed on
2026-08-06 *despite* that measurement, which re-solved unchanged: 250 packages
with it, **256 without**. Nothing links it — no `find_package(Boost)`, no
`boost/` include, and no `libboost` load command in any built extension in the
tree or the local modules (the TTTR library says so in its own `CMakeLists.txt`:
"Boost removed - using C++17 standard library"). The +6 is not a service boost
was performing; it is the *shape of the solve* its stale pins were forcing.
Compare the two closures package by package and the mechanism is plain — with
`boost-cpp` the solver is held on an older branch throughout (icu 75 vs 78,
qt-main build 6 vs 8, gstreamer 1.24 vs 1.26, krb5 1.21 vs 1.22, matplotlib
3.10 vs 3.11). The fourteen font/cairo/pango packages have a single owner, and
it is none of the obvious suspects: `gst-plugins-base` **gained a `pango`
dependency between 1.24.11 (no font deps at all) and 1.26.11 (`pango >=1.56.4`)**,
and GStreamer is there because Qt is. Pillow is the same build in both solves;
pinning `matplotlib <3.11` recovers only one of the fourteen (`libraqm`). So the
chain is `boost-cpp` → an `xz`/`icu`-era pin → `qt-main` build 6 → GStreamer
1.24 → no Pango. Keeping a C++ library nothing compiles against, in
order to freeze five unrelated packages at older builds, is a pin wearing a
dependency's clothes: the next unrelated re-solve moves that branch anyway. The
rule the measurement supports is *measure before removing*, not *never remove
what measures badly* — when the closure delta is a side effect rather than a
use, the use decides.

Not every removal shrinks the closure, and saying which is which matters more
than the count. Dropping `numexpr` frees **nothing**: `pytables` hard-requires
it, so it is installed either way, and the gain is that no ChiSurf code reaches
for it (the kernel that replaced it is also 22× faster). `pyarrow-core` was
worth a real **37**.

`pandas` is the same story and is **not a removal candidate**, measured
2026-08-06: taking it out of the recipe's `run:` list moves the closure 256 →
255 — it is worth exactly **itself**. Its usual companions stay behind for other
owners (`python-dateutil` for matplotlib and the Jupyter client, `pytz` and
`python-tzdata` for `arrow`), and in the **dev env it would not leave at all**,
because `pdb2pqr` requires `pandas >=1.0`. Against that single package stands
the port: 69 importing files, 31 of them at module scope, 202 `DataFrame`
constructions, and an API surface — `groupby`, `merge`, `query`, `describe`,
`quantile`, `Categorical`, `read_csv`/`to_csv`, `HDFStore` — that is not the
page of code the reimplementation rule is about. Two of those uses are
**contracts rather than conveniences**: the `chitable` widget family is
DataFrame-backed by design ([PRD-66](../prds/prd-66.md)), and the burst
exports' pandas HDF5 `format="table"` layout is what ndX opens, so replacing it
changes a file format another tool reads. The rule is *reimplement what is
trivial*, and the trigger for it is the size of the package's job here, not the
size of the package.

What *is* worth doing is moving the **storage model** off it, which is a
different question from removing the import: [PRD-82](../prds/prd-82.md) stages
`chitable`, the burst tables and the HDF5 writers onto the simulation library's
columnar store, keeping pandas as an interop and fallback layer. The gain there
is not a package count — it is 114.3 → **60.2 MB** on a 1M-row burst table,
dtypes and missing values that survive a file, and finally making the `pytables`
removal true rather than declared.

The mirror image of an undeclared *dependency* is an undeclared *import*, and it
fails the same way: on a developer machine the package is there transitively, in
a packaged install the plugin does not load. `test/test_declared_dependencies.py`
holds the line — every **module-level** import under `chisurf/` must resolve to a
declared distribution, the standard library, or a sibling project, and the three
lists must agree with each other: what the dev env declares the conda package
ships, and what the conda runtime has the wheel declares too (as a requirement,
or as an extra when the code detects it and works without it). Every deliberate
difference is named in the test with its reason — `micromamba` ships but is not
a wheel dependency, `pdb2pqr` and `latexify-py` are dev-env-only. An import
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

## A native build dependency that arrived by accident, and left the same way

`hdf5` is a **build** dependency of the photon library — its CMake calls
`find_package(HDF5)` unconditionally — but it was never declared as one. It used
to arrive in the environment as a transitive dependency of the HDF5 table
package, so nothing noticed. Removing that package took HDF5 out of the macOS
environment with it, and `build-tttrlib` has been unable to configure there ever
since:

```
CMake Error ... Could NOT find HDF5 (missing: HDF5_LIBRARIES HDF5_INCLUDE_DIRS C)
```

It *was* declared — for `win-64` and `linux-64` only — which is what made the
failure read as platform-specific rather than as the missing dependency it was.
It is now in the common `[dependencies]` table, and in `_BUILD_ONLY` in
`test/test_declared_dependencies.py`, because it is not part of the released
runtime: the shipped package depends on the photon library already linked.

**Two traps this hid behind.** A pipeline hides it — `pixi run build-tttrlib |
tail` reports the exit status of `tail`, so a failed build reads as success; run
it unpiped, or check `${PIPESTATUS[0]}`. And the failure is *not* fatal to
anything you would notice: the previously built library stays installed and
importable, so a C++ change appears to have been rebuilt when it has not. The
way to tell is to assert the new behaviour from Python, not to read the build log.

**Verifying a library change without disturbing anyone.** Building into a
scratch prefix touches neither environment, which matters because the
environments here are shared and the lock file usually carries another session's
uncommitted work:

```bash
ENV=<conda env with hdf5>
CMAKE_ARGS="-DCMAKE_PREFIX_PATH=$ENV -DHDF5_ROOT=$ENV -DHDF5_NO_FIND_PACKAGE_CONFIG_FILE=TRUE" \
  $ENV/bin/python -m pip install <library source> --no-build-isolation --no-deps \
    --target /tmp/verify/pkg --config-settings=build-dir=/tmp/verify/build
PYTHONPATH=/tmp/verify/pkg python -c "..."
```

Running the affected suites under that `PYTHONPATH` as well as normally is how a
change is shown to be correct against **both** the shipped build and the fixed
one.

## Two environments, two HDF5s, one shared build

The photon library is built once, into the pixi environment, and `link_build()`
symlinks the result into the sibling conda environment. That only works while
both environments agree on the native libraries the build links, and **they do
not agree about HDF5**: the pixi solve takes HDF5 2.1 (`libhdf5.320`), the conda
environment carries 1.14 (`libhdf5.310`). A build made in one is unloadable in
the other:

```
ImportError: dlopen(...): Library not loaded: @rpath/libhdf5.320.dylib
```

**`build-tttrlib` reports success anyway**, because it verifies the environment
it installed *into* (`sys.prefix`) and that one is fine. The symlinked sibling
breaks silently, and the failure only shows up the next time a test suite runs
there.

Until the two environments agree on HDF5, the sibling needs **its own build**
rather than a symlink — built against its own prefix and installed as a real
directory:

```bash
ENV=<sibling conda env>
SP=$ENV/lib/python3.12/site-packages
CMAKE_ARGS="-DCMAKE_PREFIX_PATH=$ENV -DHDF5_ROOT=$ENV -DHDF5_NO_FIND_PACKAGE_CONFIG_FILE=TRUE" \
  $ENV/bin/python -m pip install <library source> --no-build-isolation --no-deps \
    --target /tmp/build/pkg --config-settings=build-dir=/tmp/build/tree
rm "$SP/<pkg>" "$SP/<pkg>-*.dist-info"          # symlinks: removing them leaves pixi untouched
cp -R /tmp/build/pkg/<pkg> /tmp/build/pkg/<pkg>-*.dist-info "$SP/"
find "$SP/<pkg>" \( -name '*.so' -o -name '*.dylib' \) -exec /usr/bin/codesign --force --sign - {} \;
```

The codesign step is not optional on macOS: a copied extension whose signature
is invalidated dies on import with **exit 137 / Killed: 9** and no message.

**Re-running `build-tttrlib` re-creates the symlink and breaks the sibling
again.** The durable fix is for the two environments to pin the same HDF5, or
for the link step to check that the built extension actually loads in every
environment it links into — not only in the one it installed to.

## The same error with nothing wrong with the build

Once each environment has a build it can load, that `libhdf5.320` message is
*still* reachable — and then it is not a build problem at all. Read the loader's
last line rather than its first:

```
ImportError: dlopen(<pixi env>/site-packages/_tttrlib…so):
  Library not loaded: @rpath/libhdf5.320.dylib
  Reason: tried: '<conda env>/bin/../lib/libhdf5.320.dylib' (no such file)
```

The extension comes from **one** environment and the rpath that has to resolve
its libraries comes from the interpreter of **another**. `@rpath` is resolved
against the load commands of the *running executable*, so an extension is only
loadable by the interpreter it was installed for; the import itself succeeds,
because `sys.path` says nothing about which environment an entry belongs to.

**Nobody sets that up on purpose. An IDE does.** Marking an environment's
`site-packages` as a *source root* makes the IDE prepend it to `PYTHONPATH` for
every run configuration, whichever interpreter that configuration selects — and
IntelliJ/PyCharm offers to do exactly this whenever it indexes a directory that
looks like sources. One such root in `.idea/*.iml` is enough to make
`<conda python> -m chisurf` load the pixi environment's photon library. The
project's module file had accumulated **twelve**: both pixi environments, a
rattler build tree, and nine Python 3.10 benchmark virtualenvs (one of them
pinning an *older* photon library). Exclude those trees; never source-root them.

`chisurf.__init__` no longer depends on getting that right.
`drop_foreign_environment_paths()` in
[`chisurf/_bundled_packages.py`](../../chisurf/_bundled_packages.py) removes any
`sys.path` entry that is the `site-packages` **or standard library** of an
environment other than the running interpreter's — comparing against `sys.prefix`
and `sys.base_prefix`, so a virtual environment still reaches the system packages
it was created with. It runs before the first ChiSurf import, because by the time
one has happened the first compiled extension has already been resolved against
the wrong environment. It logs what it removed and why (a foreign *standard
library* is the worse case: it shadows the running interpreter's own modules),
and `CHISURF_ALLOW_FOREIGN_ENVIRONMENT_PATHS=1` opts out.
`test/test_foreign_environment_paths.py` covers the layouts, the escape hatch,
and the end-to-end launch with a poisoned `PYTHONPATH`.

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

**`modules/quest` is a sibling checkout too, and was a stale submodule.** It was
pinned at a commit predating QuEst's own restructuring, so it carried neither
`quest/rpc` nor `quest/gui` — which is to say the pin could not satisfy the
`quenching_estimator` plugin that imports both. Nothing failed as long as the
installed QuEst won the import; an IDE run configuration that puts
`modules/quest` on `PYTHONPATH` makes the stale copy win instead, and startup
then logs `ModuleNotFoundError: No module named 'quest.rpc'` from plugin service
registration and continues with sixteen RPC methods missing. **A duplicate of a
package that is developed elsewhere is a shadowing bug waiting for a path
order**, which is why the actively-developed companions are symlinks rather than
copies. `modules/quest -> ../../quest` now, as `mmfdb` and `tttrlib` already
were; the submodule is out of `.gitmodules`. Its old object store is left in
`.git/modules/quest`, because the pinned commit is not reachable from the
sibling checkout — the two histories diverged — and that directory is the only
local copy.

# Conda recipe: what it builds, and what it must not grow back

`rattler-recipe/recipe.yaml` packages **chisurf and nothing else**. The whole
build is the inline `script:` — one `pip install . --no-deps
--no-build-isolation` — because ChiSurf compiles nothing: no `.pyx`, no `.i`, no
`Extension`, and `setup.py` stopped building the burbulator C++ library when
that simulator was retired. Everything else in a runnable installation (the TTTR
library, the label library, the metadata store, the IMP mixin, the local
`modules/*`) is layered on top of this package by the installer builder below.

Two consequences worth stating, because both were violated for months:

- **`host:` carries no toolchain.** Compilers, cmake, ninja, swig, cython,
  pythran, pybind11, eigen, boost-cpp, doxygen and hdf5 were all inherited from
  builds that no longer happen; only python, pip, setuptools, wheel, numpy (for
  `--no-build-isolation`) and git (the version fallback) remain. Whatever still
  compiles does so elsewhere — tttrlib in `build_tools/build_tttrlib.py`,
  labellib and the local modules in `build_tools/build_installer.py`.
  **`run:` is now held to the same list**, which is how `boost-cpp` survived the
  first sweep: the guard only read `host:`, so a build-time C++ library sitting
  in the *runtime* list — the strangest place of the two — went unseen for
  months. `test_recipe_needs_no_toolchain` checks both sections.
- **An inline `script:` makes a `build.sh`/`build.bat` beside it dead.**
  rattler-build runs one or the other, and the inline script wins. Two such
  scripts sat in `rattler-recipe/` from April to August 2026 being actively
  maintained — a step to install the metadata store was added to both in July,
  described as closing a packaging gap it could not close — while rattler-build
  had not read either since April. They are gone; extend the `script:`.

**The entry-point list is generated, and drifts silently.**
`rattler-recipe/collect_entry_points.py` regenerates the block between the
`BEGIN_ENTRY_POINTS`/`END_ENTRY_POINTS` sentinels from
`pyproject.toml`'s `[project.scripts]` / `[project.gui-scripts]` plus each
plugin's `cli_entrypoint` assignment. Nothing imports those targets at build
time, so a moved module leaves a command that only fails once installed: six
`csg_*` launchers named pre-reorganisation paths and `csc` pointed at
`chisurf.cli` long after it became `chisurf.core.cli`.
`test/test_rattler_recipe.py` now resolves every entry point against the tree
(parsing, not importing — importing a plugin pulls in Qt), checks the generated
block is current, and checks the recipe's own tests stay headless: the recipe
used to test `chisurf --version`, an entry point that ignores argv and enters
the Qt event loop, which would have hung the build had the driver not been
passing `--test skip`. That flag is gone from
`build_tools/run_rattler_build.py`; `import chisurf` is now a real gate on the
`run:` list, and `CHISURF_SKIP_PACKAGE_TEST=1` opts a local build out.

A plugin that ships a `cli.py` but no `cli_entrypoint` assignment is invisible
to the generator — it ships in the package with no command to reach it. About
twenty plugins are in that state; `burst-background` is the one that had a
console script and lost it.

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
