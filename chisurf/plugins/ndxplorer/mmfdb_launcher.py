"""Open a registered burst selection from MMFDB in ndX.

The chisurf side of the ndX ↔ MMFDB round trip. Reuses the existing dataset
picker (the sample/measurement selection widget) and ``mmfdb.datasets.open`` to
resolve an artifact to a local path, then opens it in ChiSurf's ndX window
(:func:`chisurf.plugins.ndxplorer.window.build_ndxplorer_window`), whose
File > Import > From MMFDB runs :func:`pick_burst_selection_path` too.
``modules/ndxplorer`` stays chisurf-free; this module is the only glue.

Usable directly (e.g. from the Code Editor) for a manual round-trip test::

    from chisurf.plugins.ndxplorer.mmfdb_launcher import open_burst_selection_from_mmfdb
    open_burst_selection_from_mmfdb(client=authenticated_mmfdb_client)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Artifact kinds that can be opened in ndX (burst outputs).
#: A burst selection's .bur files reference photons by index in the original TTTR
#: file, so the thing to open is the on-disk burst *folder* (registered as a
#: directory external_reference next to the TTTR files), not an object-store copy.
#: That folder is also the single group for a multi-file run — one entry per run.
BURST_KINDS = ["external_reference"]
#: Data formats to show: the burst output directory (the group).
BURST_FORMATS = ["directory"]


def resolve_dataset_path(client: Any, artifact_id: str) -> str | None:
    """Resolve an MMFDB artifact to a local readable path via ``mmfdb.datasets.open``."""
    if not artifact_id:
        return None
    result = client.call("mmfdb.datasets.open", {"artifact_id": artifact_id}) or {}
    return result.get("local_path") or result.get("path")


def open_path_in_ndxplorer(path: str) -> Any:
    """Open ``path`` in a new ndX window and show it.

    Returns the window, or ``None`` if ndX could not be opened.
    """
    try:
        from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

        window = build_ndxplorer_window(path)
    except Exception as exc:  # pragma: no cover - depends on optional module
        logger.error("ndX could not be opened: %s", exc)
        return None
    window.show()
    window.raise_()
    window.activateWindow()
    return window


def pick_burst_selection_path(
    parent: Any = None,
    scope: str = "all",
    *,
    client: Any,
) -> str | None:
    """Let the user pick a registered burst selection; return its local path.

    ``None`` when nothing was picked or the artifact has no local path.
    """
    from chisurf.gui.widgets.mmfdb.dataset_browser import MmfdbDatasetPickerDialog

    sel = MmfdbDatasetPickerDialog.pick_dataset(
        parent=parent,
        kinds=BURST_KINDS,
        formats=BURST_FORMATS,
        scope=scope,
        client=client,
    )
    if sel is None:
        return None
    path = resolve_dataset_path(client, sel.artifact_id)
    if not path:
        logger.error("Could not resolve a local path for artifact %s", sel.artifact_id)
        return None
    return path


def open_burst_selection_from_mmfdb(
    parent: Any = None,
    scope: str = "all",
    *,
    client: Any,
) -> Any:
    """Pick a registered burst selection from MMFDB and open it in ndX.

    Pick (the sample/measurement selection widget) → resolve the artifact to a
    local path → open in ndX. Returns the ndX window, or ``None`` if nothing
    was selected / it could not be opened.
    """
    path = pick_burst_selection_path(parent, scope, client=client)
    return open_path_in_ndxplorer(path) if path else None


def send_path_to_ndxplorer(path: str, parent: Any = None) -> Any:
    """Open a burst-selection output path (e.g. just produced) in ndX."""
    if not path:
        return None
    return open_path_in_ndxplorer(path)
