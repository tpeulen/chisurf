"""A ``{cite}`` role that resolves against ChiSurf's own bibliography.

The documentation cites papers by key — ``{cite}`magde1972``` — and the key is
resolved in `docs/references/bibliography.yaml`. The help browser expands the
same role with the same module, so a citation reads and links identically in the
application and on the website, and there is one place to correct a reference.

The role renders as a link: to the DOI where one is recorded, otherwise to a
literature search for the title. Sphinx therefore needs no bibliography
extension and no BibTeX toolchain.

An unknown key is rendered as literal text and reported as a warning, so a typo
is loud at build time rather than silently dropped.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

from docutils import nodes


def _bibliography_module():
    """Import ChiSurf's bibliography helper, with the repo on the path."""
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from chisurf.plugins.core.help.api import bibliography

    return bibliography


def cite_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    """Render ``{cite}`key``` (or ``:cite:`key1,key2```) as reference links."""
    bib = _bibliography_module()
    entries = bib.bibliography()
    children: list[nodes.Node] = []
    messages: list[nodes.Node] = []

    keys = [key.strip() for key in text.split(",") if key.strip()]
    for index, key in enumerate(keys):
        if index:
            children.append(nodes.Text("; "))
        entry = entries.get(key)
        if entry is None:
            reporter = inliner.reporter
            messages.append(
                reporter.warning(f"unknown citation key {key!r}", line=lineno)
            )
            children.append(nodes.literal(rawtext, key))
            continue
        children.append(
            nodes.reference(
                rawtext,
                bib.short_citation(entry),
                refuri=bib.entry_url(entry),
            )
        )
    return children, messages


def setup(app) -> dict[str, Any]:
    """Register the role."""
    app.add_role("cite", cite_role)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
