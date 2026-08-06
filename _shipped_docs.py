"""Which of ``docs/`` a distribution carries, so the in-app help works.

ChiSurf's help browser reads the documentation from disk at runtime. The tree
it navigates, the pages it renders, the figures in them and the bibliography
its citations resolve against are all files under ``docs/`` — none of which a
wheel or conda package contained, because ``docs/`` sits beside the package
rather than inside it. Installed from a distribution, the Help window opened
onto an empty tree.

So the build copies the documentation *into* the package, at ``chisurf/docs``,
and :func:`chisurf.plugins.core.help.api.toc.docs_root` prefers that copy. The
checkout is never written to: the copy is assembled into the build directory,
so ``docs/`` stays the single place an author edits.

Not all of it ships. ``docs/_build`` is Sphinx output that the browser does not
read, ``docs/_old_manual`` is the retired Word original, ``docs/_ext`` is
Sphinx extension code, and the manual's ``.emf`` figures — 103 MB of them, four
fifths of the whole tree — are a vector format neither a browser nor Qt can
display, which is why ``docs-manual`` converts them to PNG in the first place.
What is left is about 22 MB and is what the reader actually sees.

This module is imported by ``setup.py`` and by the test that keeps the two in
step, which is why it is a module rather than a few lines inside the build.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

#: Suffixes the help browser can read: pages, figures and the data files the
#: renderer resolves against (bibliography, review status, registers).
SHIPPED_SUFFIXES = frozenset(
    {
        ".md",
        ".rst",
        ".png",
        ".svg",
        ".jpg",
        ".jpeg",
        ".gif",
        ".json",
        ".yaml",
        ".bib",
    }
)

#: Directories under ``docs/`` that no reader opens: build output, the retired
#: Word manual, Sphinx extension code, and caches.
SHIPPED_EXCLUDED_DIRS = frozenset({"_build", "_old_manual", "_ext", "__pycache__"})


def iter_shipped_docs(docs: pathlib.Path) -> Iterator[pathlib.Path]:
    """Yield the documentation files a distribution carries.

    Parameters
    ----------
    docs : pathlib.Path
        The repository's ``docs/`` directory.

    Yields
    ------
    pathlib.Path
        Each file to ship, relative to *docs*, in sorted order.

    """
    if not docs.is_dir():
        return
    for path in sorted(docs.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(docs)
        if SHIPPED_EXCLUDED_DIRS.intersection(relative.parts[:-1]):
            continue
        if path.suffix.lower() not in SHIPPED_SUFFIXES:
            continue
        yield relative
