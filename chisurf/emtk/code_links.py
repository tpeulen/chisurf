"""Open a documentation link to source in the code editor.

A page that names a function should be able to *take you there*. The link is
resolved by symbol (:mod:`chisurf.plugins.core.help.api.source_links`) and
handed to the code editor, which already knows how to open a file in a new tab
or raise the tab it is in.

Reusing the editor that is open, rather than opening another one, is the point:
following three references from a page should leave one editor with three tabs,
not three editors.
"""

from __future__ import annotations

import logging
import pathlib
import sys
from typing import Any

from chisurf.core.support.weak_registry import WeakOrderedRegistry

logger = logging.getLogger(__name__)

__all__ = ["open_source"]


_ACTIVE_EMTK_EDITORS = WeakOrderedRegistry()


def register_emtk_editor(editor: Any) -> None:
    """Register an active EMTK code editor instance."""
    if editor not in _ACTIVE_EMTK_EDITORS:
        _ACTIVE_EMTK_EDITORS.append(editor)


def host_in_open_shell(plugin_id: str, then: Any = None) -> bool:
    """Open *plugin_id* in the emtk shell of this process, if one is open; ``then()`` once built.

    Looked up in :data:`sys.modules`, so a process without the shell never imports it.
    """
    import sys

    shell_module = sys.modules.get("chisurf.emtk.main_app")
    host = getattr(shell_module, "host_in_shell", None)
    return bool(host(plugin_id, then)) if callable(host) else False


def unregister_emtk_editor(editor: Any) -> None:
    """Unregister an EMTK code editor instance."""
    if editor in _ACTIVE_EMTK_EDITORS:
        _ACTIVE_EMTK_EDITORS.remove(editor)


def open_source(
    target: str,
    base: pathlib.Path | None = None,
) -> bool:
    """Open *target* in the full code editor.

    Parameters
    ----------
    target : str
        ``path``, ``path#symbol`` or ``src:path#symbol``.
    base : pathlib.Path, optional
        Directory a relative path is resolved against first.

    Returns
    -------
    bool
        Whether the editor was given the file. ``False`` lets the caller fall
        back — a link that resolves to nothing must not be swallowed.
    """
    from chisurf.plugins.core.help.api.source_links import resolve

    resolved = resolve(target, base)
    if resolved is None:
        logger.debug("no source file for %r", target)
        return False

    line_num = resolved.line or None

    if resolved.missing_symbol:
        logger.warning(
            "%s no longer defines %r — the documentation link is stale",
            resolved.path.name,
            resolved.symbol,
        )
    for editor in reversed(_ACTIVE_EMTK_EDITORS):
        if editor is not None:
            try:
                editor.open_file(str(resolved.path), line=line_num)
                return True
            except Exception:
                logger.debug("could not open in active EMTK editor", exc_info=True)

    # No editor yet: the open emtk shell makes one as a dock and hands it the file
    # (chisurf.core.plugin.handoff, the editor's manifest declares open_file), not a second
    # process whose OS window falls behind the main one; without a shell, a standalone editor.
    from chisurf.core.plugin import handoff

    if handoff.available("code_editor", "open_file"):
        try:
            handoff.hand_off(
                "code_editor", "open_file", {"path": str(resolved.path), "line": line_num or 0}
            )
            return True
        except handoff.HandoffError:
            logger.debug("the shell refused the code editor hand-off", exc_info=True)
    try:
        import subprocess
        import sys

        cmd = [
            sys.executable,
            "-m",
            "chisurf.emtk",
            "--plugin",
            "code_editor",
            "--path",
            str(resolved.path),
        ]
        if line_num:
            cmd.extend(["--anchor", str(line_num)])
        subprocess.Popen(cmd)
        return True
    except Exception:
        logger.debug("could not spawn EMTK code editor process", exc_info=True)
        return False
