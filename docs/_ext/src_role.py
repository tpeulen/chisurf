"""A ``{src}`` role that points at ChiSurf's own source, addressed by symbol.

The documentation constantly names code. In the application those links open
the **code editor** at the definition; on the website they have to go somewhere
too, so this role renders them as links into the repository browser.

Addressed by symbol rather than by line number, because a line number is wrong
the moment anything above it is edited and fails silently, while a renamed
symbol fails loudly:

.. code-block:: rst

   :src:`chisurf/core/fitting/fit.py#sample_fit`
   :src:`sample_fit <chisurf/core/fitting/fit.py#sample_fit>`

A target that does not exist is reported as a warning at build time, so a moved
file is caught by the build rather than by a reader.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

from docutils import nodes

#: Where the sources are browsable. Overridden with ``source_base_url`` in conf.
DEFAULT_BASE = "https://gitlab.peulen.xyz/tpeulen/chisurf/-/blob/master/"


def _resolver():
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from chisurf.plugins.core.help.api import source_links

    return source_links


def src_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    """Render ``{src}`path#symbol`` as a link into the source tree."""
    body = text.strip()
    caption = ""
    if "<" in body and body.endswith(">"):
        caption, body = body[: body.index("<")].strip(), body[body.index("<") + 1: -1]

    source_links = _resolver()
    resolved = source_links.resolve(body)
    messages = []
    if resolved is None:
        messages.append(
            inliner.reporter.warning(f"no source file for {body!r}", line=lineno)
        )
        return [nodes.literal(rawtext, caption or body)], messages

    try:
        config = inliner.document.settings.env.config
        base = getattr(config, "source_base_url", DEFAULT_BASE)
    except Exception:
        base = DEFAULT_BASE

    root = pathlib.Path(__file__).resolve().parent.parent.parent
    try:
        relative = resolved.path.relative_to(root).as_posix()
    except ValueError:
        relative = resolved.path.name
    uri = base.rstrip("/") + "/" + relative
    if resolved.line:
        uri += f"#L{resolved.line}"
    elif resolved.missing_symbol:
        messages.append(
            inliner.reporter.warning(
                f"{relative} does not define {resolved.symbol!r}", line=lineno
            )
        )

    label = caption or source_links.link_label(body, resolved)
    node = nodes.reference(rawtext, "", nodes.literal(rawtext, label), refuri=uri)
    return [node], messages


def setup(app) -> dict[str, Any]:
    """Register the role and its configuration."""
    app.add_config_value("source_base_url", DEFAULT_BASE, "env")
    app.add_role("src", src_role)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
