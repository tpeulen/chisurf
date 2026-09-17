"""reStructuredText rendering for the Help browser.

The user manual is reStructuredText, not Markdown, so the browser needs a second
renderer. Rendering happens through plain ``docutils`` rather than Sphinx: a full
Sphinx build is far too slow for interactive browsing and needs the whole project
environment. The price is that Sphinx-specific roles and directives are unknown
to bare docutils, so the ones the manual actually uses are registered here as
no-op fallbacks that render their text instead of raising.
"""

from __future__ import annotations

import html as _html
import re

#: Sphinx roles that bare docutils does not know. Rendered as their text so a
#: cross-reference degrades to a readable label instead of an error marker.
_SPHINX_TEXT_ROLES = (
    "term",
    "mod",
    "class",
    "func",
    "meth",
    "attr",
    "data",
    "exc",
    "obj",
    "guilabel",
    "menuselection",
    "kbd",
    "file",
    "command",
    "samp",
    "abbr",
    "eq",
)

#: Sphinx directives bare docutils does not know, and what each becomes.
#: ``seealso`` matters most: the manual's cross-references to the concept pages
#: are written with it, and an unknown directive is *dropped silently* at the
#: report level the browser parses with -- so those links were invisible.
_SPHINX_ADMONITIONS = {
    "seealso": "See also",
    "versionadded": "Added in version",
    "versionchanged": "Changed in version",
    "deprecated": "Deprecated since version",
    "todo": "To do",
}

#: Directives that carry navigation or build metadata rather than prose.
_DROPPED_DIRECTIVES = ("toctree", "index", "only", "meta", "highlight", "tabularcolumns")

_roles_registered = False
_directives_registered = False


def _register_sphinx_roles() -> None:
    """Register no-op text roles so Sphinx markup does not break rendering."""
    global _roles_registered
    if _roles_registered:
        return
    try:
        from docutils import nodes
        from docutils.parsers.rst import roles
    except Exception:  # pragma: no cover - docutils missing
        return

    def _text_role(name, rawtext, text, lineno, inliner, options=None, content=None):
        # ``:role:`label <target>``` -> show the label only.
        match = re.match(r"^(.*?)\s*<[^>]*>$", text)
        label = match.group(1) if match else text
        return [nodes.literal(rawtext, label)], []

    def _reference_role(name, rawtext, text, lineno, inliner, options=None, content=None):
        """``:ref:``/``:doc:`` -> a link into the documentation.

        The manual points at the concept pages with these roles. Rendered as
        literal text they are dead ends, which is what they were: the reader
        was shown ``concept-fcs-correlation`` and left to find it.
        """
        from chisurf.plugins.core.help.api.xref import document_reference

        target, anchor, label = document_reference(name, text)
        if target is None:
            return [nodes.emphasis(rawtext, label)], []
        uri = str(target) + (f"#{anchor}" if anchor else "")
        return [nodes.reference(rawtext, label, refuri=uri)], []

    def _source_role(name, rawtext, text, lineno, inliner, options=None, content=None):
        """``:src:`path#symbol``` -> a link the browser opens in the code editor.

        Written the same way in a Markdown page and a manual page, so a reader
        cannot tell which renderer produced the link — and neither can a writer
        have to remember.
        """
        from chisurf.plugins.core.help.api.source_links import resolve

        body = text.strip()
        caption = ""
        if "<" in body and body.endswith(">"):
            caption, body = body[: body.index("<")].strip(), body[body.index("<") + 1 : -1]
        resolved = resolve(body)
        label = caption or (resolved.label if resolved else body)
        if resolved is None:
            return [nodes.literal(rawtext, label)], []
        return [nodes.reference(rawtext, "", nodes.literal(rawtext, label), refuri=body)], []

    def _cite_role(name, rawtext, text, lineno, inliner, options=None, content=None):
        """``:cite:`key``` -> the short citation, linked to where the work lives."""
        from chisurf.plugins.core.help.api.bibliography import (
            bibliography,
            entry_url,
            short_citation,
        )

        entries = bibliography()
        children: list = []
        for index, key in enumerate(k.strip() for k in text.split(",")):
            if not key:
                continue
            if index:
                children.append(nodes.Text("; "))
            entry = entries.get(key)
            if entry is None:
                children.append(nodes.literal(rawtext, key))
                continue
            children.append(
                nodes.reference(rawtext, short_citation(entry), refuri=entry_url(entry))
            )
        return children or [nodes.Text(text)], []

    for role_name in ("ref", "doc", "numref"):
        try:
            roles.register_local_role(role_name, _reference_role)
        except Exception:  # pragma: no cover
            continue

    for role_name, handler in (
        ("src", _source_role),
        ("code-src", _source_role),
        ("cite", _cite_role),
    ):
        try:
            roles.register_local_role(role_name, handler)
        except Exception:  # pragma: no cover
            continue

    for role_name in _SPHINX_TEXT_ROLES:
        try:
            roles.register_local_role(role_name, _text_role)
        except Exception:  # pragma: no cover
            continue
    _roles_registered = True


def _register_sphinx_directives() -> None:
    """Register the Sphinx directives the manual uses, as docutils equivalents."""
    global _directives_registered
    if _directives_registered:
        return
    try:
        from docutils import nodes
        from docutils.parsers.rst import Directive, directives
        from docutils.parsers.rst.directives.admonitions import BaseAdmonition
    except Exception:  # pragma: no cover - docutils missing
        return

    def _make_admonition(label: str):
        class _Admonition(BaseAdmonition):
            node_class = nodes.admonition
            required_arguments = 0
            optional_arguments = 1
            final_argument_whitespace = True
            has_content = True

            def run(self):
                # ``BaseAdmonition`` takes the title from the first argument;
                # the Sphinx spelling has none, so one is supplied.
                title = label if not self.arguments else f"{label} {self.arguments[0]}"
                self.arguments = [title]
                nodes_out = super().run()
                for node in nodes_out:
                    node["classes"].append(label.split()[0].lower())
                return nodes_out

        return _Admonition

    class _Dropped(Directive):
        """A directive whose content is not prose; consumed and discarded."""

        required_arguments = 0
        optional_arguments = 99
        has_content = True
        option_spec = {}

        def run(self):
            return []

        @classmethod
        def with_any_options(cls):
            return cls

    for name, label in _SPHINX_ADMONITIONS.items():
        try:
            directives.register_directive(name, _make_admonition(label))
        except Exception:  # pragma: no cover
            continue
    for name in _DROPPED_DIRECTIVES:
        try:
            directives.register_directive(name, _Dropped)
        except Exception:  # pragma: no cover
            continue
    _directives_registered = True


def render_rst(text: str, *, theme=None, math=None, font_size: float = 10.5) -> str | None:
    """Render reStructuredText to a complete, themed HTML document.

    Parameters
    ----------
    text : str
        reStructuredText source.
    theme : Theme, optional
        Colours for the page; the light theme when omitted.
    math : MathRenderer, optional
        Shared renderer used to typeset ``:math:`` roles and ``.. math::``
        blocks, which docutils otherwise emits as raw LaTeX.
    font_size : float, optional
        Body text size in points.

    Returns
    -------
    str or None
        A full HTML document, or *None* when docutils is unavailable or parsing
        fails, in which case the caller should fall back to the plain source.

    """
    try:
        from docutils.core import publish_parts
    except Exception:
        return None

    _register_sphinx_roles()
    _register_sphinx_directives()
    # Docutils 0.21 renamed ``writer_name`` to ``writer``; support both.
    try:
        import docutils

        writer_kwargs = (
            {"writer": "html5"}
            if tuple(int(p) for p in docutils.__version__.split(".")[:2]) >= (0, 21)
            else {"writer_name": "html5"}
        )
    except Exception:  # pragma: no cover
        writer_kwargs = {"writer_name": "html5"}

    try:
        parts = publish_parts(
            source=text,
            **writer_kwargs,
            settings_overrides={
                # Never abort and never dump system messages into the output:
                # an unknown directive should degrade, not replace the page.
                "report_level": 5,
                "halt_level": 5,
                "traceback": True,
                "embed_stylesheet": False,
                "output_encoding": "unicode",
                "input_encoding": "unicode",
                "doctitle_xform": False,
                "sectsubtitle_xform": False,
                "file_insertion_enabled": False,
                "raw_enabled": False,
                "syntax_highlight": "none",
                # Emit the LaTeX source, delimited, for our own typesetter.
                # Docutils' default is MathML, which Qt cannot lay out: it
                # renders the leaf text of every node, so "\tau_x" arrives as
                # "τ x" and a fraction as its numerator and denominator side by
                # side. Any formula in the manual was unreadable.
                "math_output": "MathJax",
            },
        )
    except Exception:
        return None

    body = parts.get("html_body") or parts.get("fragment")
    if not body:
        return None
    body = _normalise_headings(body)
    body = _style_admonitions(body)
    if math is not None:
        body = _typeset_math(body, math)
    from chisurf.plugins.core.help.api import theme as _theme

    active = theme or _theme.LIGHT
    css = _theme.stylesheet(active, font_size=font_size)
    return f"<html><head>{css}</head><body>{body}</body></html>"


_HEADING_TAG = re.compile(r"<(/?)h([1-6])\b", re.IGNORECASE)


def _normalise_headings(body: str) -> str:
    """Make the page's own title an ``<h1>``, whatever its depth in the manual.

    The manual was split out of one long document, so a page that was a
    fourth-level section carries a fourth-level title — rendered alone, its
    heading is smaller than the body text of the page before it. Shifting every
    level by the same amount keeps the page's internal hierarchy while giving
    it a title that looks like one.
    """
    levels = [int(match.group(2)) for match in _HEADING_TAG.finditer(body)]
    if not levels:
        return body
    shift = 1 - min(levels)
    if shift == 0:
        return body
    return _HEADING_TAG.sub(
        lambda m: f"<{m.group(1)}h{max(1, min(6, int(m.group(2)) + shift))}", body
    )


#: How docutils' HTML5 writer emits mathematics when no MathJax is configured.
_MATH_BLOCK = re.compile(
    r'<div class="math">\s*(?:\\begin\{[^}]*\})?(.*?)(?:\\end\{[^}]*\})?\s*</div>',
    re.DOTALL,
)
_MATH_INLINE = re.compile(r'<span class="math">\\\((.*?)\\\)</span>', re.DOTALL)


def _typeset_math(body: str, math) -> str:
    """Replace docutils' LaTeX passthrough with typeset images."""
    body = _MATH_BLOCK.sub(lambda m: math.to_html(_unescape(m.group(1)), display=True), body)
    body = _MATH_INLINE.sub(lambda m: math.to_html(_unescape(m.group(1)), display=False), body)
    return body


def _unescape(text: str) -> str:
    """Undo the HTML escaping docutils applies inside a maths node."""
    return _html.unescape(text).strip()


#: How docutils opens an admonition, in either writer generation.
_ADMONITION_OPEN = re.compile(
    r'<(?P<tag>aside|div)\s+class="(?P<classes>[^"]*\badmonition\b[^"]*)"[^>]*>',
    re.IGNORECASE,
)
#: Its title, which docutils writes as a paragraph rather than a heading.
_ADMONITION_TITLE = re.compile(
    r'^\s*<p class="admonition-title">(?P<title>.*?)</p>', re.DOTALL | re.IGNORECASE
)


def _style_admonitions(body: str) -> str:
    """Re-wrap docutils admonitions as one-cell tables.

    Qt paints a block background behind that block's own lines only, so a
    coloured ``<aside>`` shows a stripe behind its title and leaves the content
    on the page background — and Qt does not know ``<aside>`` at all. The same
    single-cell table the Markdown renderer uses gives one solid box.
    """
    out = []
    position = 0
    while True:
        match = _ADMONITION_OPEN.search(body, position)
        if match is None:
            out.append(body[position:])
            return "".join(out)
        out.append(body[position : match.start()])
        tag = match.group("tag")
        inner, end = _matching_block(body, match.end(), tag)
        # docutils spells the kind as ``admonition-see-also``; the stylesheet
        # (shared with the Markdown renderer) keys on ``seealso``.
        classes = " ".join(
            sorted(
                {
                    word.replace("admonition-", "").replace("-", "")
                    for word in match.group("classes").split()
                    if word != "admonition"
                }
            )
        )
        title = ""
        title_match = _ADMONITION_TITLE.match(inner)
        if title_match:
            title = title_match.group("title").strip()
            inner = inner[title_match.end() :]
        kind = f"admonition {classes}".strip()
        heading = f'<p class="admonition-title">{title}</p>' if title else ""
        out.append(
            f'<table class="{kind}" width="100%" cellpadding="9" cellspacing="0" '
            f'border="0"><tr><td class="{kind}">{heading}{inner}</td></tr></table>'
        )
        position = end


def _matching_block(body: str, start: int, tag: str) -> tuple[str, int]:
    """Return the content of an element and the index just past its close tag."""
    opener = re.compile(rf"<{tag}\b", re.IGNORECASE)
    closer = re.compile(rf"</{tag}\s*>", re.IGNORECASE)
    depth = 1
    position = start
    while depth:
        next_open = opener.search(body, position)
        next_close = closer.search(body, position)
        if next_close is None:
            return body[start:], len(body)
        if next_open is not None and next_open.start() < next_close.start():
            depth += 1
            position = next_open.end()
            continue
        depth -= 1
        position = next_close.end()
        if depth == 0:
            return body[start : next_close.start()], position
    return body[start:], position


def extract_rst_title(text: str) -> str | None:
    """Return the first section title of a reStructuredText document.

    A title is a line of text underlined (optionally also overlined) by a run of
    punctuation at least as long as the text.

    Parameters
    ----------
    text : str
        reStructuredText source.

    Returns
    -------
    str or None
        The title, or *None* when no section title is present.

    """
    lines = text.splitlines()
    adornment = re.compile(r"^([!-/:-@\[-`{-~])\1{1,}\s*$")
    for i, line in enumerate(lines[:-1]):
        title = line.strip()
        if not title or adornment.match(line):
            continue
        underline = lines[i + 1]
        if adornment.match(underline) and len(underline.strip()) >= len(title):
            return title
    return None


def rst_to_plain_text(text: str) -> str:
    """Return an escaped ``<pre>`` fallback for unrenderable source.

    Parameters
    ----------
    text : str
        Document source.

    Returns
    -------
    str
        HTML showing the raw source verbatim.

    """
    return f"<pre>{_html.escape(text)}</pre>"
