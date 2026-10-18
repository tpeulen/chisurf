"""Make the links in a tool's help text actually go somewhere.

Every ChiSurf tool ends its help with a *Further reading* list — the concept
page, the guide, a couple of papers. Rendered as plain text those are three
lines nobody can follow: the user has to find the repository, find the file, and
open it in something else. This module turns them into working links, so the
same list is a way in rather than a citation.

Two destinations, dispatched on the URL:

* a **document** — anything that names a file in the repository's ``docs/``
  tree, with or without an ``#anchor`` — opens in the ChiSurf documentation
  browser, at that page;
* a **web address** — ``http``/``https``, a ``doi:`` or a bare
  ``10.xxxx/...`` DOI, or ``mailto:`` — opens in the system browser.

Anything else is left alone rather than guessed at.

Attach it to any rich-text widget with :func:`wire_text_browser`, which is what
the shared ``?`` help modal does — so a plugin gets clickable cross-references
by writing ordinary Markdown links in its ``help.md``.
"""

from __future__ import annotations

import logging
import pathlib
import sys
import webbrowser


from chisurf.plugins.core.help.api.source_links import is_source_path
from chisurf.plugins.core.help.api.xref import (
    expand_roles,
    ref_index,
    repository_root,
    resolve_document,
    resolve_ref,
)

logger = logging.getLogger(__name__)

__all__ = [
    "expand_roles",
    "open_link",
    "ref_index",
    "repository_root",
    "resolve_document",
    "resolve_ref",
    "wire_text_browser",
]

#: URL schemes handed to the system browser.
WEB_SCHEMES = ("http", "https", "ftp", "mailto")


def open_link(url, base: pathlib.Path | None = None) -> bool:
    """Open *url* in the documentation browser or the web browser.

    Parameters
    ----------
    url : QUrl or str
        The clicked link.
    base : pathlib.Path, optional
        Directory the help text lives in, for resolving a relative document.

    Returns
    -------
    bool
        Whether the link was handled. ``False`` means the caller should fall
        back to its own behaviour rather than silently swallowing the click.
    """
    qt_core = _loaded_qt_core()
    if qt_core is not None and isinstance(url, qt_core.QUrl):
        qurl = url
        scheme = qurl.scheme().lower()
        text = qurl.toString()
        fragment = qurl.fragment()
        is_local = qurl.isLocalFile()
        local_path = qurl.toLocalFile()
        path_str = qurl.path() or text
    else:
        text = str(url or "").strip()
        scheme = text.split(":", 1)[0].lower() if ":" in text else ""
        fragment = text.split("#", 1)[1] if "#" in text else ""
        is_local = False
        local_path = ""
        path_str = text.split("#", 1)[0]

    # 1. Source code links (e.g. {src}, src:path#symbol, bare .py file)
    if is_source_path(text):
        from chisurf.emtk.code_links import open_source

        return open_source(text, base)

    # 2. Web & external schemes
    if scheme in WEB_SCHEMES:
        return _open_web(text)
    if scheme == "doi":
        return _open_web("https://doi.org/" + text.split(":", 1)[-1])
    # A bare DOI, as papers are usually cited.
    if not scheme and text.startswith("10.") and "/" in text:
        return _open_web("https://doi.org/" + text)

    # 3. Local file
    if is_local and local_path:
        candidate = pathlib.Path(local_path)
        return _open_document(candidate, fragment) if candidate.is_file() else False

    # 4. Document cross-reference
    document = resolve_document(path_str, base)
    if document is not None:
        return _open_document(document, fragment)
    logger.debug("no destination for help link %r", text)
    return False


def _open_web(url: str) -> bool:
    """Open *url* in the system browser."""
    try:
        webbrowser.open(url)
        return True
    except Exception:
        logger.debug("could not open %s", url, exc_info=True)
        return False


def _open_document(path: pathlib.Path, anchor: str = "") -> bool:
    """Show *path* in the ChiSurf documentation browser at *anchor*.

    An open help browser takes it; else the open emtk shell docks one (the ``help``
    plugin's ``open_page`` hand-off); else a standalone help window opens.
    """
    from chisurf.plugins.core.help.gui.help_app import open_help_page

    if open_help_page(path, anchor=anchor or None):
        return True
    # The emtk shell is open: the help browser is one of its docks, not a second
    # process whose OS window falls behind the main one.
    from chisurf.core.plugin import handoff

    if handoff.available("help", "open_page"):
        try:
            handoff.hand_off("help", "open_page", {"path": str(path), "anchor": anchor or ""})
            return True
        except handoff.HandoffError:
            logger.debug("the shell refused the help hand-off", exc_info=True)
    try:
        import subprocess

        command = [sys.executable, "-m", "chisurf.emtk", "--plugin", "help", "--path", str(path)]
        if anchor:
            command.extend(["--anchor", anchor])
        subprocess.Popen(command)
        return True
    except Exception:
        logger.debug("could not launch native documentation viewer", exc_info=True)
        return _open_web(path.as_uri())


# ──────────────────────────────────────────────────────────────────────────────
# MyST cross-reference roles
# ──────────────────────────────────────────────────────────────────────────────
# Resolution itself lives in the Qt-free help API, because the manual's
# reStructuredText renderer needs exactly the same answers and cannot import a
# widget module. These names stay here as the GUI-side entry points.
