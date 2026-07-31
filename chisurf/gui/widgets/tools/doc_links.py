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
import re
import webbrowser

from qtpy import QtCore

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


def repository_root() -> pathlib.Path:
    """Return the directory that holds ``docs/`` — the repo or install root."""
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docs").is_dir():
            return parent
    return here.parents[-1]


def resolve_document(target: str, base: pathlib.Path | None = None) -> pathlib.Path | None:
    """Resolve a link target to a documentation file.

    Parameters
    ----------
    target : str
        Path from the link, e.g. ``docs/concepts/pair_correlation.md``,
        ``concepts/pair_correlation.md``, or one relative to *base*.
    base : pathlib.Path, optional
        Directory the help text itself lives in, tried first so a plugin can
        link to a file beside its own ``help.md``.

    Returns
    -------
    pathlib.Path or None
        The existing file, or ``None`` when nothing matches.
    """
    text = str(target or "").strip()
    if not text:
        return None
    path = pathlib.Path(text)
    if path.is_absolute():
        return path if path.is_file() else None

    root = repository_root()
    candidates: list[pathlib.Path] = []
    if base is not None:
        candidates.append(base / path)
    candidates.append(root / path)
    # A link may name the page without the ``docs/`` prefix, which is how the
    # docs cross-reference each other.
    candidates.append(root / "docs" / path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


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
    qurl = url if isinstance(url, QtCore.QUrl) else QtCore.QUrl(str(url))
    scheme = qurl.scheme().lower()
    text = qurl.toString()

    if scheme in WEB_SCHEMES:
        return _open_web(text)
    if scheme == "doi":
        return _open_web("https://doi.org/" + text.split(":", 1)[-1])
    # A bare DOI, as papers are usually cited.
    if not scheme and text.startswith("10.") and "/" in text:
        return _open_web("https://doi.org/" + text)

    if qurl.isLocalFile():
        candidate = pathlib.Path(qurl.toLocalFile())
        return _open_document(candidate, qurl.fragment()) if candidate.is_file() else False

    path = qurl.path() or text
    document = resolve_document(path, base)
    if document is not None:
        return _open_document(document, qurl.fragment())
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
    """Show *path* in the ChiSurf documentation browser.

    An already-open browser is reused and raised rather than a second one being
    stacked on top of it, so following three cross-references does not leave
    three windows behind.
    """
    try:
        from qtpy import QtWidgets

        from chisurf.plugins.core.help.gui.tool import HelpWidget
    except Exception:
        logger.debug("the documentation browser is unavailable", exc_info=True)
        return _open_web(path.as_uri())

    widget = None
    for candidate in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(candidate, HelpWidget):
            widget = candidate
            break
    if widget is None:
        widget = HelpWidget()
    try:
        widget.show()
        widget.raise_()
        widget.activateWindow()
        widget._open_document_path(path, anchor or None)
    except Exception:
        logger.debug("could not open %s in the documentation browser", path, exc_info=True)
        return False
    return True


def wire_text_browser(browser, base: pathlib.Path | None = None) -> None:
    """Route a ``QTextBrowser``'s links through :func:`open_link`.

    Parameters
    ----------
    browser : QtWidgets.QTextBrowser
        The widget to wire.
    base : pathlib.Path, optional
        Directory the shown text came from, for relative document links.

    Notes
    -----
    ``setOpenLinks(False)`` is what makes this work: left to itself the browser
    tries to *navigate* to the target and, failing, blanks the page it was
    showing — so a dead link would eat the help text.
    """
    try:
        browser.setOpenLinks(False)
        browser.setOpenExternalLinks(False)
    except Exception:  # pragma: no cover - not a QTextBrowser
        return

    def _clicked(url) -> None:
        if url.scheme() == "" and not url.path() and url.fragment():
            # An in-page anchor: scroll rather than leave the document.
            try:
                browser.scrollToAnchor(url.fragment())
            except Exception:
                logger.debug("could not scroll to %s", url.fragment(), exc_info=True)
            return
        open_link(url, base)

    browser.anchorClicked.connect(_clicked)


# ──────────────────────────────────────────────────────────────────────────────
# MyST cross-reference roles
# ──────────────────────────────────────────────────────────────────────────────
#: ``{ref}`label``` / ``{ref}`text <label>``` and the same for ``{doc}``.
_ROLE = re.compile(r"\{(ref|doc)\}`([^`]+)`")
#: A MyST target at the top of a page: ``(concept-image-correlation)=``.
_TARGET = re.compile(r"^\((?P<label>[A-Za-z0-9_.:-]+)\)=\s*$", re.M)

_REF_CACHE: dict[str, pathlib.Path] | None = None


def ref_index(refresh: bool = False) -> dict[str, pathlib.Path]:
    """Return every ``(label)=`` target in the docs, mapped to its page.

    Parameters
    ----------
    refresh : bool
        Rebuild the index instead of using the cached one.

    Returns
    -------
    dict
        ``{label: path}``. Empty when there is no ``docs/`` tree.
    """
    global _REF_CACHE
    if _REF_CACHE is not None and not refresh:
        return _REF_CACHE
    index: dict[str, pathlib.Path] = {}
    docs = repository_root() / "docs"
    if docs.is_dir():
        for page in docs.rglob("*.md"):
            try:
                text = page.read_text(encoding="utf-8")
            except Exception:
                continue
            for match in _TARGET.finditer(text):
                index.setdefault(match.group("label"), page)
    _REF_CACHE = index
    return index


def resolve_ref(label: str) -> pathlib.Path | None:
    """Return the page that defines ``(label)=``, or ``None``."""
    return ref_index().get(str(label).strip())


def expand_roles(text: str, base: pathlib.Path | None = None) -> str:
    """Turn MyST ``{ref}``/``{doc}`` roles into ordinary Markdown links.

    The documentation is written in MyST, whose cross-references are roles
    rather than links. A plain Markdown viewer renders them as literal text --
    ``{ref}`concept-fcs-correlation``` -- so the pages that cross-reference each
    other most are exactly the ones that cannot be navigated. Rewriting them to
    ``[text](path)`` before rendering makes them clickable without touching the
    sources, which still have to build under Sphinx.

    Parameters
    ----------
    text : str
        Markdown source.
    base : pathlib.Path, optional
        Directory of the page, for resolving a relative ``{doc}`` target.

    Returns
    -------
    str
        The same text with resolvable roles rewritten as links; an unresolvable
        role is left as it was rather than turned into a dead link.
    """
    def _replace(match: "re.Match[str]") -> str:
        role, body = match.group(1), match.group(2).strip()
        label, caption = body, ""
        if "<" in body and body.endswith(">"):
            caption, label = body[: body.index("<")].strip(), body[body.index("<") + 1 : -1]
        target = (
            resolve_ref(label) if role == "ref"
            else resolve_document(label.lstrip("/") + ".md", base)
            or resolve_document(label.lstrip("/"), base)
        )
        if target is None:
            return match.group(0)
        try:
            href = target.relative_to(repository_root()).as_posix()
        except ValueError:
            href = str(target)
        return f"[{caption or label}]({href})"

    return _ROLE.sub(_replace, str(text))
