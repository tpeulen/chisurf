"""Cross-reference resolution for the documentation.

The documentation is one web, written in two dialects. A guide points at the
theory with MyST — ``{ref}`concept-fcs-correlation``` — and the manual points at
the same page with reStructuredText — ``:ref:`concept-fcs-correlation```. Both
are *roles*, not links, so anything that is not Sphinx shows them as literal
text: the pages that cross-reference each other most were exactly the ones a
reader could not navigate.

Resolving them needs no Qt and no browser, only the docs tree, so it lives here
rather than in the widget that happens to display the result — the GUI, the
plugin ``?`` modal and the reStructuredText renderer all resolve the same way,
against one index.

What a reference resolves *to* matters as much as whether it resolves. A label
carries no words a reader wants to see, so a reference with no caption of its
own is rendered as the **title of the page it leads to**.
"""

from __future__ import annotations

import pathlib
import re

__all__ = [
    "expand_roles",
    "ref_index",
    "reference_text",
    "repository_root",
    "resolve_document",
    "resolve_ref",
]

#: A MyST target at the top of a page: ``(concept-image-correlation)=``.
_TARGET = re.compile(r"^\((?P<label>[A-Za-z0-9_.:-]+)\)=\s*$", re.M)
#: A directive's ``:name:`` option, which is how figures and equations are named.
_NAMED = re.compile(r"^[ \t]*:name:[ \t]*(?P<label>[A-Za-z0-9_.:-]+)[ \t]*$", re.M)
#: A Markdown heading, used as a cross-reference's text.
_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*(?:\{#[-\w]+\})?\s*$", re.M)
#: ``{ref}`label``` / ``{ref}`text <label>``` and the same for the other roles.
_ROLE = re.compile(r"\{(ref|doc|numref|eq|term)\}`([^`]+)`")

_REF_CACHE: dict[str, tuple[pathlib.Path, str]] | None = None


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


def ref_index(refresh: bool = False) -> dict[str, tuple[pathlib.Path, str]]:
    """Return every cross-reference label in the docs, with its page and text.

    Both kinds of label are indexed: a page target written ``(label)=`` and a
    directive named with ``:name: label`` (figures, equations).

    Parameters
    ----------
    refresh : bool
        Rebuild the index instead of using the cached one.

    Returns
    -------
    dict
        ``{label: (path, text)}``. Empty when there is no ``docs/`` tree.

    """
    global _REF_CACHE
    if _REF_CACHE is not None and not refresh:
        return _REF_CACHE
    index: dict[str, tuple[pathlib.Path, str]] = {}
    docs = repository_root() / "docs"
    if docs.is_dir():
        for page in docs.rglob("*.md"):
            try:
                text = page.read_text(encoding="utf-8")
            except Exception:
                continue
            title_match = _HEADING.search(text)
            page_title = title_match.group("title").strip() if title_match else page.stem
            for match in _TARGET.finditer(text):
                index.setdefault(
                    match.group("label"),
                    (page, _text_after(text, match.end(), page_title)),
                )
            for match in _NAMED.finditer(text):
                index.setdefault(match.group("label"), (page, "the figure"))
    _REF_CACHE = index
    return index


def _text_after(text: str, position: int, fallback: str) -> str:
    """Return the heading that follows a target, or *fallback*.

    A target is written directly above the thing it names, so the heading under
    it is the honest label for a reference that carries no caption — far better
    than showing the reader the raw ``concept-fcs-correlation``.
    """
    match = _HEADING.search(text, position)
    if match is None:
        return fallback
    # Only when it is the *next* thing in the file, not a heading pages later.
    if text.count("\n", position, match.start()) > 3:
        return fallback
    return match.group("title").strip()


def resolve_ref(label: str) -> pathlib.Path | None:
    """Return the page that defines ``(label)=``, or ``None``."""
    entry = ref_index().get(str(label).strip())
    return entry[0] if entry else None


def reference_text(label: str) -> str:
    """Return the words a reference to *label* should read as."""
    entry = ref_index().get(str(label).strip())
    return entry[1] if entry else ""


def document_reference(
    role: str, body: str, base: pathlib.Path | None = None
) -> tuple[pathlib.Path | None, str, str]:
    """Resolve one cross-reference role.

    Parameters
    ----------
    role : str
        ``ref``, ``doc``, ``numref``, ``eq`` or ``term``.
    body : str
        The role's content: a label, or ``caption <label>``.
    base : pathlib.Path, optional
        Directory of the page holding the reference.

    Returns
    -------
    tuple
        ``(path, anchor, text)``. *path* is ``None`` when nothing resolves, and
        *text* is then still the best label available, so a caller can degrade
        to plain words instead of showing markup.

    """
    label, caption = body.strip(), ""
    if "<" in label and label.endswith(">"):
        caption, label = label[: label.index("<")].strip(), label[label.index("<") + 1: -1]
    label = label.strip()

    if role in ("ref", "numref", "eq"):
        entry = ref_index().get(label)
        if entry is None:
            return None, "", caption or label
        return entry[0], label, caption or entry[1] or label

    if role == "term":
        return None, "", caption or label

    target = resolve_document(label.lstrip("/") + ".md", base) or resolve_document(
        label.lstrip("/"), base
    )
    if target is None:
        return None, "", caption or label
    text = caption
    if not text:
        try:
            from chisurf.plugins.core.help.api.render import document_title

            text = document_title(target.read_text(encoding="utf-8"), target) or ""
        except Exception:
            text = ""
    return target, "", text or label


def expand_roles(text: str, base: pathlib.Path | None = None) -> str:
    """Turn MyST cross-reference roles into ordinary Markdown links.

    Parameters
    ----------
    text : str
        Markdown source.
    base : pathlib.Path, optional
        Directory of the page, for resolving a relative ``{doc}`` target.

    Returns
    -------
    str
        The same text with resolvable roles rewritten as links. An unresolvable
        role degrades to its own words: a reader is not helped by seeing the
        markup that failed.

    """
    def _replace(match: "re.Match[str]") -> str:
        role, body = match.group(1), match.group(2)
        target, anchor, label = document_reference(role, body, base)
        if target is None:
            return label
        try:
            href = target.relative_to(repository_root()).as_posix()
        except ValueError:
            href = str(target)
        return f"[{label}]({href}{'#' + anchor if anchor else ''})"

    return _ROLE.sub(_replace, str(text))
