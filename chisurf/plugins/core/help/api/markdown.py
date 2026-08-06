"""Markdown rendering for the Help browser.

The documentation is MyST-flavoured Markdown — the dialect Sphinx builds the
shipped HTML from — and that is more than CommonMark: admonition directives
(``:::{note}``), cross-reference targets (``(concept-fret)=``), figures with
captions, and LaTeX mathematics. A plain Markdown converter passes all of it
through as literal text, which is what the in-app help used to show: a concept
page opened on the line ``(concept-fret)=`` and its formulas read
``\\frac{1}{\\tau_D}``.

So the pipeline here is: mask code (nothing inside a fence is markup), turn the
MyST constructs into HTML, typeset the mathematics with
:mod:`~chisurf.plugins.core.help.api.mathtext`, run the ordinary Markdown
converter over what is left, and put the pieces back. The page is then wrapped
in a stylesheet built for the running theme, so it belongs to the window it is
shown in.

Rendering stays Qt-free and Sphinx-free: the browser must open a page in
milliseconds, and a full Sphinx build needs the whole documentation environment.
"""

from __future__ import annotations

import html as _html
import re
from typing import Optional

from chisurf.plugins.core.help.api import theme as _theme
from chisurf.plugins.core.help.api.mathtext import MathRenderer, split_math

__all__ = [
    "extract_title",
    "render_markdown",
    "render_body",
    "slugify_heading",
    "strip_front_matter",
]

#: Directive names rendered as a coloured admonition box.
ADMONITIONS = {
    "note": "Note",
    "warning": "Warning",
    "tip": "Tip",
    "important": "Important",
    "caution": "Caution",
    "danger": "Danger",
    "error": "Error",
    "hint": "Hint",
    "attention": "Attention",
    "seealso": "See also",
    "admonition": "",
}

#: Directives whose content is navigation or build metadata, not prose.
_DROPPED_DIRECTIVES = {"toctree", "contents", "index", "meta", "raw", "only"}

_FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,}|:{3,})\{(?P<name>[\w.-]+)\}\s*(?P<arg>.*)$")
_OPTION = re.compile(r"^[ \t]*:([\w-]+):\s*(.*)$")
_TARGET = re.compile(r"^\((?P<name>[^)]+)\)=\s*$")


def render_markdown(
    text: str,
    *,
    theme: Optional[_theme.Theme] = None,
    math: Optional[MathRenderer] = None,
    font_size: float = 10.5,
) -> Optional[str]:
    """Render Markdown *text* to a complete, themed HTML document.

    Parameters
    ----------
    text : str
        MyST-flavoured Markdown source.
    theme : Theme, optional
        Colours for the page; defaults to the light theme.
    math : MathRenderer, optional
        Renderer used for LaTeX. Pass one shared instance to reuse its cache
        across pages; ``None`` builds one matching *theme*.
    font_size : float, optional
        Body font size in points.

    Returns
    -------
    str or None
        A full HTML document, or *None* only if rendering raised — callers show
        the source in that case.

    """
    active = theme or _theme.LIGHT
    renderer = math or MathRenderer(colour=active.text, font_size=font_size)
    body = render_body(text, math=renderer)
    css = _theme.stylesheet(active, font_size=font_size)
    return f"<html><head>{css}</head><body>{body}</body></html>"


def render_body(text: str, *, math: Optional[MathRenderer] = None) -> str:
    """Render Markdown *text* to an HTML fragment, without the page wrapper.

    Parameters
    ----------
    text : str
        MyST-flavoured Markdown source.
    math : MathRenderer, optional
        Renderer for LaTeX; when omitted, mathematics is left as source.

    Returns
    -------
    str
        HTML fragment.

    """
    source = strip_front_matter(text)
    keeper = _Placeholders()
    source = _convert_targets(source, keeper)
    # Fenced blocks first, in one pass: a code fence and a directive fence are
    # the same syntax, so scanning for them separately let the closing back
    # ticks of a ``{figure}`` block pair up with the opening ones as *inline*
    # code -- which is how a whole figure directive ended up on the page as
    # pink monospace.
    source = _convert_blocks(source, keeper, math)
    source = keeper.mask_inline_code(source)
    if math is not None:
        source = _convert_math(source, keeper, math)
    source = _prepare_markdown_with_heading_ids(source)

    body = _render_with_markdown_lib(source)
    if body is None:
        body = _basic_markdown_to_html(source)
    return keeper.restore(body)


def strip_front_matter(text: str) -> str:
    """Remove a leading YAML front-matter block, which is metadata not prose."""
    if not text.startswith("---"):
        return text
    match = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    return text[match.end():] if match else text


def extract_title(text: str) -> Optional[str]:
    """Return the first Markdown heading from *text*, or *None*."""
    for line in strip_front_matter(text).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if not m:
            continue
        heading = m.group(2)
        heading = re.sub(r"\{\s*#[-\w]+\s*\}\s*$", "", heading).strip()
        if heading:
            return heading
    return None


def slugify_heading(text: str) -> str:
    """Convert a heading string to an HTML-anchor-compatible slug."""
    slug = text.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug or "section"


# ── placeholder bookkeeping ─────────────────────────────────────────


class _Placeholders:
    """Hold HTML that must survive the Markdown converter untouched.

    Code, formulas and converted directives are already HTML by the time the
    Markdown pass runs; letting the converter see them would escape their
    angle brackets or reflow them. Each is swapped for a token that looks like
    an ordinary word — so the converter leaves it in place — and swapped back
    afterwards.
    """

    #: A token no Markdown construct can interfere with.
    _TOKEN = "xzhelpph{index}zx"

    def __init__(self):
        self._items: list[str] = []

    def add(self, html: str) -> str:
        """Store *html* and return the token standing in for it."""
        token = self._TOKEN.format(index=len(self._items))
        self._items.append(html)
        return token

    def restore(self, text: str) -> str:
        """Put every stored fragment back into *text*.

        A stored fragment can itself contain tokens — a note holding a code
        block — and the code was stored *before* the note that swallowed it, so
        one pass in index order would put the code back before the note that
        carries it is in the text. Passes repeat until nothing changes.
        """
        for _ in range(len(self._items) + 1):
            before = text
            for index, html in enumerate(self._items):
                token = self._TOKEN.format(index=index)
                if token not in text:
                    continue
                # A block fragment the converter wrapped in a paragraph would
                # nest a <div> inside a <p>, which Qt lays out badly.
                text = re.sub(rf"<p>\s*{token}\s*</p>", lambda _m, h=html: h, text)
                text = text.replace(token, html)
            if text == before:
                break
        return text

    def mask_inline_code(self, text: str) -> str:
        """Replace ``code spans`` with tokens holding their HTML.

        The span may not cross a line: without that limit a pair of fence lines
        left over anywhere in the page reads as one enormous code span.
        """
        return re.sub(
            r"(?<!`)(`{1,2})(?!`)([^\n]+?)(?<!`)\1(?!`)",
            lambda m: self.add(f"<code>{_html.escape(m.group(2))}</code>"),
            text,
        )


def _admonition(kind: str, title: str, inner_html: str) -> str:
    """Render an admonition as a one-cell table.

    A ``<div>`` would be the obvious element, but Qt's rich-text engine paints
    a block background behind the block's *own* line boxes only, so a coloured
    div showed a stripe behind the title and left its content on the page
    background. A table cell is painted as one rectangle, which is what an
    admonition has to look like.
    """
    klass = "admonition" if kind == "admonition" else f"admonition {kind}"
    heading = (
        f'<p class="admonition-title">{_html.escape(title)}</p>' if title else ""
    )
    return (
        f'<table class="{klass}" width="100%" cellpadding="9" cellspacing="0" border="0">'
        f'<tr><td class="{klass}">{heading}{inner_html}</td></tr></table>'
    )


def _code_block(body: str, language: str = "") -> str:
    """Render a code block; the language is shown only when it is informative."""
    escaped = _html.escape(body.rstrip("\n"))
    return f"<pre><code>{escaped}</code></pre>"


# ── MyST constructs ─────────────────────────────────────────────────


def _convert_targets(text: str, keeper: _Placeholders) -> str:
    """Turn ``(name)=`` cross-reference targets into real anchors.

    The line is invisible in the shipped HTML because Sphinx consumes it; a
    plain converter prints it, which is why every concept page used to open on
    ``(concept-fret)=``.
    """
    out = []
    for line in text.splitlines():
        match = _TARGET.match(line)
        if match:
            anchor = match.group("name").strip()
            out.append(keeper.add(f'<a name="{_html.escape(anchor, quote=True)}"></a>'))
            continue
        out.append(line)
    return "\n".join(out)


#: Any fenced block: ```` ``` ````, ``~~~`` or ``:::``, with its info string.
_ANY_FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,}|:{3,})(?P<info>.*)$")


def _convert_blocks(
    text: str, keeper: _Placeholders, math: Optional[MathRenderer]
) -> str:
    """Convert every fenced block — code and MyST directive — to HTML.

    Both use the same fence syntax and differ only in the info string, so they
    are recognised in one pass. Directive content is rendered recursively, so a
    note may hold a list, a formula or a code sample.
    """
    lines = text.splitlines()
    out: list[str] = []
    index = 0
    while index < len(lines):
        opener = _ANY_FENCE.match(lines[index])
        if opener is None:
            out.append(lines[index])
            index += 1
            continue

        fence = opener.group("fence")
        info = opener.group("info").strip()
        marker = fence[0]
        closer = re.compile(rf"^[ \t]*{re.escape(marker)}{{{len(fence)},}}[ \t]*$")
        directive = _FENCE.match(lines[index])

        body: list[str] = []
        index += 1
        depth = 0
        while index < len(lines):
            line = lines[index]
            nested = _ANY_FENCE.match(line)
            if nested is not None and nested.group("fence")[0] == marker:
                if closer.match(line) and depth == 0:
                    index += 1
                    break
                if nested.group("info").strip():
                    depth += 1
                elif depth:
                    depth -= 1
            body.append(line)
            index += 1

        if directive is None:
            # A plain code fence; ``:::`` without a name is a bare container.
            if marker == ":":
                out.append(_convert_blocks("\n".join(body), keeper, math))
                continue
            rendered = _code_block("\n".join(body), info)
        else:
            options, content = _split_options(body)
            rendered = _render_directive(
                directive.group("name").lower(),
                directive.group("arg").strip(),
                options,
                content,
                math,
            )
        out.append("")
        out.append(keeper.add(rendered) if rendered else "")
        out.append("")
    return "\n".join(out)


def _split_options(body: list[str]) -> tuple[dict, str]:
    """Separate a directive's ``:key: value`` options from its content."""
    options: dict[str, str] = {}
    index = 0
    while index < len(body):
        line = body[index]
        if not line.strip():
            index += 1
            if options:
                break
            continue
        match = _OPTION.match(line)
        if match is None:
            break
        options[match.group(1).lower()] = match.group(2).strip()
        index += 1
    return options, "\n".join(body[index:])


def _render_directive(
    name: str,
    argument: str,
    options: dict,
    content: str,
    math: Optional[MathRenderer],
) -> str:
    """Render one MyST directive to HTML."""
    anchor = ""
    if options.get("name"):
        anchor = f'<a name="{_html.escape(options["name"], quote=True)}"></a>'

    if name in _DROPPED_DIRECTIVES:
        return ""

    if name in ADMONITIONS:
        title = argument or ADMONITIONS[name] or name.title()
        inner = render_body(content, math=math)
        return anchor + _admonition(name, title, inner)

    if name == "math":
        if math is None:
            return f"<pre>{_html.escape(content)}</pre>"
        return anchor + math.to_html(content, display=True)

    if name in ("code-block", "code", "sourcecode"):
        return anchor + _code_block(content, argument)

    if name in ("figure", "image"):
        source = argument or options.get("figure", "")
        width = options.get("width", "")
        attrs = f' width="{_html.escape(width, quote=True)}"' if width.isdigit() else ""
        alt = _html.escape(options.get("alt", ""), quote=True)
        image = f'<img src="{_html.escape(source, quote=True)}" alt="{alt}"{attrs}>'
        caption = content.strip()
        if caption:
            rendered = render_body(caption, math=math)
            return (
                f'{anchor}<p align="center">{image}</p>'
                f'<p align="center" class="doc-caption">{rendered}</p>'
            )
        return f'{anchor}<p align="center">{image}</p>'

    if name == "rubric":
        return f"{anchor}<h3>{_html.escape(argument)}</h3>"

    if name in ("dropdown", "details"):
        inner = render_body(content, math=math)
        return anchor + _admonition("note", argument or "Details", inner)

    if name in ("tab-set", "grid", "card-carousel", "div", "container"):
        return anchor + render_body(content, math=math)

    if name in ("tab-item", "card", "grid-item-card"):
        title = f"<h4>{_html.escape(argument)}</h4>" if argument else ""
        return anchor + title + render_body(content, math=math)

    # An unknown directive still has content worth reading; show it labelled
    # rather than dropping it or spilling the raw fence into the page.
    label = f"<h4>{_html.escape(argument or name)}</h4>"
    return anchor + label + render_body(content, math=math)


def _convert_math(text: str, keeper: _Placeholders, math: MathRenderer) -> str:
    """Replace ``$…$`` / ``$$…$$`` with typeset images."""
    if "$" not in text and "\\(" not in text and "\\[" not in text:
        return text
    pieces: list[str] = []
    for kind, payload in split_math(text):
        if kind == "text":
            pieces.append(payload)
            continue
        display = kind == "display"
        rendered = math.to_html(payload, display=display)
        token = keeper.add(rendered)
        pieces.append(f"\n\n{token}\n\n" if display else token)
    return "".join(pieces)


# ── ordinary Markdown ───────────────────────────────────────────────


def _prepare_markdown_with_heading_ids(text: str) -> str:
    """Ensure every heading has an ``{#id}`` attribute marker."""
    out_lines = []
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if not m:
            out_lines.append(line)
            continue
        prefix, title = m.group(1), m.group(2)
        if re.search(r"\{\s*#[-\w]+\s*\}\s*$", title):
            out_lines.append(line)
            continue
        slug = slugify_heading(title)
        out_lines.append(f"{prefix} {title} " + "{" + f"#{slug}" + "}")
    return "\n".join(out_lines)


def _render_with_markdown_lib(text: str) -> Optional[str]:
    """Render with the ``markdown`` package if available."""
    try:
        import markdown as _md
    except Exception:
        return None
    for extensions in (
        ["attr_list", "tables", "sane_lists", "def_list", "footnotes", "md_in_html"],
        ["attr_list"],
        [],
    ):
        try:
            return _md.markdown(text, output_format="html5", extensions=extensions)
        except Exception:
            continue
    return None


def _basic_markdown_to_html(text: str) -> str:
    """Convert simple Markdown to HTML when the converter is unavailable."""
    lines = text.splitlines()
    html_lines = []

    in_ul = False
    in_ol = False

    def _process_inline_with_images(raw: str) -> str:
        placeholders = {}

        def _img_repl(m):
            alt = m.group(1)
            src = m.group(2).strip()
            key = f"__CS_IMG_{len(placeholders)}__"
            alt_esc = _html.escape(alt)
            src_esc = _html.escape(src, quote=True)
            placeholders[key] = f'<img src="{src_esc}" alt="{alt_esc}">'
            return key

        tmp = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _img_repl, raw)
        escaped = _html.escape(tmp)
        escaped = _apply_inline_markdown(escaped)
        for key, tag in placeholders.items():
            escaped = escaped.replace(key, tag)
        return escaped

    for line in lines:
        stripped = line.lstrip()
        if not stripped:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            html_lines.append("")
            continue

        m_ul = re.match(r"^[-*+]\s+(.*)", stripped)
        m_ol = re.match(r"^(\d+)[.)]\s+(.*)", stripped)

        if m_ul:
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            content = _process_inline_with_images(m_ul.group(1))
            html_lines.append(f"<li>{content}</li>")
            continue

        if m_ol:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if not in_ol:
                html_lines.append("<ol>")
                in_ol = True
            content = _process_inline_with_images(m_ol.group(2))
            html_lines.append(f"<li>{content}</li>")
            continue

        if in_ul:
            html_lines.append("</ul>")
            in_ul = False
        if in_ol:
            html_lines.append("</ol>")
            in_ol = False

        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            level = len(m.group(1))
            raw_content = m.group(2)
            m_id = re.search(r"\{\s*#([-\w]+)\s*\}\s*$", raw_content)
            if m_id:
                anchor = m_id.group(1)
                raw_content = raw_content[:m_id.start()].rstrip()
            else:
                anchor = slugify_heading(raw_content)
            content = _process_inline_with_images(raw_content)
            html_lines.append(f'<h{level} id="{anchor}">{content}</h{level}>')
        else:
            content = _process_inline_with_images(line)
            html_lines.append(f"<p>{content}</p>")

    if in_ul:
        html_lines.append("</ul>")
    if in_ol:
        html_lines.append("</ol>")

    return "\n".join(html_lines)


def _apply_inline_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    return text
