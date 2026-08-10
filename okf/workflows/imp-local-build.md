---
type: Workflow
title: IMP from source, wired into the arm64 conda env
description: The conda IMP package cannot carry IMP.bff, so arm64 runs IMP built from ../imp with modules/bff symlinked to ../imp.bff. One .pth wires the build tree into the env, and rebuilds land with no re-install.
resource: /Users/tpeulen/dev/imp/cmake-build-arm64
tags: [build, environment, imp, imp.bff, conda, arm64, swig]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

1. The FRET suite is **6 failed / 122 passed** (from 16/112). All six remaining
   failures are `test_examples.py` wanting `/Users/tpeulen/dev/olga`, a sibling
   checkout not on this machine. Nothing IMP-related is outstanding.
2. `IMP.npctransport` is disabled in this build — IMP's `FindProtobuf` rejects
   the env's protobuf 6.31.1. Nothing in ChiSurf uses it; revisit only if that
   changes.
3. The `imp.bff` fix lives on a local branch (`dev`, commit `124f6bc`) and is
   **not pushed**. It should go upstream — the same break hits anyone building
   imp.bff with SWIG ≥ 4.3.

# Why IMP is built from source at all

ChiSurf's FRET modelling plugin needs `IMP.bff`, and specifically
`IMP.bff.restraints.AVNetworkRestraintWrapper`
([`imp_engine.py:551`](../../chisurf/plugins/modelling/fret/core/imp_engine.py)).
The conda-forge `imp` package cannot supply it — `imp 2.24.0` shipped an
`IMP.bff.restraints` package that is **empty**:

```
$ python -c "import IMP.bff.restraints as r; print(dir(r))"   # conda imp 2.24.0
[]
```

The class is not missing from the world, only from the package: it is in the
sibling checkout at
`/Users/tpeulen/dev/imp.bff/pyext/src/restraints/AVNetworkRestraint.py:69`.
The way to get it is to build IMP from `/Users/tpeulen/dev/imp` with
`modules/bff` symlinked at that checkout, and point the env at the build tree.
IMP is **2.25** (`develop`) as of this writing; the conda package is 2.24.

This is the same shape as the photon library in
[build-and-env](build-and-env.md) — a dependency whose published package lags
the source by enough to be wrong rather than merely old — but the mechanism is
different, and simpler: no copying, no codesigning, no second build.

# The checkout: modules/bff is a symlink, and pulls fight it

`/Users/tpeulen/dev/imp` carries two permanent local modifications:

| Path | State |
|---|---|
| `modules/bff` | **symlink** → `../../imp.bff`, replacing the git submodule. `git status` reports `typechange` forever; that is correct, not something to clean up. |
| `.gitignore` | adds `build`, `cmake_modules`, `cmake-build*` |

Upstream moves the `modules/bff` gitlink, so **stashing the typechange makes the
pop conflict**. Pull like this instead — stash only `.gitignore`, drop to a
plain gitlink, pull, then re-make the symlink:

```bash
cd /Users/tpeulen/dev/imp
git stash push -m "local build-dir ignores" .gitignore
rm modules/bff && git checkout -- modules/bff
git -c submodule.recurse=false pull --ff-only origin develop
git submodule update --init --recursive -- \
    modules/npctransport modules/pmi1 modules/bayesianem modules/sampcon \
    modules/nestor modules/emseqfinder components/pathway_mapping components/metamodeling
rm -rf modules/bff && ln -s ../../imp.bff modules/bff
git config submodule.modules/bff.update none    # future pulls leave it alone
git stash pop
```

`submodule.modules/bff.update none` matters beyond the pull: IMP's own
`post-checkout` hook runs `git submodule update --recursive --init`, which would
otherwise replace the symlink on every branch switch.

**IMP's git hooks hard-code an interpreter path.** They were still invoking
`envs/IMP_BUILD/bin/python3.12` — an environment that no longer exists — so every
checkout printed two `No such file or directory` lines and silently skipped
`cleanup_pycs.py` and `setup_cmake.py`. Regenerate them with the interpreter you
actually use: `<env>/bin/python setup_git.py`.

# Building against arm64

Prerequisite gaps in the env, both real: **`cereal` was missing** (a hard IMP
dependency) and is now installed. Present and used: boost 1.88, eigen 5.0.1,
hdf5 1.14.6, gsl, fftw, opencv4, openmpi, swig 4.4.1, ninja, numpy 2.4.6.
Absent and therefore auto-disabled: CGAL (`IMP.cgal`), libTAU (`IMP.cnmultifit`),
doxygen 1.8.6 (docs). `IMP.npctransport` is disabled too — see below.

```bash
E=/Users/tpeulen/mambaforge/envs/arm64
B=/Users/tpeulen/dev/imp/cmake-build-arm64        # matches the `cmake-build*` ignore
conda install -p $E -c conda-forge -y cereal

$E/bin/cmake -S /Users/tpeulen/dev/imp -B $B -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=$E \
  -DCMAKE_OSX_SYSROOT=$(xcrun --show-sdk-path) \
  -DPython3_EXECUTABLE=$E/bin/python \
  -DSWIG_EXECUTABLE=$E/bin/swig \
  -DIMP_USE_SYSTEM_RMF=on \
  -DIMP_USE_SYSTEM_IHM=on \
  -DIMP_MAX_CHECKS=USAGE

ninja -C $B -j6            # ~90 min on 8 cores, ~700 MB of build tree
```

Use **`$E/bin/cmake`, not `cmake`** — the one on `PATH` is a pip-installed CMake
4.2 inside mambaforge *base*, and the point of this build is that every part of
the toolchain comes from the target environment.

**`IMP_USE_SYSTEM_RMF` / `IMP_USE_SYSTEM_IHM` are not optional here.** conda
`rmf` 1.7.0 and `ihm` 2.11 live *in* `site-packages`, which always precedes
`.pth` entries on `sys.path`. A bundled RMF would therefore be shadowed by
conda's whichever way the build was configured; consuming them as system
dependencies makes that shadowing correct instead of dangerous, and drops RMF
out of the compile entirely. IMP ships `cmake_modules/FindRMF.cmake` and conda
`rmf` provides the headers, library and `share/RMF/swig` it needs.

**No RPATH flags are needed.** CMake puts `$E/lib` in the build-tree RPATH by
itself, because the conda dylibs carry `@rpath/lib*.dylib` install names. The
built extensions then reference IMP's own libraries by **absolute path**
(`/Users/tpeulen/dev/imp/cmake-build-arm64/lib/libimp_kernel.0.dylib`), which is
what makes the `.pth` wiring below sufficient — no `DYLD_LIBRARY_PATH` anywhere.

**One `libc++`, not two.** The compiler is Apple clang 17 from the Command Line
Tools, and the worry with that is linking Apple's `libc++` while conda's boost
links conda's. It does not happen: the env ships no C++ headers
(`$E/include/c++/v1` does not exist) and the link lands on
`@rpath/libc++.1.dylib`, which resolves through the same RPATH to the env's own
`libcxx`. One standard library in the process, so exceptions and typeinfo cross
the boost boundary safely. If that ever changes, the fallback is
`conda install -p $E clang_osx-arm64 clangxx_osx-arm64` and explicit
`-DCMAKE_C_COMPILER`/`-DCMAKE_CXX_COMPILER` — at the cost of `activate.d`
scripts that export `CC`/`CXX`/`CFLAGS` for *everything* built in `arm64`,
including tttrlib.

# Wiring the build tree into the env

`_IMP_kernel`, `_IMP_core`, … are imported as **top-level** modules
(`IMP/core/__init__.py:15` is `import _IMP_core`), so the whole `<build>/lib`
directory has to be one `sys.path` entry. That is one `.pth` line, and it never
needs maintenance — a module added to IMP tomorrow is covered. A symlink farm
would be ~40 links and a re-link every time that happens.

```bash
SP=$E/lib/python3.12/site-packages
conda remove -p $E --force -y imp        # --force: leaves rmf, ihm and every dep
```

`$SP/imp-local-build.pth`:

```
/Users/tpeulen/dev/imp/cmake-build-arm64/lib
import os; os.environ.setdefault('IMP_DATA', '/Users/tpeulen/dev/imp/cmake-build-arm64/data'); os.environ.setdefault('IMP_EXAMPLE_DATA', '/Users/tpeulen/dev/imp/cmake-build-arm64/doc/examples')
```

Removing the conda `imp` package is required, not tidiness: `site-packages`
precedes `.pth` entries, so conda's IMP would win every import.

The second line is the part that is easy to miss. A build tree compiles
`/usr/local/share/IMP` in as its data directory, so without `IMP_DATA` anything
touching module data dies:

```
IOException: Unable to find data file top_heav.lib in [/usr/local/share/IMP].
IMP is not installed or set up correctly.
```

IMP's own `$B/setup_environment.sh` exports it, but that only helps a shell that
sourced it. A `.pth` line beginning with `import` is **executed** at interpreter
startup, so putting it there covers every entry point — an activated shell, a
bare `$E/bin/python`, an IDE run configuration — with one file. `setdefault`
means an explicit `IMP_DATA` still wins.

To undo the whole arrangement: `rm $SP/imp-local-build.pth` and
`conda install -p $E imp`.

**Never `make install` into the env.** That is where the stray
`$E/lib/python3.{1,10,11}/site-packages` trees came from, and it would defeat
the point of everything above.

# Rebuilds really do land in the env

Verified on 2026-08-10, both directions:

**Python — no rebuild at all.** IMP *symlinks* module Python sources into the
build tree, so the chain from the env to the working copy is unbroken:

```
$SP/imp-local-build.pth
  └─ cmake-build-arm64/lib/IMP/bff/restraints/AVNetworkRestraint.py
       → imp/modules/bff/pyext/src/restraints/AVNetworkRestraint.py
          → imp.bff/pyext/src/restraints/AVNetworkRestraint.py   (the working copy)
```

Appending a sentinel to the file in `../imp.bff` and importing it from the env
in a fresh interpreter showed it immediately, with no build step, and
`os.path.realpath(module.__file__)` pointed back into `/Users/tpeulen/dev/imp.bff`.

**C++ — one `ninja`.** `touch ../imp.bff/src/AV.cpp && ninja -C $B IMP.bff-lib`
relinked `lib/libimp_bff.0.dylib` in place (mtime moved), and the env imported
the rebuilt library on the next interpreter start. Because the extensions
reference that dylib by absolute path, nothing needs re-linking or re-installing.

# imp.bff does not build with SWIG ≥ 4.3 (fixed on `dev`)

The whole build fails at exactly one target with the env's SWIG 4.4.1:

```
FAILED: modules/bff/pyext/.../bff_swig/wrap.cpp.o
wrap.cpp:29718: error: no matching function for call to 'SWIG_Python_AppendOutput'
  note: candidate function not viable: requires 3 arguments, but 2 were provided
```

SWIG 4.3 added a third `is_void` argument to `SWIG_Python_AppendOutput`, and
imp.bff's **vendored** `pyext/numpy.i` predates it — 38 typemap call sites still
use the two-argument spelling. No IMP module hits this; only imp.bff carries its
own copy of `numpy.i`.

Fixed on the new `imp.bff` branch **`dev`** (commit `124f6bc`) by routing those
call sites through a macro that adapts to `SWIG_VERSION`, so older SWIG still
builds:

```c
#if SWIG_VERSION >= 0x040300
#define IMPBFF_SWIG_AppendOutput(result, obj) SWIG_Python_AppendOutput(result, obj, 0)
#else
#define IMPBFF_SWIG_AppendOutput(result, obj) SWIG_Python_AppendOutput(result, obj)
#endif
```

`is_void=0` reproduces the pre-4.3 behaviour exactly.

# What the build fixed, and what it did not

```bash
$E/bin/python -c "
import IMP, IMP.bff, IMP.bff.restraints as r
print(IMP.get_module_version())      # develop-345e71cb9a
print(r.AVNetworkRestraintWrapper)   # <class ...AVNetworkRestraintWrapper>
print(IMP.atom.get_data_path('top_heav.lib'))"
```

All three answer correctly — but the build alone did **not** move the FRET
suite, and finding out why was the substantive part of this work.

```bash
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
  python -m pytest chisurf/plugins/modelling/fret/test -p no:cov -o addopts="" -q
# 16 failed, 112 passed        <- local build alone, unchanged from the baseline
# 6 failed, 122 passed         <- after the imp-tricks fix below
```

Ten of the sixteen were still
`AttributeError: module 'IMP.bff.restraints' has no attribute 'AVNetworkRestraintWrapper'`
with the class sitting in the build tree the whole time.

**The wrapper was never gone — it was shadowed.**
`modules/imp-tricks/src/sitecustomize.py` inserts imp-tricks' own tree at the
**front** of `IMP.bff.__path__`:

```
IMP.bff.__path__ == ['/Users/tpeulen/dev/imp-tricks/src/IMP/bff',
                     '/Users/tpeulen/dev/imp/cmake-build-arm64/lib/IMP/bff']
```

imp-tricks ships an `IMP/bff/restraints/` package of its own
(`SimpleAVNetworkRestraint`, `DirectLabelingRestraint`, `LabelingSite`, …), and a
subpackage resolves to the **first** matching directory and stops — that one
directory becomes its entire `__path__`. So imp.bff's `restraints` was
unreachable: not its submodules, not the names its `__init__` exports. This is
precisely the failure its own docstring says extending `__path__` was meant to
avoid ("puts the source modules beside the compiled ones instead of replacing
them"). That holds for a name on one side only; it does not hold for
`restraints`, which exists on both.

The A/B was unambiguous — same interpreter, same build, one `PYTHONPATH` entry:

| `PYTHONPATH` | `IMP.bff.restraints.__file__` | `AVNetworkRestraintWrapper` |
|---|---|---|
| with `modules/imp-tricks/src` | `imp-tricks/src/IMP/bff/restraints/__init__.py` | **absent** |
| without it | `cmake-build-arm64/lib/IMP/bff/restraints/__init__.py` | **present** |

**Fixed in imp-tricks** (`5967e77`), which is where it belonged. A subpackage
found in both trees now has the two directories unioned into one `__path__`
(local first, so precedence is unchanged), and the shadowed `__init__` is
evaluated against the live package so its public names are adopted. Nothing
local is overwritten; it recurses to any depth. All five names now resolve from
one package:

```
IMP.bff.restraints.__path__ == ['…/imp-tricks/src/IMP/bff/restraints',
                                '…/cmake-build-arm64/lib/IMP/bff/restraints']
AVNetworkRestraintWrapper  SimpleAVNetworkRestraint  DirectLabelingRestraint
LabelingSite  AVMeasurement                         -> all present
```

The six remaining failures are unrelated to IMP: all `test_examples.py`, all
wanting `/Users/tpeulen/dev/olga`, a sibling checkout not on this machine.

**Worth keeping**: a missing attribute had been recorded as an upstream API
removal without anyone checking whether something on `sys.path` stood in front
of it. `IMP.bff.__path__` had two entries all along, and printing it would have
ended the question in one line. When a name that should exist does not, print
the package's `__path__` and `__file__` before believing it was deleted.

# Traps

- **Disk.** The build tree is ~700 MB, but the full compile needs headroom well
  beyond that; it died once with the volume at 100% and `ninja` reported nothing
  useful — the failure surfaced as an empty tool output, then as `_IMP_algebra`
  vanishing from an otherwise finished build. If extensions disappear, check
  `df` before debugging anything else.
- **`/Users/tpeulen/dev/imp/build`** is a *stale* build tree (936 MB) targeting
  `envs/IMP_BUILD`, an environment that no longer exists. Nothing can import it.
  `cmake-build-Debug` likewise targets mambaforge base.
- **`IMP.npctransport` is disabled**: `FindProtobuf` does not accept the env's
  protobuf 6.31.1. Unused by ChiSurf.
- After a failed build, re-run plain `ninja -C $B` — the first failure stops
  scheduling and leaves later targets unbuilt.
