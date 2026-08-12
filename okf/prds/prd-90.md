---
type: PRD
prd: "90"
title: "PRD-90: Provenance-driven citation list for ChiSurf analysis pipelines"
description: tttrlib PRD-027 Part 5b defines automatic citation generation from .pto provenance graphs. This is the ChiSurf side: surface those citations in the GUI, let the user export them, and ensure ChiSurf-written .pto files embed them.
status: Draft
created: 2026-08-08
owner: tpeulen
sibling: tttrlib/okf/prds/PRD-027-modular-algorithm-registry.md (Part 5b)
---

# PRD-90 — Provenance-driven citation list for ChiSurf

## Summary

tttrlib PRD-027 Part 5b defines that a `.pto`-mmfdb container's provenance
graph can be walked to produce a deduplicated citation list — every algorithm
that touched an artifact contributes its `references_json`. The list is
available as JSON, text, or BibTeX, and can be embedded as a `citations`
attachment inside the `.pto`.

ChiSurf must **consume and surface** these citations. When a user opens a
`.pto` file, the citation list is visible in the GUI. When a user saves an
analysis pipeline, the citations are embedded automatically. The user can
export them in their preferred format at any time.

This is the sibling of tttrlib PRD-027 Part 5b. tttrlib builds the citation
list from the registry; ChiSurf displays it and makes it actionable.

## Problem / motivation

Today, when a researcher uses ChiSurf to analyse data and publishes results,
they must manually track which algorithms they used and find the original
papers to cite. This is error-prone — a multi-step burst analysis pipeline
might use a sliding-window burst search (Fries et al. 1998), an MLE fitter
(Margeat et al. 2006), BVA (Nevskyi et al. 2018), and a PDA model (Antonik
et al. 2006), and forgetting one is easy.

The algorithm registry (PRD-027) now carries `references_json` per algorithm.
The `.pto` provenance graph records which algorithms ran. ChiSurf is the
primary consumer of both — it should close the loop: the user clicks
"Export Citations" and gets a bibliography, or the `.pto` file they share
with collaborators already contains it.

## Goals

- When ChiSurf opens a `.pto` file, the citation list for every algorithm in
  the provenance graph is available in the GUI — a panel or menu item that
  shows "This analysis used the following algorithms" with their references.
- When ChiSurf saves a `.pto` file (after a burst search, a fit, etc.),
  `embed_citations` is called automatically so the file is self-contained.
- The user can export citations in three formats from the GUI:
  - **JSON** — for programmatic use or integration with reference managers
  - **Text** — numbered bibliography, paste-ready for a manuscript
  - **BibTeX** — for LaTeX
- The citation list updates live: if the user runs a new analysis step (e.g.
  adds a PDA fit), the citations panel reflects the new reference without
  reopening the file.
- ndx (the DataFrame editor) also surfaces a citation indicator when a `.pto`
  contains embedded citations, so a user browsing files knows which are
  publication-ready.

## Non-goals

- **A full reference manager.** ChiSurf is not Zotero. The citation list is
  derived from the algorithm registry, not user-curated.
- **Citation style formatting (APA, Chicago, etc.).** The text output is a
  plain numbered bibliography. Style formatting is the user's reference
  manager's job — export to BibTeX or JSON and import.
- **The algorithm `references_json` content.** That is maintained in
  tttrlib's algorithm registry. ChiSurf reads it, does not author it.

## Part 1 — citations panel in the ChiSurf GUI

A "Citations" panel (or a section in the provenance/info sidebar) that:

1. Calls `tttrlib.PtoFile.citations(current_file)` on open.
2. Displays each algorithm's display name, a one-line summary, and its
   references as a numbered list with author, title, journal, year, and a
   DOI link.
3. Highlights algorithms that have **no references** declared — a warning
   that a step in the pipeline has no citable reference, so the user knows
   to find one manually.
4. Updates when a new analysis step is run and the `.pto` is saved.

## Part 2 — automatic embedding on save

When ChiSurf writes a `.pto` file (burst search results, fit output, etc.):

```python
# After every write_table or container save
tttrlib.PtoFile.embed_citations(path)
```

This ensures the file is self-contained — a collaborator who receives the
`.pto` can read the `citations` attachment without tttrlib or ChiSurf
installed.

## Part 3 — export from the GUI

A menu action "Export Citations…" with three sub-options:

- **As BibTeX (.bib)** — writes a `.bib` file
- **As text (.txt)** — numbered bibliography
- **As JSON (.json)** — structured citation list

The export reflects the current pipeline's citations, not just the file on
disk (in case the user has run new steps since the last save).

## Criteria

1. ChiSurf displays a citations panel when a `.pto` file is open, listing
   every algorithm in the provenance graph with its references.

2. Each citation shows author, title, journal, year, and a clickable DOI
   link when available.

3. Algorithms with no `references_json` are flagged with a warning in the
   panel.

4. When ChiSurf saves a `.pto` file, `embed_citations` is called
   automatically. Opening the file in a text editor and reading the
   `citations` attachment shows the bibliography.

5. The user can export the citation list as BibTeX, text, or JSON from the
   GUI via "Export Citations…".

6. The citations panel updates after a new analysis step is run (without
   reopening the file).

7. A `.pto` file written by ChiSurf that is opened in ndx shows a citation
   indicator confirming embedded citations are present.
