"""The documentation the page ships: the user-facing ``docs/`` markdown.

The desktop help browser (the ``help`` plugin) reads the checkout's ``docs/``
tree; a page has no checkout -- its Python is the unpacked archive. So the
archive carries the same tree: :func:`doc_files` packs the user-facing markdown
as the bundle's *extra files*, under their repository-relative ``docs/...``
paths. Unpacked, the archive is one directory on ``sys.path`` with ``chisurf/``
and ``docs/`` as siblings -- exactly the layout
:func:`chisurf.plugins.core.help.api.toc.docs_root` and
:func:`chisurf.plugins.core.help.api.io.discover_docs` resolve, so the help
plugin lists, searches, renders and cross-links the shipped pages with no
changes of its own.

What ships is the user-facing split (the same one
:func:`chisurf.plugins.core.help.api.toc.build_toc` shows by default): the
getting-started pages, the fundamentals, the per-tool guides, the concepts, the
user manual and the reference material -- plus each directory's
``review_status.json`` so the reader's review badges stay truthful. What stays
behind is maintainer material and everything a page cannot show anyway:
``development/`` (architecture notes, migration plans), ``_old_manual``, the
Sphinx build, and the figures (the reader draws text, not images; a link to a
figure that is not there degrades to its caption).
"""

from __future__ import annotations

import pathlib

__all__ = [
    "DOC_SIDECAR",
    "SKIP_DIR_NAMES",
    "TOP_LEVEL_FILES",
    "USER_DOC_ROOTS",
    "doc_files",
    "docs_source",
]

#: The ``docs/`` subdirectories that ship: the user-facing split.
#: ``development/`` (and the ``_``-prefixed trees) are for maintainers.
USER_DOC_ROOTS = (
    "getting_started",
    "fundamentals",
    "guides",
    "concepts",
    "manual",
    "reference",
    "references",
)

#: Files directly under ``docs/`` that ship.
TOP_LEVEL_FILES = ("index.md", "licensing.md")

#: The per-directory review registry, shipped beside the pages so the reader's
#: review badges mean the same in the page as on the desktop.
DOC_SIDECAR = "review_status.json"

#: Directory names that never ship, at any depth: maintainer material, build
#: output, and the binary figures the reader cannot draw.
SKIP_DIR_NAMES = frozenset({
    "__pycache__",
    "_build",
    "_old_manual",
    "_ext",
    "development",
    "figures",
    "screenshots",
    "images",
    "_images",
})


def docs_source() -> pathlib.Path | None:
    """The ``docs/`` tree the bundle packs, or ``None`` when there is none.

    The packaged copy first (``chisurf/docs`` -- what a wheel install carries),
    then the checkout's, found the way
    :func:`chisurf.plugins.core.help.api.toc.docs_root` finds it: so the page
    ships exactly what the desktop help browser reads.
    """
    package = pathlib.Path(__file__).resolve().parent.parent
    packaged = package / "docs"
    if (packaged / "guides").is_dir():
        return packaged
    for parent in package.parents:
        if (parent / "docs" / "guides").is_dir():
            return parent / "docs"
    return None


def doc_files() -> dict[str, bytes]:
    """The shipped documentation, keyed by archive path (``docs/...``).

    Markdown pages under :data:`USER_DOC_ROOTS`, the :data:`TOP_LEVEL_FILES`,
    and every :data:`DOC_SIDECAR` beside them. A page's markdown is small
    (a few MB raw; the archive is deflated), the figures it names are not --
    they stay behind with the rest of :data:`SKIP_DIR_NAMES`.
    """
    docs = docs_source()
    if docs is None:
        return {}
    out: dict[str, bytes] = {}
    for path in sorted(docs.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(docs)
        if any(part in SKIP_DIR_NAMES for part in rel.parts[:-1]):
            continue
        if len(rel.parts) == 1:
            if path.name not in TOP_LEVEL_FILES:
                continue
        else:
            if rel.parts[0] not in USER_DOC_ROOTS:
                continue
            if path.suffix != ".md" and path.name != DOC_SIDECAR:
                continue
        out[f"docs/{rel.as_posix()}"] = path.read_bytes()
    return out
