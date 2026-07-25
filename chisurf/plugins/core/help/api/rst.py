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
    "doc",
    "ref",
    "numref",
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

_roles_registered = False


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

    for role_name in _SPHINX_TEXT_ROLES:
        try:
            roles.register_local_role(role_name, _text_role)
        except Exception:  # pragma: no cover
            continue
    _roles_registered = True


def render_rst(text: str) -> str | None:
    """Render reStructuredText to a standalone HTML fragment.

    Parameters
    ----------
    text : str
        reStructuredText source.

    Returns
    -------
    str or None
        HTML body, or *None* when docutils is unavailable or parsing fails, in
        which case the caller should fall back to showing the plain source.

    """
    try:
        from docutils.core import publish_parts
    except Exception:
        return None

    _register_sphinx_roles()
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
            },
        )
    except Exception:
        return None

    body = parts.get("html_body") or parts.get("fragment")
    return body if body else None


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
