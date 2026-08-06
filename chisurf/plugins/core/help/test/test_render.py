"""Tests for how a documentation page is turned into what the reader sees.

Each of these covers something that was showing on screen as raw markup: a MyST
target, an admonition fence, a LaTeX formula, a cross-reference role. They are
written against the *rendered output* rather than the pipeline, because that is
what the defect looked like.
"""

import pathlib

import pytest

from chisurf.plugins.core.help.api import theme as theme_api
from chisurf.plugins.core.help.api.markdown import render_body, render_markdown
from chisurf.plugins.core.help.api.mathtext import (
    MathRenderer,
    html_math,
    math_rows,
    normalise_latex,
    split_math,
)
from chisurf.plugins.core.help.api.rst import render_rst


# ── MyST constructs ─────────────────────────────────────────────────


def test_cross_reference_target_is_not_shown():
    """``(concept-fret)=`` is an anchor; every concept page opened on it."""
    html = render_body("(concept-fret)=\n# FRET\n\nText.\n")
    assert "(concept-fret)=" not in html
    assert 'name="concept-fret"' in html


def test_admonition_becomes_a_box_not_a_fence():
    html = render_body(":::{note}\nMind the gap.\n:::\n")
    assert ":::" not in html
    assert "admonition" in html and "Note" in html
    # A one-cell table: Qt paints a div's background behind its own line only.
    assert "<table" in html and "<td" in html


def test_admonition_keeps_its_own_title():
    html = render_body("```{seealso}\nTheory\n\nMore.\n```\n")
    assert "See also" in html


def test_figure_directive_renders_the_image_and_caption():
    html = render_body(
        "```{figure} figures/x.png\n:name: fig-x\n:width: 90%\n\nThe caption.\n```\n"
    )
    assert "<img" in html and 'src="figures/x.png"' in html
    assert "The caption." in html
    assert 'name="fig-x"' in html
    assert "{figure}" not in html


def test_a_directive_fence_is_not_read_as_inline_code():
    """The closing back-ticks used to pair with the opening ones as a code span."""
    text = "Before.\n\n```{figure} figures/x.png\n\nCaption.\n```\n\nAfter.\n"
    html = render_body(text)
    assert "<code>" not in html
    assert "After." in html


def test_code_fence_survives_intact():
    html = render_body("```python\nx = 1  # {note}\n```\n")
    assert "<pre>" in html and "x = 1" in html
    assert "admonition" not in html


def test_toctree_is_navigation_and_is_dropped():
    html = render_body("```{toctree}\n:maxdepth: 1\n\nsomething\n```\n\nText.\n")
    assert "toctree" not in html
    assert "Text." in html


def test_tables_render_as_tables():
    html = render_body("| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert "<table>" in html and "<th>" in html


# ── mathematics ─────────────────────────────────────────────────────


def test_inline_maths_is_text_not_a_picture():
    """An image sits at its own baseline and in its own font; text does not."""
    renderer = MathRenderer()
    out = renderer.to_html(r"\tau_D", display=False)
    assert "<img" not in out
    assert "τ" in out and "<sub>" in out


def test_inline_maths_almost_never_becomes_an_image():
    """A picture in the middle of a sentence is what "horrible" looked like.

    An inline image sits at its own baseline, at its own size, and a tall one
    (a fraction, a sum with limits) shoves the line apart and floats above the
    words around it. Inline mathematics is therefore converted to HTML text —
    slashed fractions, sub/superscript limits, combining accents — and only
    genuinely two-dimensional constructs (matrices) may fall through.
    """
    import re

    from chisurf.plugins.core.help.api.toc import docs_root

    rasterised = []
    for page in sorted(docs_root().rglob("*.md")):
        text = re.sub(r"```.*?```", " ", page.read_text(encoding="utf-8"), flags=re.DOTALL)
        text = re.sub(r"`[^`\n]*`", " ", text)
        for kind, payload in split_math(text):
            if kind != "inline":
                continue
            if html_math(payload.strip()) is None:
                rasterised.append((page.name, payload.strip()[:60]))
    assert len(rasterised) <= 6, rasterised


def test_a_fraction_in_a_sentence_is_slashed_not_stacked():
    assert html_math(r"x_i = a_i/\sum_j a_j") is not None
    assert html_math(r"\frac{\tau_{DA}}{\tau_D}") == (
        "τ<sub><i>D</i><i>A</i></sub>/τ<sub><i>D</i></sub>"
    )
    # ...and precedence is kept when the slash would otherwise change the sense.
    assert html_math(r"\frac{a+b}{c}") == "(<i>a</i>+<i>b</i>)/<i>c</i>"


def test_an_inline_image_is_centred_on_the_line():
    """The few that remain must not hang below the baseline."""
    renderer = MathRenderer()
    out = renderer.to_html(r"\begin{pmatrix}a & b\\ c & d\end{pmatrix}", display=False)
    if "<img" in out:
        assert "vertical-align: middle" in out


def test_display_maths_is_typeset():
    renderer = MathRenderer()
    out = renderer.to_html(r"E = \frac{1}{1 + (R/R_0)^6}", display=True)
    assert "<img" in out and "data:image/png;base64," in out


def test_typeset_maths_has_no_opaque_background():
    """A white card behind every formula is what a dark theme showed before."""
    import base64
    import io

    renderer = MathRenderer(colour="#ffffff")
    out = renderer.to_html(r"\sqrt{x}", display=True)
    payload = out.split("base64,")[1].split('"')[0]
    data = base64.b64decode(payload)
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    assert image.getpixel((0, 0))[3] == 0


def test_latex_the_engine_cannot_read_is_rewritten():
    for source in (r"\tfrac12", r"\lVert x\rVert", r"\big(x\big)", r"a \le b"):
        assert MathRenderer()._image_tag(source, False) is not None, source


def test_every_formula_in_the_documentation_typesets():
    """A page of unreadable LaTeX is worse than no page; keep it at zero."""
    import re

    from chisurf.plugins.core.help.api.toc import docs_root

    renderer = MathRenderer()
    failures = []
    for page in sorted(docs_root().rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        text = re.sub(r"`[^`\n]*`", " ", text)
        for kind, payload in split_math(text):
            if kind == "text":
                continue
            for row in (math_rows(payload) if kind == "display" else [payload]):
                if kind == "inline" and html_math(row) is not None:
                    continue
                if renderer._image_tag(row, kind == "display") is None:
                    failures.append((page.name, row[:60]))
    assert not failures, failures[:5]


def test_multiline_display_maths_becomes_several_lines():
    rows = math_rows(r"a = b \\ c = d")
    assert rows == ["a = b", "c = d"]
    assert "\n" not in normalise_latex("a = b\n\\qquad c = d")


# ── reStructuredText ────────────────────────────────────────────────


def test_rst_seealso_is_rendered_not_dropped():
    """Unknown directives are dropped silently; the manual's links were in one."""
    html = render_rst("Title\n=====\n\n.. seealso::\n\n   Read this.\n")
    assert "See also" in html and "Read this." in html


def test_rst_reference_role_becomes_a_link():
    html = render_rst(
        "Title\n=====\n\nTheory: :ref:`concept-fcs-correlation`.\n"
    )
    assert "<a" in html and "fcs_correlation.md" in html
    # And it reads as the page, not as the label.
    assert "concept-fcs-correlation<" not in html


def test_rst_page_title_is_a_first_level_heading():
    """Manual pages were split out mid-document and kept their depth."""
    html = render_rst('Deep page\n"""""""""\n\nText.\n')
    assert "<h1" in html


def test_rst_gets_the_theme():
    html = render_rst("Title\n=====\n\nText.\n", theme=theme_api.DARK)
    assert theme_api.DARK.background in html


# ── page assembly ───────────────────────────────────────────────────


def test_rendered_page_carries_the_running_theme():
    html = render_markdown("# Title\n\nText.\n", theme=theme_api.DARK)
    assert theme_api.DARK.background in html
    assert theme_api.DARK.link in html


def test_front_matter_is_metadata_not_prose():
    html = render_body("---\ntitle: x\n---\n\n# Real title\n")
    assert "title: x" not in html


def test_real_pages_render_without_leaking_markup():
    """Spot-check the shipped pages for markup that reached the reader."""
    from chisurf.plugins.core.help.api.toc import docs_root

    renderer = MathRenderer()
    offenders = []
    pages = sorted(docs_root().glob("concepts/*.md")) + sorted(
        docs_root().glob("guides/*.md")
    )
    for page in pages:
        html = render_body(page.read_text(encoding="utf-8"), math=renderer)
        for marker in (":::{", "```{", "$$"):
            if marker in html:
                offenders.append((page.name, marker))
    assert not offenders, offenders[:5]


def test_documents_dispatch_on_suffix():
    from chisurf.plugins.core.help.api.render import render_document

    assert "<h1" in render_document("# Title\n", pathlib.Path("x.md"))
    assert "<h1" in render_document("Title\n=====\n", pathlib.Path("x.rst"))


# ── citations ───────────────────────────────────────────────────────


def test_a_citation_becomes_a_link_to_the_paper():
    """``{cite}`key``` is the one way a page cites, in both renderers."""
    from chisurf.plugins.core.help.api import bibliography as bib

    entries = bib.bibliography()
    if not entries:
        pytest.skip("no bibliography in this checkout")
    key = "magde1972"
    assert key in entries
    expanded = bib.expand_citations(f"See {{cite}}`{key}`.")
    assert "doi.org" in expanded and "Magde" in expanded
    assert "{cite}" not in expanded


def test_a_work_without_a_doi_still_leads_somewhere():
    """A reader wants the paper, so an entry with no identifier gets a search."""
    from chisurf.plugins.core.help.api import bibliography as bib

    entry = bib.Entry(key="x", authors="A. Author", title="Some title", year="2020")
    url = bib.entry_url(entry)
    assert url.startswith("https://") and "Some+title" in url


def test_every_citation_in_the_documentation_resolves():
    """A key with no entry would render as a dead code span."""
    from chisurf.plugins.core.help.api import bibliography as bib
    from chisurf.plugins.core.help.api.toc import docs_root

    unknown = {}
    for page in list(docs_root().rglob("*.md")) + list(docs_root().rglob("*.rst")):
        if "_build" in page.parts:
            continue
        missing = bib.unknown_keys(page.read_text(encoding="utf-8"))
        if missing:
            unknown[page.name] = missing
    assert not unknown, unknown


def test_the_literature_page_lists_every_work():
    """The page is generated; a work added to the bibliography must appear."""
    from chisurf.plugins.core.help.api import bibliography as bib
    from chisurf.plugins.core.help.api.toc import docs_root

    page = docs_root() / "references" / "index.md"
    if not page.is_file():
        pytest.skip("no Literature page in this checkout")
    text = page.read_text(encoding="utf-8")
    for key, entry in bib.bibliography().items():
        assert f"({key})=" in text, key
        assert bib.entry_url(entry) in text, key


def test_a_heading_with_maths_keeps_a_usable_id():
    """A placeholder token inside an id spilled the attribute into the page."""
    html = render_body("## Where the reference $D$ comes from\n", math=MathRenderer())
    import re

    match = re.search(r'<h2[^>]*id="([^"]*)"', html)
    assert match, html
    assert "<" not in match.group(1) and match.group(1) == "where-the-reference-comes-from"
    # ...and nothing of the attribute leaked into the words the reader sees.
    visible = re.sub(r"<[^>]+>", "", html.split("</h2>")[0])
    assert visible.strip() == "Where the reference D comes from"


def test_no_page_writes_a_reference_by_hand():
    """A citation is a key, or the same paper gets said two different ways.

    A bullet whose whole content is a DOI link is a reference written out in
    place; it belongs in the bibliography with a key, so that the wording, the
    link and the entry on the Literature page cannot drift apart.
    """
    import re

    from chisurf.plugins.core.help.api.toc import docs_root, repository_root

    pattern = re.compile(r"^\s*[-*]\s.*\[10\.\d{4,9}/[^\]]+\]\(https?://[^)]*doi\.org[^)]*\)\s*$", re.M)
    offenders = []
    roots = [docs_root(), repository_root() / "chisurf" / "plugins"]
    for root in roots:
        for page in root.rglob("*.md"):
            if "_build" in page.parts or page.parent.name == "references":
                continue
            if pattern.search(page.read_text(encoding="utf-8")):
                offenders.append(str(page.relative_to(repository_root())))
    assert not offenders, offenders


def test_every_recorded_doi_looks_like_one():
    """A malformed identifier resolves to nothing and is silently a dead link."""
    import re

    from chisurf.plugins.core.help.api import bibliography as bib

    wrong = [
        (key, entry.doi)
        for key, entry in bib.bibliography().items()
        if entry.doi and not re.fullmatch(r"10\.\d{4,9}/\S+", entry.doi)
    ]
    assert not wrong, wrong
    # Supplementary-material identifiers point at the SI, not at the paper.
    supplementary = [
        (key, entry.doi)
        for key, entry in bib.bibliography().items()
        if re.search(r"\.s\d+$", entry.doi or "")
    ]
    assert not supplementary, supplementary


def test_the_help_modal_renders_like_the_browser(qapp=None):
    """A plugin's `?` shows the same dialect the browser does.

    The modal used Qt's own Markdown, which knows nothing of MyST: a plugin's
    help page showed `:::{note}`, `{cite}` and raw LaTeX as literal text —
    exactly the defects fixed in the browser, in the window most readers open.
    """
    from chisurf.gui.widgets.tools.help_render import render_help
    from chisurf.plugins.core.help.api.toc import repository_root

    page = (
        repository_root()
        / "chisurf/plugins/calculator/fcs_saturation_calc/gui/help.md"
    )
    if not page.is_file():
        pytest.skip("plugin not present in this checkout")
    html = render_help(page.read_text(encoding="utf-8"), page)
    assert html is not None
    for marker in ("{cite}", ":::{", "```{"):
        assert marker not in html, marker
    assert "doi.org" in html, "citations must resolve to links"
