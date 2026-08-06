---
type: Development Note
title: Refreshing the documentation
description: 'This page is written for an agent. It is the standing instruction for keeping ChiSurf''s documentation true: what to check, in what order, what counts as evidence, and what must never be done.'
tags: [development, documentation, maintenance]
audience: developer
anchor: documentation-maintenance
---

(documentation-maintenance)=
# Refreshing the documentation

This page is written for **an agent**. It is the standing instruction for
keeping ChiSurf's documentation true: what to check, in what order, what counts
as evidence, and what must never be done. A human maintainer can follow it too,
but the wording assumes an automated reader because that is who will run it most
often.

The documentation is large — 340 pages, 202 figures, 464 tables, 383 code
blocks — and it goes stale silently. Nothing fails when a screenshot shows last
year's toolbar; the reader simply loses trust. Everything below exists to make
staleness *detectable*.

---

## The standing prompt

Copy this verbatim into a new session when the documentation needs a refresh.

> You are refreshing the ChiSurf documentation. Work in this order and do not
> skip a stage:
>
> 1. **Run the checks.** `pytest chisurf/plugins/core/help/test test/test_docs_okf.py`
>    and `python build_tools/docs/make_registers.py --check` and
>    `python build_tools/docs/make_bibliography.py --check` and
>    `python -m sphinx -b html -q docs <tmp>`. Every failure is a defect in the
>    documentation, not in the checks. Fix them before anything else.
> 2. **Take the register as your worklist.** `docs/reference/figures.md` lists
>    every image with its origin; anything **unrecorded** or **⚠️ missing** is
>    the first thing to fix. `docs/reference/code.md` says which blocks are
>    verified. `csc help review-list --status unreviewed` says which pages have
>    never been read.
> 3. **Regenerate what is generated** — plots with
>    `python docs/guides/make_figures.py`, GUI screenshots with
>    `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python docs/guides/make_screenshots.py`,
>    the plugin catalogue with `python build_tools/docs/generate_plugin_docs.py`,
>    then the registers, the Literature page and
>    `python build_tools/docs/okf_frontmatter.py`.
> 4. **Verify every screenshot you touched by looking at it.** Open the PNG and
>    read it. A screenshot that does not show what its caption claims is worse
>    than no screenshot. If the interface has changed, retake it from the recipe
>    in {src}`docs/references/figures.yaml` and update the caption in the same change.
> 5. **Read the pages you changed, end to end**, and record what you read:
>    `csc help review-set <page> --ai`. Never record a page you did not read.
>    Never record `--reviewer` (a human sign-off) on your own behalf.
> 6. **Leave the worklist better than you found it.** Append what you did to
>    `okf/log.md` and update the "Where to pick this up" section of
>    `okf/subsystems/documentation-browser.md`.

---

## Rules

### The page header

**Every Markdown page carries a short OKF header, and it is generated.**

```yaml
---
type: Guide
title: Fusing bursts the same molecule produced
description: A burst folder in which one passage through the confocal spot is one burst…
tags: [guides, bursts, fusion]
anchor: guide-burst-fusion
---
```

`docs/` is an [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog)
bundle: a corpus a machine can navigate, not only a website. The header is what
makes it one, and it is read by the assistant behind the help browser's **Ask**
panel ({ref}`the guide <guide-ask-the-documentation>`), which routes a question
to a *kind* of page — a `Concept` explains, a `Guide` instructs, a
`Plugin Reference` enumerates controls — before it reads anything. Without a
header the page is reachable only by matching the reader's words against its
words, which is exactly the lookup that fails.

The header is **metadata and never prose**: Sphinx keeps it out of the rendered
HTML and the help browser strips it, so a reader never sees it.

Do not write one by hand. {src}`build_tools/docs/okf_frontmatter.py` derives it
from the page — `type` from the directory, `title` from the first heading,
`description` from the lead paragraph, `tags` from the name and title — and
writes it in:

```bash
python build_tools/docs/okf_frontmatter.py            # write, keeping hand edits
python build_tools/docs/okf_frontmatter.py --check     # fail on a page without one
python build_tools/docs/okf_frontmatter.py --refresh   # re-derive every field
```

Rules that follow from this:

* **A hand-edited field survives a re-run**, so improve a description that reads
  badly — the derivation takes the author's first sentence, which is usually
  right and occasionally is a sentence about something else. `--refresh`
  discards those edits; use it only when the derivation itself changed.
* **A generated page's header comes from its generator**, not from the injector
  — {src}`build_tools/docs/generate_plugin_docs.py`,
  {src}`build_tools/docs/make_registers.py`,
  {src}`build_tools/docs/make_bibliography.py`. Injecting one would be
  overwritten by the next regeneration.
* **`okf_version` lives only in `docs/index.md`**, the bundle root, and is
  quoted (unquoted, `0.10` would read as `0.1`).
* `test/test_docs_okf.py` is the guardrail: it fails on a page with no header,
  on a header with no `type`, on a description too thin to rank on, and on a
  title that disagrees with the page's first heading.

### Figures

**Every image is in the register, with an origin.** {src}`docs/references/figures.yaml`
is the source of truth; `docs/reference/figures.md` is generated from it. An
image used by a page but absent from the file shows as *unrecorded*, and the
build's `--check` mode fails when the register is stale.

An entry must carry enough for the figure to be **remade without asking anyone**:

```yaml
guides/figures/fcs_model_editor.png:
  caption: The composable FCS model editor, with the Diffusion section set to
    Gauss and the Equation box showing the assembled G(τ).
  origin: docs/guides/make_screenshots.py::fcs_model_editor
  kind: screenshot
  recipe: >
    Launch ChiSurf offscreen, open the FCS experiment, add the
    "3D Gauss, 1 bunching" model, expand the Diffusion and Equation sections,
    and grab the model editor widget at 900×600.
  pages: [docs/guides/09_diffusion_fcs.md]
```

* `origin` is `script.py::function` when a script draws it. If nothing draws it,
  say what does — a plugin, a document it was extracted from, an external source.
* `recipe` is prose, and it is written **for someone who has never seen the
  figure**. Name the tool, the data, the state, the size. "Screenshot of the
  model editor" is not a recipe; the block above is.
* `kind` is `plot`, `screenshot`, `diagram` or `legacy screenshot`. A *legacy*
  screenshot came out of the old Word manual and shows an interface that no
  longer exists — those are the ones worth replacing first.

**When a page talks about the interface, it shows the interface.** Describing a
panel in words when a picture would do is a defect. Take the screenshot
headlessly (`QT_QPA_PLATFORM=offscreen`, `widget.grab().save(...)`), drive the
widget into a *realistic* state — real data loaded, the analysis actually run —
and register it.

**A figure fills the reading column, and clicking it opens it full size.** The
browser scales a block figure *up* as well as down, so a plot saved at 470
pixels no longer sits as a thumbnail in an 860-pixel measure — but that also
means a figure saved too small is now visibly soft. Save plots at a width of
about 900–1200 px. Whatever the column cannot show, the reader gets by
clicking: the figure opens in a window sized to the screen, with zoom and
actual-size.

**Look at every screenshot you produce.** Not "the test passed": open the image
and read it. Clipped labels, a status box eating the panel, an upside-down plot
and overlapping tab bars are invisible to assertions and obvious in an image.

### Tables

Every table is listed in `docs/reference/tables.md` with the section it belongs
to. Generated tables — the plugin catalogue, the parameter glossary, the
Literature page, the registers themselves — are rebuilt by their generators and
must never be hand-edited. A written table is checked when its page is reviewed;
if it lists parameters or settings, check it against the code, not against
memory.

### Code blocks

**Every Python block is verified** (`test_doc_code.py`): it must parse, and
every `chisurf.…` name it uses must exist. That check is what catches a module
that moved — it has already caught two.

Mark a self-contained block ```` ```python run ```` and it is **executed** in a
temporary directory as part of the suite. Do that whenever the snippet can stand
alone. Leave the marker off when it needs a measurement, a GUI or the reader's
own file; it is still parsed and its names are still checked.

A block that is not Python — a shell command, a signature sketch, an IPython
magic — carries the honest language tag (`bash`, `text`, `ipython`), because a
block claiming to be Python is a block that claims to run.

### Literature

Citations are keys into {src}`docs/references/bibliography.yaml`; write
`` {cite}`key` ``, never a reference by hand. Add a work by adding an entry and
regenerating ({src}`build_tools/docs/make_bibliography.py`).

**Never invent a DOI.** Verify it against Crossref
(`https://api.crossref.org/works/<doi>`) and compare the returned title with the
entry. An entry with no verified identifier simply omits `doi:` and the page
links to a title search instead — a reader sent to a search finds the paper; a
reader sent to the wrong DOI does not know they are lost. Watch for
supplementary-material identifiers (`…s001`): they point at the SI, not the
article.

### Links

* A link to **source** opens the code editor:
  `` [`sample_fit`](chisurf/core/fitting/fit.py#sample_fit) ``. Address it by
  **symbol**, never by line number — a line number is wrong the moment anything
  above it is edited, and it fails *silently*; a symbol that is renamed fails
  loudly and the reader is told.
* A link to another **page** is an ordinary Markdown link or a `{doc}` /`{ref}`
  role. Both resolve in the browser and on the website.
* A **guided tour** may carry links too: `{"cite": "hellenkamp2018"}`,
  `{"doc": "..."}`, `{"src": "...#symbol"}`, `{"url": "https://…"}`. Use them
  to hand over to the reasoning instead of growing the bubble into an essay.

### Review

Two levels, and they mean different things:

| Level | What it claims | Who records it |
| --- | --- | --- |
| `ai-reviewed` | Read end to end and corrected against the source code. | An agent, with `csc help review-set <page> --ai` |
| `reviewed` | Checked against the *running application*: screenshots match, the procedure works. | A human, with `--reviewer <name>` |

An agent must never record the second. Either level lapses automatically when
the page is edited, so sign off page by page rather than in a sweep.

### What ships with the application

The help browser reads these pages from disk, so an installed ChiSurf has to
carry them: the build copies a selection of `docs/` into the package itself, at
`chisurf/docs`, and the browser prefers that copy over any source tree. A
checkout has no such copy — `docs/` stays the single place a page is edited.

The selection lives in {src}`_shipped_docs.py#iter_shipped_docs`: pages,
figures and the data files the renderer resolves against (the bibliography, the
figure register, review status). Left out are Sphinx build output, the retired
Word manual, the Sphinx extensions, and the manual's `.emf` figures — a vector
format no browser draws, which is why `docs-manual` converts them to PNG.

Practical consequence when adding documentation: **a page in a format the
selection does not list ships as a broken link, not as an error.** A guardrail
test (`test_packaging.py`) fails if anything the table of contents lists is not
carried, so add the suffix there rather than working around it.

---

## What the checks are

| Command | What it protects |
| --- | --- |
| `pytest chisurf/plugins/core/help/test` | Rendering, structure, cross-references, citations, code blocks |
| `pytest test/test_docs_okf.py` | Every page carries a conformant OKF header, and it never reaches the reader |
| `python build_tools/docs/okf_frontmatter.py --check` | The same, as a build step |
| `python build_tools/docs/make_registers.py --check` | The figure, table and code registers are current |
| `python build_tools/docs/make_bibliography.py --check` | The Literature page matches the bibliography |
| `python -m sphinx -b html -q docs <out>` | The published site builds without a warning |
| `csc help review-check` | No unreviewed page ships |

All of them are cheap. Run them before you start, so you know what was already
broken, and after you finish, so you know what you changed.
