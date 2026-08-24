---
type: Reference
title: Licensing
description: The documentation is CC BY-SA 4.0 and the source code is GPL-3.0-or-later; what that split allows, and how to attribute material reused here or from here.
tags: [reference, licensing, attribution, copyright]
anchor: licensing
---

(licensing)=
# Licensing

ChiSurf is distributed under two licences, and which one applies depends on
what you are looking at rather than where it lives in the package:

| What | Licence | File |
|---|---|---|
| **Source code** — everything under `chisurf/`, `modules/`, `build_tools/`, `test/` | GNU General Public License v3.0 **or later** | `LICENSE` at the repository root |
| **Documentation** — everything under `docs/` | Creative Commons **Attribution-ShareAlike 4.0 International** | [`docs/LICENSE`](LICENSE) |

    SPDX-License-Identifier: GPL-3.0-or-later AND CC-BY-SA-4.0

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
| GPL text, or a paper's copyrighted prose | **No.** Cite it and write your own summary |

That last row is the one that catches people: a compatible *code* licence does
not make prose usable here, and quoting a journal article at length is a
copyright problem regardless of which licence this documentation carries.

Compatibility runs one way with the code, too. CC BY-SA 4.0 is an approved
one-way compatible licence for GPLv3, so prose from these pages may be moved
into the GPL codebase — a tooltip, a `help.md`, a docstring. The reverse is not
true: text that is GPL-only cannot be moved into `docs/`.

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

## Contributing

Contributions to `docs/` are accepted under CC BY-SA 4.0 and contributions to
the code under GPL-3.0-or-later; opening a pull request is taken as agreement to
that. If you are contributing text you did not write, say where it came from in
the pull request, and add the `sources:` block above.

## See also

- {ref}`literature` — every work these pages cite.
- {doc}`/development/documentation_maintenance` — how the pages are built and
  what the generators own.
