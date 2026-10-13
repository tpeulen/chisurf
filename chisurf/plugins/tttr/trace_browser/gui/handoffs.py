"""The Trace Browser's hand-offs: its *HMM*, *TW* and *NDX* requests as plugin hand-offs.

The model records a request (``open_intensity_trace``, ``open_time_window``, ``open_ndxplorer``
plus a payload); the app passes it to ``on_request(name, payload)``. This module is that
callback in ChiSurf: each request becomes a hand-off (:mod:`chisurf.core.plugin.handoff`) to the
tool that declares the payload kind in its manifest's ``accepts``:

* ``open_intensity_trace`` -> ``intensity_trace`` / ``tttr_trace`` (file, bin window, setup);
* ``open_time_window`` -> ``tttr_time_windows`` / ``tttr_files`` (files, bin window);
* ``open_ndxplorer`` -> ``ndxplorer`` / ``open_path`` (the burst-analysis folder the model wrote).

The host (the emtk shell) opens the tool as a dock and hands it the payload once it is built.
Without a host there is no handler and the three buttons are greyed. No toolkit is imported.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from typing import Any

from chisurf.core.plugin import handoff

#: ``request name -> (target plugin, payload kind, payload of the request -> payload of the kind)``.
ROUTES: dict[str, tuple[str, str, Callable[[dict], dict]]] = {
    "open_intensity_trace": ("intensity_trace", "tttr_trace", dict),
    "open_time_window": ("tttr_time_windows", "tttr_files", dict),
    "open_ndxplorer": (
        "ndxplorer",
        "open_path",
        lambda payload: {"path": payload["folder"], "file": payload.get("file")},
    ),
}


def _check_files(payload: dict) -> None:
    """Refuse a file that vanished since it was listed, before a tool opens for it."""
    paths = [payload["file"]] if "file" in payload else list(payload.get("files") or [])
    if "folder" in payload:
        paths = [payload["folder"]]
    for path in paths:
        if not pathlib.Path(str(path)).exists():
            raise FileNotFoundError(f"{path} does not exist")


def handle(name: str, payload: dict) -> Any:
    """Hand request *name* with *payload* to its tool; raise when that cannot be done."""
    route = ROUTES.get(name)
    if route is None:
        raise ValueError(f"unknown request {name!r}")
    plugin_id, kind, adapt = route
    _check_files(payload)
    return handoff.hand_off(plugin_id, kind, adapt(dict(payload)))


def default_request_handler() -> Callable[[str, dict], Any] | None:
    """:func:`handle` when a host is open that takes a hand-off, else ``None`` (greyed buttons).

    A route whose tool is missing from the host fails when pressed, and says so.
    """
    if not any(handoff.available(plugin, kind) for plugin, kind, _ in ROUTES.values()):
        return None
    return handle
