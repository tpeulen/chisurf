---
type: Documentation
title: Licensing
description: The source code is MIT and the documentation CC BY-SA 4.0; the licence of every package in the stack, how IMP.bff's LGPL is met, and how to attribute material reused here or from here.
tags: [licensing]
anchor: licensing
---

(licensing)=
# Licensing

ChiSurf is distributed under two licences, and which one applies depends on
what you are looking at rather than where it lives in the package:

| What | Licence | File |
|---|---|---|
| **Source code** — everything under `chisurf/`, `build_tools/`, `test/` | MIT | `LICENSE` at the repository root |
| **Documentation** — everything under `docs/` | Creative Commons **Attribution-ShareAlike 4.0 International** | [`docs/LICENSE`](LICENSE) |

The source code's licence is MIT:

    SPDX-License-Identifier: MIT

The split is deliberate. Documentation is prose, figures and worked examples,
and the reasons to share those are not the reasons to share code: a copyleft
that talks about linking and object files is the wrong instrument for a page
explaining what $\kappa^2$ does to a distance. CC BY-SA is the licence the rest
of the scientific-reference world already uses, so text can move between this
documentation and its neighbours in both directions.

Note that the documentation is **installed into the package**, not merely kept
beside it — the help browser reads these pages at runtime. A ChiSurf install
therefore contains both licences, and both files ship with it.

## What you may do with these pages

Copy them, print them, translate them, put them in a lecture course, quote them
in a paper, adapt them into your group's own protocol — commercially or not.
Two conditions:

- **Attribution.** Credit ChiSurf, link to the page or the project, and say if
  you changed anything. A line such as *"Adapted from the ChiSurf documentation
  (CC BY-SA 4.0)"* with a link is enough.
- **ShareAlike.** If you distribute an adaptation, it goes out under CC BY-SA
  4.0 as well. Quoting a paragraph in a paper is not an adaptation; rewriting a
  page into your own handbook is.

Neither condition applies to the *facts*. Förster's $1/R^6$ is not ours, the
bibliography's DOIs are not ours, and nothing here restricts your use of an
equation.

## Bringing outside material in

The share-alike condition is also what lets these pages **absorb** material from
the CC BY-SA commons — Wikipedia most obviously. Before adding text from
anywhere, check the licence of the source:

| Source licence | May it be used here? |
|---|---|
| CC BY-SA 4.0 (Wikipedia, and most wikis) | **Yes**, with attribution and a note of changes |
| CC BY 4.0, CC0, public domain | **Yes** — the weaker terms absorb into CC BY-SA cleanly |
| CC BY-SA 3.0 | Yes — 3.0 permits relicensing an adaptation under 4.0 |
| CC **NC** or **ND** variants | **No.** They are not compatible with CC BY-SA 4.0 |
| Copyrighted prose (a paper, a GPL-licensed manual) | **No.** Cite it and write your own summary |

That last row is the one that catches people: a compatible *code* licence does
not make prose usable here, and quoting a journal article at length is a
copyright problem regardless of which licence this documentation carries.

Compatibility with the code runs freely: the code is MIT, so prose from these
pages may be moved into the codebase — a tooltip, a `help.md`, a docstring —
with attribution in the file. Text that is *copyleft-licensed prose* (a GPL
manual, an FDL textbook) still cannot be moved into `docs/`: it would bind
these pages to its share-alike terms.

### Recording where something came from

A page that incorporates outside material carries the source in its front
matter, so the obligation is visible to whoever edits it next and survives being
copied out of context:

```yaml
---
type: Concept
title: ...
sources:
  - text: Adapted in part from the English Wikipedia article "Dexter electron transfer"
    url: https://en.wikipedia.org/wiki/Dexter_electron_transfer
    licence: CC-BY-SA-4.0
---
```

Attribution is per page, not per project — a blanket note in this file does not
discharge it. If you cannot name the source, do not add the text.

**Prefer writing to importing.** The documentation has a voice: terse, symbols
matching the code, no glossaries, every claim tied to something ChiSurf actually
computes. Imported prose rarely has that, and a page assembled from other
people's paragraphs reads like one. Licence compatibility makes importing
*allowed*; it does not make it the better option, and the usual right answer is
still to read the source, follow its citations to the primary literature, and
write the page here.

## The stack

ChiSurf is assembled from separately distributed packages. Each carries its own
licence file and declares the same licence in its package metadata (`pyproject.toml`
and conda recipe). The table below is checked against those declarations by
`test/test_stack_licences.py` wherever the repositories are checked out.

<!-- stack-licences:start -->
| Package | Licence (SPDX) | Role |
|---|---|---|
| chisurf | MIT | the application |
| emtk | MIT | the GUI toolkit |
| chimol | MIT | the molecular viewer |
| mmfdb | MIT | the metadata and provenance store |
| ndxplorer | MIT | the n-dimensional histogram explorer |
| quest | MIT | the quenching estimator |
| imp-tricks | MIT | coarse-grained molecules and related IMP extensions |
| labelizer | MIT | the labelling-site finder (a chimol plugin) |
| tttrlib | BSD-3-Clause | photon-stream I/O and analysis |
| imp-bff | LGPL-2.1-or-later | structures, accessible volumes and fluorescence models (`IMP.bff`) |
<!-- stack-licences:end -->

MIT and BSD-3-Clause are permissive and combine freely. IMP.bff is an IMP
module and keeps IMP's licence for its LGPL modules, the GNU Lesser General
Public License, version 2.1 or later; it is the only copyleft package ChiSurf
needs at run time.

`chinet` is obsolete — unreachable from ChiSurf and
unmaintained — and is not part of the stack. Every other dependency, with its
licence, is listed in {doc}`/development/licenses`.

(licensing-lgpl)=
### IMP.bff and the LGPL

The LGPL governs the library, not the program that uses it, provided the
user can still replace the library. ChiSurf stays MIT because it uses IMP.bff
in exactly that way:

- **Separate package.** IMP.bff is its own distribution (`imp-bff`, imported
  as `IMP.bff`), built from its own repository and installed beside ChiSurf in
  `site-packages`, unmodified. It is never merged into the `chisurf` package.
- **Dynamically loaded.** ChiSurf reaches it through Python's import system at
  run time; its compiled parts are a Python extension module and a shared
  library loaded by the interpreter.
- **User-replaceable.** Installing another build of IMP.bff — including a
  modified one — over the shipped one (`python -m pip install <wheel>` with the
  runtime's interpreter) is all it takes; ChiSurf uses whatever IMP.bff is
  installed.
- **No copied code.** No ChiSurf file copies IMP.bff code. Where computation
  moved into IMP.bff, ChiSurf calls its public interface (the numpy adapters
  in `chisurf/core/math/special.py` and `chisurf/core/fluorescence/crosstalk.py`
  forward to it; they do not reimplement it).
- **Text with the installer.** The installer
  (`build_tools/build_installer.py`) writes a `licenses/` folder into the
  runtime (`Contents/Resources/licenses` in the macOS app): ChiSurf's MIT
  licence, this documentation's CC BY-SA 4.0, tttrlib's BSD-3-Clause, the
  **LGPL 2.1** text, and `NOTICE.txt`, which repeats these terms, records the
  shipped imp-bff version (its `+g<hash>` suffix names the source commit) and
  names the source file below. The texts live in `build_tools/licenses/`.
- **Source beside the installer.** The installer carries IMP.bff as object
  code, so LGPL 2.1 §6 asks for its complete source to be offered from the same
  place. Every [ChiSurf release](https://github.com/Fluorescence-Tools/chisurf/releases)
  therefore lists, next to the macOS, Linux and Windows installers, the
  **source distribution of the exact imp-bff version they bundle**
  (`imp_bff-<version>.tar.gz`). The installer build makes it: it reads the
  bundled version, checks out that revision of
  <https://github.com/tpeulen/IMP.bff>, runs `python -m build --sdist`, refuses
  an sdist whose version differs from the bundled one, and writes the file name
  into `NOTICE.txt`. A build that cannot produce the sdist fails, and the
  release job uploads it with the installers (`.github/workflows/pixi-ci.yml`).

The splash screen and the About window state the same: ChiSurf MIT, the
documentation CC BY-SA 4.0, tttrlib BSD-3-Clause, IMP.bff LGPL-2.1-or-later.

## Contributing

Contributions to `docs/` are accepted under CC BY-SA 4.0 and contributions to
the code under MIT; opening a pull request is taken as agreement to that. If you are contributing text you did not write, say where it came from in
the pull request, and add the `sources:` block above.

## See also

- {ref}`literature` — every work these pages cite.
- {doc}`/development/documentation_maintenance` — how the pages are built and
  what the generators own.
- {doc}`/development/licenses` — the license of every dependency (generated by
  `build_tools/license_tracker.py`).
