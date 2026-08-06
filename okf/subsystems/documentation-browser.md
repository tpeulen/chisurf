---
type: Subsystem
title: The documentation browser
description: The in-application help window — a tree read from the documentation's own toctrees, ranked full-text search, and a renderer that typesets the formulas and resolves the cross-references instead of showing their markup.
resource: chisurf/plugins/core/help/
tags: [gui, qt, help, documentation, rendering, search, myst, rst]
timestamp: '2026-08-06T00:00:00Z'
---

# Where to pick this up

**The measurement.** Render the window headlessly and *look at it* — this is a
component whose defects are invisible to assertions and obvious in an image
(`QT_QPA_PLATFORM=offscreen`, the `arm64` env, `widget.grab().save(...)`; drive
it through a concept page, a manual page, a guide, a plugin README, the start
page and a search). Three automated numbers back that up:

* `pytest chisurf/plugins/core/help/test` — 81 tests. Two are the real
  guardrails: **every formula in `docs/` typesets** (`test_render.py`) and **no
  page leaks markup** — no `:::{`, no ` ```{ `, no `$$` reaching the reader.
* `pytest chisurf/plugins/core/help/test/test_docs_crosslinks.py` — 188 tests:
  every concept points at a guide, every guide at a concept, and every
  `{doc}`/`{ref}`/`[…](….md)` resolves to a page that is there.
* `python -m sphinx -b html -q docs <out>` must be **warning-free**. The tree
  and the website are built from the same toctrees, so a warning there is a
  wrong tree here.

**What is open.**

1. **The manual is AI-reviewed and awaits a human** — `csc help review-list`
   reports `0 reviewed, 79 AI-reviewed, 0 stale, 0 unreviewed`. All 79 pages
   have been read end to end and corrected against the source code; what remains
   needs somebody with the application open, checking that each screenshot still
   matches the interface and that each procedure still works, then pressing
   **Mark reviewed** (or `csc help review-set <path> --reviewer <name>`). Do it
   per page: the sign-off stores a content hash, so editing the page afterwards
   makes it stale. Pages rewritten from the source rather than merely tidied:
   `partial_donordonor_energy_migration`, `wormlike_chain`, `fcalculator`,
   `fluorescence_lifetime`, `discrete_fret_rate_constants`, `parameter_sampling`,
   `parameter_optimization`, `adding_the_membranediffusion_models`,
   `introduction`, `fit_models`.
2. **The RST manual has no `docs/manual/_images` scaling policy.** Screenshots
   are full-resolution and arrive as big blocks with a lot of air around them;
   `_constrain_image_widths` bounds the width but the vertical rhythm around a
   block image is still loose.
3. **Only `.md` files are indexed for cross-reference labels**
   (`api/xref.py:ref_index`). A `(label)=` in an `.rst` page is therefore not
   findable — no page needs it yet, and adding it means teaching the index the
   reStructuredText spelling too.

# What it is

`chisurf/plugins/core/help/` is the help *browser*: the window a reader lands in
from the Help menu, from a plugin's `?` (see
[help buttons and guided tours](gui-help-and-guides.md)) and from any
documentation link anywhere in the application.

| Layer | Module | Responsibility |
| --- | --- | --- |
| Contents | `api/toc.py` | Reads the documentation's `toctree` blocks into a `Node` tree — order, grouping and titles as authored. |
| Cross-references | `api/xref.py` | Resolves `{ref}`/`{doc}`/`:ref:`/`:doc:` and `[…](….md)` to a page, an anchor and the words the link should read as. Qt-free, so both renderers share it. |
| Markdown | `api/markdown.py` | MyST: directives, admonitions, figures, targets, tables, code, mathematics. |
| reStructuredText | `api/rst.py` | The manual, through bare docutils, with the Sphinx-only roles and directives registered as equivalents. |
| Mathematics | `api/mathtext.py` | Inline LaTeX as HTML text; display LaTeX rasterised transparently through matplotlib's mathtext. |
| Theme | `api/theme.py` | One colour set per page, taken from the running palette. |
| Window | `gui/tool.py` | Tree, start page, search, history, previous/next, authoring tools. |

# Decisions worth keeping

**The tree is the documentation's own table of contents.** It is parsed from the
`toctree` directives that build the published HTML, not from a directory walk.
That is what makes *one* fix serve both surfaces, and it is why the manual's
chapters live in `docs/manual/index.rst`: `build_tools/docs/convert_manual.py`
writes `index.generated.rst` beside it and never over it, because the chapter
structure exists nowhere in the source document.

**A group comes from the page, not from a list here.** A `.. rubric::` or a `##`
heading above a toctree names the group under it, and a `:caption:` does the
same. Nothing in the code enumerates "Fundamentals", "Correlation methods" or
"Worked example — calibrating an FCS setup".

**Two rows with the same words are not navigation.** The manual arrived with
three pages called *Overview* and two called *Calculations*; they are retitled at
the source, and `test_toc.py` fails if a section ever contains two pages with
one title.

**Developer documentation is not user documentation.** Architecture notes,
migration plans and the bundled modules' READMEs appear only behind the
*Authoring → Developer docs* toggle. So does the review sign-off: a release gate
is a maintainer's tool and was taking a third of the toolbar.

**"An agent read it" is a real state, and it is tracked.** The sign-off ladder is
`unreviewed → ai-reviewed → reviewed` (`api/review.py`). An agent can read a page
end to end and correct what it can verify against the source code; it cannot open
the application, so it cannot tell whether a screenshot still matches the
interface. Collapsing that into *unreviewed* throws away the only signal that
says which pages still need the **first** pass — which of 79 pages nobody and
nothing has been through. Three properties make the distinction safe, each with
a test in `test_review_levels.py`:

* an agent's sign-off **does not clear the release gate** — `review-check` still
  exits non-zero, and `report.ok` is still human-only;
* an agent **never overwrites a human's** sign-off, so a sweep over the whole
  manual cannot quietly erase what somebody actually checked;
* either level goes **stale** the moment the page is edited, and the record
  remembers which level expired.

Recorded from the GUI (*Authoring → 🤖 AI-reviewed*), over RPC
(`help.review.set` with `status: "ai-reviewed"`), or in bulk from the shell:
`csc help review-set docs/manual/*.rst --ai`.

**Markup that reaches the reader is a defect, not a cosmetic issue.** The
concept pages are the most information-dense in the project and were the worst
affected: each opened on its own `(concept-fret)=` anchor, its formulas read as
`\frac{1}{\tau_D}`, its admonitions as `:::{note}`, and its cross-references as
`{ref}`concept-x``. The renderer's contract is that none of those four ever
appear, and two tests hold it over the whole shipped tree.

**Inline mathematics is text; display mathematics is a picture.** `\tau_D` as an
image sits on its own baseline, in its own font, at a size that stops matching
the moment anything around it changes — so simple formulas are converted to
HTML (`τ<sub>D</sub>`) and only genuinely two-dimensional ones (fractions,
roots, sums with limits) are rasterised. Those are drawn onto a *transparent*
figure: `mathtext.math_to_image` bakes in a white background, which on a dark
theme is a bright card behind every equation.

**Qt paints a block background behind that block's own lines only.** An
admonition rendered as a `<div>` shows a coloured stripe behind its title and
leaves its content on the page background. Both renderers emit a single-cell
table instead — that is the one element Qt fills as one rectangle.

**A dead cross-reference degrades to words, never to markup.** If a label does
not resolve, the reader sees the caption, not `{ref}`something``.

# Failure modes seen here

* **An unknown directive is dropped silently.** Bare docutils parses at a report
  level where `.. seealso::` — which is how the manual points at the concept
  pages — produced *nothing at all*. The links were not broken; they were
  invisible. Registering the Sphinx-only directives is what made them appear.
* **A fence pairs with a fence.** Masking inline code before block fences let the
  closing back-ticks of a ```` ```{figure} ```` block pair with the opening ones
  as one enormous code span, so a whole figure directive rendered as pink
  monospace. Code and directive fences are the same syntax and are scanned in
  one pass.
* **Filtering a tree by a raw query string empties it.** "anisotropy g-factor"
  appears verbatim in no row, so matching rows against the string hid everything
  exactly when the search had found forty pages. The tree is filtered by the
  *result set*.
* **matplotlib's mathtext is a subset of LaTeX.** 153 of 1965 formulas in `docs/`
  failed to parse. They are rewritten before rendering (`normalise_latex`) —
  `\boldsymbol`, `\mathsf`, `\tfrac`, `\le`, `\lVert`, `\underbrace`,
  brace-less `\frac12`, and newlines, which are a parse error rather than
  whitespace. Mapping `\big(`/`\big)` onto `\left`/`\right` *creates* unbalanced
  input; the size modifier is dropped instead.
* **docutils renders maths as MathML by default, and Qt cannot lay that out.**
  It draws the leaf text of every node instead, so `\tau_x` arrived as "τ x" and
  a fraction as its numerator and denominator side by side — every formula in
  the *manual* was unreadable while the Markdown pages were fine. The writer is
  put into `math_output: MathJax`, whose delimited LaTeX our own typesetter
  picks up.
* **An emoji in a tree row restyles the row.** Qt falls back to a colour font
  for the whole item, with different metrics, so the navigation was set in a
  different face and size from the rest of the application. Sections are told
  apart by weight, not by icon.
* **Zoom has to re-render, not scale the widget.** Every size in the stylesheet
  is in points, so `QTextBrowser.zoomIn` moves the body text and leaves the
  headings, tables and formulas where they were. Ctrl+± re-renders the page at a
  new point size and re-typesets the formulas with it.

# Related

* [Help buttons and guided tours](gui-help-and-guides.md) — the `?` and the tour
  a plugin carries; the `?` modal opens its links in this browser.
* [Plugin documentation standard](../plugins/documentation-standard.md) — what a
  plugin must ship for its rows in this tree to be worth reading.
* [Testing](../workflows/testing.md) — the rule that a GUI change is unfinished
  until its screenshot has been looked at.
