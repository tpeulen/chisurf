"""Which tool performs which analysis step — the reverse of a provenance record.

A ``.pto`` records that a table was produced by ``burst_lifetime_fitting``. It
deliberately does not record *which program* did it: the container is
tool-agnostic, and a term that named a ChiSurf plugin would have made the file
unreadable by anything else in exactly the way the vocabulary exists to prevent.

That leaves a real gap for a reader. Looking at a result and asking "where does
this come from" is only half the question; the other half is "open the thing that
made it", and until now nothing in ChiSurf could answer it. This module closes it
from the other side: a plugin declares the ``operation_types`` it is the tool for
in its ``manifest.json``, and the map is built by reading manifests — no import,
no Qt, and no list maintained anywhere but in the plugins themselves.

The mapping is deliberately many-to-many. Several tools legitimately produce a
``model_fitting`` result, and a single tool covers several steps; a caller that
needs one answer asks for the first and shows the rest.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from chisurf.core.plugin.manifest import PluginManifest

logger = logging.getLogger(__name__)

__all__ = ["clear_cache", "operation_index", "tools_for_operation"]

#: Cached ``{operation_type: [manifest, ...]}``; built on first use.
_INDEX: dict[str, list] | None = None


def _discover() -> list[PluginManifest]:
    """Return every discoverable plugin manifest, or an empty list."""
    from chisurf.core.plugin.registry import PluginRegistry

    registry = PluginRegistry()
    try:
        registry.discover()
    except Exception:
        logger.debug("plugin discovery failed", exc_info=True)
    return registry.all_manifests


def operation_index(*, refresh: bool = False) -> dict[str, list]:
    """Return ``{operation_type: [manifest, ...]}`` over all discovered plugins.

    Parameters
    ----------
    refresh : bool, optional
        Rebuild instead of returning the cached index. Plugin discovery walks
        the plugin tree, so it is done once per session unless asked otherwise.

    Returns
    -------
    dict
        Manifests are ordered by ``display_name`` within each operation, so a
        menu built from this is stable between runs.
    """
    global _INDEX
    if _INDEX is not None and not refresh:
        return _INDEX
    index: dict[str, list] = {}
    for manifest in _discover():
        for op in getattr(manifest, "operation_types", ()) or ():
            index.setdefault(str(op), []).append(manifest)
    for manifests in index.values():
        manifests.sort(key=lambda m: m.display_name or m.id)
    _INDEX = index
    return index


def tools_for_operation(operation_type: str) -> list:
    """Return the manifests of the tools that perform *operation_type*.

    Parameters
    ----------
    operation_type : str
        An ``_mmfdb_operation.operation_type`` term, as recorded in a container.

    Returns
    -------
    list of PluginManifest
        Empty when no installed tool claims the step — which is a normal answer,
        not an error: a container may carry a result computed by another program.
    """
    if not operation_type:
        return []
    return list(operation_index().get(str(operation_type), ()))


def clear_cache() -> None:
    """Drop the cached index, so the next lookup rediscovers plugins."""
    global _INDEX
    _INDEX = None
