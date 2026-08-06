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

* `pytest chisurf/plugins/core/help/test` — 743 tests. Five are the real
  guardrails, all in `test_render.py`: **every formula in `docs/` typesets**;
  **no page in the tree leaks its markup** — no fence, no `$$` and no surviving
  role, checked over *every* `.md` and `.rst` through the same chain the browser
  uses, because the version that checked three known markers on the pages it
  already knew about missed `:src:` reaching the reader in the manual;
  **inline mathematics stays text**; **every `{cite}` and `{src}` resolves** (a
  source link by *symbol*, so a rename fails here rather than opening the right
  file at the wrong line); and **no reference is written out by hand** — neither
  as a bare DOI link nor as "Author, A. (1999). Title. *Journal*…", both of
  which drift away from the entry they duplicate.
* `pytest chisurf/plugins/core/help/test/test_docs_crosslinks.py` — 188 tests:
  every concept points at a guide, every guide at a concept, and every
  `{doc}`/`{ref}`/`[…](….md)` resolves to a page that is there.
* `python -m sphinx -b html -q docs <out>` must be **warning-free**. The tree
  and the website are built from the same toctrees, so a warning there is a
  wrong tree here.

**What is open.**

1. **The manual is AI-reviewed and awaits a human** — `csc help review-list`
   reports `0 reviewed, 94 AI-reviewed, 0 stale, 231 unreviewed` over the whole
   tree; the manual's own 79 are all AI-reviewed. All 79 pages
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
2. **The rest of the documentation has not had its first pass.** Review tracking
   now covers `fundamentals`, `concepts`, `guides`, `getting_started`,
   `reference` and `references` as well as `manual`; `csc help review-list`
   reports `0 reviewed, 92 AI-reviewed, 6 stale, 241 unreviewed (339 tracked)`.
   **The 11 `fundamentals` pages have had no pass at all** — they were written
   in one sitting against the source text (see the mining record below) and
   nobody, human or agent, has since read them for correctness. They are the
   cheapest pages to check, because each states a standard result that can be
   verified against the cited primary paper rather than against the running
   application. **15 of the 36 concept pages are done**;
   the pass is worth continuing in that order (concepts, then the 63 guides,
   then `reference`) because a concept page is where the physics that a guide
   only applies is actually stated. What the finished ones needed, and therefore
   what to look for: **numbers that do not reproduce** (recompute every worked
   table — the accessible-volume Jensen table was off in three cells and did not
   say how it had been produced), **a citation pointing at a plausible
   neighbour** of the intended paper (`qian1990` was the wrong Qian & Elson
   1990), **a threshold credited to the wrong paper** (`frc_resolution` gave van
   Heel the fixed 1/7), and **pages with no pointer into their implementation at
   all**. Record a page only after reading it end to end:
   `csc help review-set <path> --ai`. The remaining 231 are not known to be
   *wrong*: an audit over all 340 pages (stubs, holes in sentences, dead links
   and cross-references, missing images, markup leaks, inline formulas as
   images, broken heading ids) found and fixed everything it could detect. What
   they have not had is somebody reading them for *correctness*, which is what
   `--ai` records.
3. **The Lakowicz pass is complete.** The two gaps recorded on 2026-08-06 are
   written: `concepts/maximum_entropy.md` (with `guides/62_maxent_decay.md`) and
   `concepts/energy_migration.md`. Both plugins were renovated with them —
   `maxent_decay` lost a bespoke `HelpDialog` that pasted `--help` output into a
   `QTextEdit`, and both are struck from `test/plugin_help_guide_allowlist.txt`
   (87 → 85). What the pass did *not* cover, and would be the next source rather
   than the next gap: frequency-domain lifetimes, spectral relaxation in depth,
   and transfer to acceptors distributed in one, two or three dimensions — the
   last is named in one paragraph of `concepts/energy_migration.md` and
   deliberately not developed, because no ChiSurf model fits it today. Adding
   one is what would justify the page.

4. **58 plugins ship without a README** and **80 GUI plugins have no `?` page or
   guided tour** (`test/plugin_help_guide_allowlist.txt` is the shrinking
   tracker for the second, owned by
   [help buttons and guided tours](gui-help-and-guides.md)). Every plugin *is*
   now in the catalogue: the generator used to walk `manifest.json` only, so 13
   plugins that declare themselves in code appeared in the menus but had no
   reference page at all.
5. **The RST manual has no `docs/manual/_images` scaling policy.** Screenshots
   are full-resolution and arrive as big blocks with a lot of air around them;
   `_constrain_image_widths` bounds the width but the vertical rhythm around a
   block image is still loose.
6. **Only `.md` files are indexed for cross-reference labels**
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
| Literature | `api/bibliography.py` | One entry per cited work; expands `{cite}` and says where the paper can be got. |
| Source links | `api/source_links.py` | Resolves `path#symbol` to a file and a line, by parsing rather than by counting; labels the link with the path as written, in both renderers. |
| Window | `gui/tool.py` | Address bar, tree, start page, search, history, previous/next, authoring tools. |

# Decisions worth keeping

**Five layers, and "Fundamentals" is one of them.** The tree is
*Getting started → Fundamentals → Concepts → Guides → Reference → Literature*,
answering in order: how do I run it, why does the signal behave like this, which
model and what do its parameters mean, which control in which order, and what is
the exact name. `docs/fundamentals/` was added on 2026-08-06 and holds 11 pages
in four groups — the excited state, orientation and transfer, probe and
environment, measuring photons — plus `conventions.md`.

The layer exists because `docs/concepts/index.rst` had a rubric *called*
"Fundamentals" that contained method pages (`fret`, `fcs_saturation`,
`parameter_uncertainty`), so the physics every concept assumed was stated
nowhere and was being partially restated in each concept that needed it. The
rubric is now "Core methods" and the physics sits one layer below it. A concept
page links **down** to a fundamentals page for grounding; a fundamentals page
links **up** to the concepts that rest on it, and does not duplicate their
model or their fitting detail.

The physics was mined from one source — Lakowicz, *Principles of Fluorescence
Spectroscopy*, 3rd ed. (bibliography key `lakowicz2006`), sitting in the
gitignored `junk/` as `doc-800.pdf`. What was taken, chapter by chapter, and
what was read and deliberately **not** taken, is recorded in
`junk/doc-800.pdf.CHISURF.md` — a sidecar rather than an in-file header, because
the reference is a 960-page PDF and cannot carry one. The `SKIPPED` half is the
half that pays: it records that the frequency-domain, metal-enhanced and
surface-plasmon chapters were checked and are out of scope, that the 2006
instrumentation detail is superseded by diode lasers and SPADs, and that the
book's `θ` and its Å-based Förster prefactor were seen and rejected in favour of
ChiSurf's spellings. Seven primary papers the book cites were added to
`docs/references/bibliography.yaml`; DOIs were recorded only for the three that
are certain, per that file's own rule.

**Figures are generated, and their provenance is a file.** No image in the
documentation is drawn by hand or pasted in. A plot is a function in
`docs/guides/make_figures.py`, a screenshot is a function in
`docs/guides/make_screenshots.py`, and both write into `docs/guides/figures/` —
concept and fundamentals pages use that one directory too, rather than each
growing its own. `docs/references/figures.yaml` records, per image, the caption,
the `script::function` that produced it, and the *recipe*; the register at
`docs/reference/figures.md` is generated from that file plus a scan of the
pages, so an image used without an entry is listed as **unrecorded** and that
list is the worklist.

Two things this catches that a hand-made figure cannot. A figure computed by the
same functions the reader will call cannot drift away from the prose: the
worked lifetime averages, the FRET efficiencies at $0.5R_0$ and $2R_0$, and the
$\kappa^2$ distance errors are all printed by the generator and quoted from it.
And a stochastic figure needs its seed recorded or it is not reproducible — the
cone model samples orientations, so `fig_kappa2_models` fixes the seed and
`figures.yaml` says so.

The scan is driven by `SECTIONS` in `build_tools/docs/make_registers.py`. It did
not include `fundamentals` when that layer was added, so five of its figures
registered as used-nowhere while looking fine on the page — **a new
documentation directory has to be added there as well as to the toctree**, or
its figures silently leave the provenance system.

**Symbols are ChiSurf's, and the alternatives are recorded rather than
harmonized.** `docs/fundamentals/conventions.md` is a translation table, not a
standard: it says ChiSurf writes `ρ` where the classical literature writes `θ`,
`a_i` where papers write `α_i`, `Q_D` where they write `Φ_D`, and it names the
collisions that a multiparameter experiment makes ambiguous — `γ` is both the
FRET detection factor and the FCS structure parameter, `α` is both leakage and
the anomalous exponent, `r_0` is both the fundamental anisotropy and (elsewhere)
a beam waist. The point of the page is that a number which fails to reproduce is
usually a convention mismatch and not an error, and that the pages must
therefore agree with the *code's* spelling rather than with any one textbook's.
It also records where ChiSurf is internally inconsistent: the Förster prefactor
`0.02108` yields nm, and `forster_radius()` returns Å.

**The tree is the documentation's own table of contents.** It is parsed from the
`toctree` directives that build the published HTML, not from a directory walk.
That is what makes *one* fix serve both surfaces, and it is why the manual's
chapters live in `docs/manual/index.rst`: `build_tools/docs/convert_manual.py`
writes `index.generated.rst` beside it and never over it, because the chapter
structure exists nowhere in the source document.

**And so are the sections.** The top level was a hard-coded tuple long after
the levels below it were being read from the source, which is exactly how
`docs/fundamentals/` came to be published on the website and absent from the
application — silently, with nothing failing. Sections and their order now come
from `docs/index.rst`. What stays in code is the *wording*: the website's
captions are parenthetical ("Concepts (theory)") where a navigation row reads
better with a dash, and a summary line has nowhere to live in a caption at all.
A section nobody has worded yet still appears, under its caption.

**A group comes from the page, not from a list here.** A `.. rubric::` or a `##`
heading above a toctree names the group under it, and a `:caption:` does the
same. Nothing in the code enumerates "Fundamentals", "Correlation methods" or
"Worked example — calibrating an FCS setup".

**Two rows with the same words are not navigation.** The manual arrived with
three pages called *Overview* and two called *Calculations*; they are retitled at
the source, and `test_toc.py` fails if a section ever contains two pages with
one title.

**A formula wider than the text column is stacked, not shrunk.** Qt gives the
*whole page* a horizontal scrollbar when one image overflows, so every paragraph
on it starts sliding sideways. A display row is therefore split at the
``\qquad``/``\quad`` its author used to set two formulas side by side — the
answer a typesetter would give — and only a single indivisible formula that is
still too wide is scaled down. The split is made at brace depth zero, and never
at a thin space, which would leave an arrow or a comma alone on a line.

**mathtext's gaps are filled by rewriting, and the rewrites have to be
brace-matching.** ``\underbrace{X}_{label}`` became ``\underset{label}{X}``
through a regex with one level of nesting baked in, so a term containing a
fraction inside a delimiter fell through and the label came out as a *subscript*
stuck to the end of the expression — "amplitudedecay" beside the RICS model
rather than under it. Two more of the same kind: a matrix keeps its shape as
``[a, b; c, d]`` instead of collapsing to ``[abcd]``, and a space inside
``\text{…}`` survives as ``\ ``, because mathtext drops ordinary spaces in
maths mode.

**Zoom is Ctrl *and* Shift.** Ctrl+scroll is the browser convention, but on a
trackpad the operating system's screen magnifier claims it and the gesture never
reaches the application — so the browser looks like it has no zoom at all.
Shift+wheel arrives on the *horizontal* delta on most mice, so either axis
zooms.

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

**A citation is a key, not a formatted string.** Every work the documentation
cites lives once in `docs/references/bibliography.yaml`; a page cites it with
`` {cite}`key` `` and the **Literature** section lists them all. The role is
expanded by the same module in both renderers — `docs/_ext/cite_role.py` for
Sphinx, `api/bibliography.py` for the browser — so a reference reads and links
identically on the website and in the application, and there is one place to
correct it. Each entry links to its **DOI**, or, when no identifier is recorded,
to a literature search for the title: a reader who wants the paper wants a way
to *get* it, and sending them to the wrong DOI is worse than sending them to a
search. `build_tools/docs/make_bibliography.py` writes the page; `--check` fails when it
is stale. The entries were **verified against Crossref**, not written from
memory: of 29 DOIs recorded by hand one resolved to nothing (`kalinin2004`) and
was corrected, 37 entries that had no identifier got one at a title match of
1.00, and two supplementary-material DOIs (`…s001`) were reduced to their
article. 23 further works were harvested from the code and plugin help that
already cited them — Rabiner's HMM tutorial, SQUAREM, DE-MC, the phasor paper,
2D-FLCS, the IRF-from-decay method — bringing the bibliography to **92 works**.

**The `?` modal renders like the browser.** It used Qt's own
`setMarkdown`, which knows no MyST, so a plugin's help page showed
`:::{note}`, `` {cite}`key` `` and raw LaTeX as literal text — the same defects
that had been fixed in the browser, in the window most readers actually open.
`chisurf/gui/widgets/tools/help_render.py` is the one entry point every widget
that displays a help page now goes through, and it degrades to Qt's Markdown
only if rendering genuinely fails.

**A link to code is addressed by symbol and opens the editor.**
`` {src}`chisurf/core/fitting/fit.py#sample_fit` `` opens the **code editor** at
the definition — reusing the editor that is already open, in a new tab, so
following three references leaves one editor with three tabs. A line number
would be wrong the moment anything above it were edited and would fail
*silently*; a renamed symbol fails loudly and the reader is told. The same role
renders on the website as a link into the repository browser
(`docs/_ext/src_role.py`).

**Every page has an address, and the address bar accepts it.** A documentation
path, a source path with a `#symbol`, a `cite:` key or a URL — the same
vocabulary the links use — with completion over every page in the tree. It is
what makes a page quotable in a bug report.

**A guided tour may carry links.** `{"cite": …}`, `{"doc": …}`, `{"src": …}`,
`{"url": …}` under a step; the tour says *which control to press* and the link
hands over to why, instead of the bubble growing into an essay.

**The documentation has three registers, and they are what make it
refreshable.** `docs/reference/figures.md` (every image, its caption and **where
it came from**), `tables.md` and `code.md` are generated by
`build_tools/docs/make_registers.py`; provenance for figures is kept by hand in
`docs/references/figures.yaml`, and an image used without an entry is listed as
*unrecorded*. A recipe must name the tool, the data and the state — enough to
retake the figure without asking anyone — and a test fails on a recipe shorter
than eight words. **Python code blocks are verified**: every one is parsed, every
`chisurf.…` name it uses must resolve, and a block marked ```` ```python run ````
is executed. That check has now caught four broken snippets and two moved
modules.

**The refresh procedure is written down for an agent**
(`docs/development/documentation_maintenance.md`): the standing prompt, the
order of the checks, what counts as evidence, and the rule that an agent records
`--ai` and never a human sign-off.

**Markup that reaches the reader is a defect, not a cosmetic issue.** The
concept pages are the most information-dense in the project and were the worst
affected: each opened on its own `(concept-fret)=` anchor, its formulas read as
`\frac{1}{\tau_D}`, its admonitions as `:::{note}`, and its cross-references as
`{ref}`concept-x``. The renderer's contract is that none of those four ever
appear, and two tests hold it over the whole shipped tree.

**Inline mathematics is text; display mathematics is a picture.** An image in
the middle of a sentence sits at its own baseline, in its own font, at a size
that stops matching the moment anything around it changes — and a tall one (a
fraction, a sum with limits) shoves the line apart and floats above the words.
So inline formulas are converted to **HTML text**: `τ<sub>D</sub>`, slashed
fractions with precedence-preserving brackets (`(a+b)/c`), big operators with
their limits as ordinary sub/superscripts, combining accents for `\hat`/`\bar`,
upright function names. That takes the documentation from **102 rasterised
inline formulas to 5** — matrices, which are genuinely two-dimensional and get
`vertical-align: middle` so they at least sit on the line. Display mathematics
*is* rasterised, onto a **transparent** figure: `mathtext.math_to_image` bakes in
a white background, which on a dark theme is a bright card behind every
equation.

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
  different face and size from the rest of the application. The icons are worth
  keeping — they are how the parts are told apart at a glance — so they live in
  the item's **icon role**, painted into a pixmap by `emoji_icon`, never in its
  text. The same trick carries the review badge on a page row.
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
