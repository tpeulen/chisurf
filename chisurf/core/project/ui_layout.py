"""The window layout a project stores, independent of the GUI toolkit that draws it.

A ``.cs.pto`` must open whatever front end opens it: the Qt main window today, an emtk one later. So the layout is
recorded in plain terms every front end understands, and a front end's own exact snapshot is only a *hint* beside it::

    "layout": {                       # toolkit-neutral; what every front end restores from
        "schema": 1,
        "window": {"x": 10, "y": 20, "width": 1400, "height": 900, "maximized": false},
        "docks": {"datasets": {"visible": true, "floating": false, "area": "left", "rect": [x, y, w, h]}},
        "views": [{"kind": "fit", "uid": "<fit uid>", "rect": [x, y, w, h], "state": "normal"}],
    },
    "backend": {"qt": {...}}          # optional exact restore of one toolkit (QMainWindow.saveState bytes, ...)

Docks are named by their stable name (the Qt ``objectName``), views by the scientific identity they show (a fit's UID),
never by a toolkit index. A front end applies its own hint when there is one and the neutral layout otherwise; hints of
other toolkits are kept but ignored. Projects written before this module stored the Qt snapshot at the top level
(``geometry``, ``dock_state``, ``mdi_area``); :func:`backend_hint` reads those as the ``qt`` hint.

A front end registers a :class:`LayoutBackend` (the Qt one: :mod:`chisurf.gui.layout_state`). Applying a layout is
presentation: a part that cannot be applied is skipped and reported, it never stops a project from opening.
"""

from __future__ import annotations

import copy
import importlib
import logging
import typing
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SCHEMA = 1
DOCK_AREAS = ("left", "right", "top", "bottom", "center")
VIEW_STATES = ("normal", "maximized", "minimized")
#: Top-level keys of projects written before the neutral layout: the Qt snapshot, now the ``qt`` hint.
LEGACY_QT_KEYS = ("geometry", "dock_state", "mdi_area")
#: Modules that register a backend when imported; tried when no registered backend claims a window.
KNOWN_BACKENDS = ("chisurf.gui.layout_state",)


@dataclass
class LayoutBackend:
    """How one GUI toolkit reads and applies a layout.

    ``matches(window)`` says whether the window is this toolkit's. ``capture(window)`` returns the neutral layout,
    ``apply(window, layout)`` restores it (returns the parts it could not apply). ``capture_hint`` /
    ``apply_hint`` are the optional exact snapshot of this toolkit (``apply_hint`` returns whether it took).
    """

    name: str
    matches: typing.Callable[[typing.Any], bool]
    capture: typing.Callable[[typing.Any], dict]
    apply: typing.Callable[[typing.Any, dict], list[str]]
    capture_hint: typing.Callable[[typing.Any], dict] | None = None
    apply_hint: typing.Callable[[typing.Any, dict], bool] | None = None
    #: The fit views' arrangement (``window_arrangement``: stacking, active, window states, view mode by fit UID):
    #: ``capture_arrangement(window)`` and ``apply_arrangement(window, arrangement, views_by_uid)``.
    capture_arrangement: typing.Callable[[typing.Any], dict | None] | None = None
    apply_arrangement: typing.Callable[[typing.Any, dict, dict], None] | None = None


_BACKENDS: dict[str, LayoutBackend] = {}


def register_backend(backend: LayoutBackend) -> None:
    _BACKENDS[backend.name] = backend


def backend_for(window: typing.Any) -> LayoutBackend | None:
    """The registered backend that claims *window* (importing the known front ends once if none does)."""
    for backend in _BACKENDS.values():
        if backend.matches(window):
            return backend
    for module in KNOWN_BACKENDS:
        try:
            importlib.import_module(module)
        except Exception:  # noqa: BLE001 - a front end that is not installed simply registers nothing
            continue
    return next((b for b in _BACKENDS.values() if b.matches(window)), None)


# ── the neutral record ────────────────────────────────────────────────────────


def _rect(value) -> list[int] | None:
    if isinstance(value, (list, tuple)) and len(value) == 4 and all(isinstance(v, (int, float)) for v in value):
        return [int(v) for v in value]
    return None


def normalize(layout: typing.Any) -> dict:
    """*layout* reduced to the fields of the schema, every value checked; unknown or malformed parts are dropped."""
    if not isinstance(layout, dict):
        return {}
    out: dict = {"schema": SCHEMA}
    window = layout.get("window")
    if isinstance(window, dict):
        w = {k: int(window[k]) for k in ("x", "y", "width", "height") if isinstance(window.get(k), (int, float))}
        if len(w) == 4 and w["width"] > 0 and w["height"] > 0:
            w["maximized"] = bool(window.get("maximized", False))
            out["window"] = w
    docks = {}
    for name, dock in (layout.get("docks") or {}).items() if isinstance(layout.get("docks"), dict) else ():
        if not isinstance(name, str) or not name or not isinstance(dock, dict):
            continue
        d = {"visible": bool(dock.get("visible", True)), "floating": bool(dock.get("floating", False))}
        if dock.get("area") in DOCK_AREAS:
            d["area"] = dock["area"]
        if _rect(dock.get("rect")):
            d["rect"] = _rect(dock["rect"])
        docks[name] = d
    if docks:
        out["docks"] = docks
    views = []
    for view in layout.get("views") or [] if isinstance(layout.get("views"), list) else []:
        if not isinstance(view, dict) or not isinstance(view.get("uid"), str) or not view["uid"]:
            continue
        v = {"kind": str(view.get("kind") or "fit"), "uid": view["uid"],
             "state": view.get("state") if view.get("state") in VIEW_STATES else "normal"}
        if _rect(view.get("rect")):
            v["rect"] = _rect(view["rect"])
        views.append(v)
    if views:
        out["views"] = views
    return out


def backend_hint(state: dict, name: str) -> dict | None:
    """The exact snapshot of toolkit *name* in a saved UI state (the legacy top-level Qt keys count as ``qt``)."""
    hints = state.get("backend") if isinstance(state.get("backend"), dict) else {}
    hint = hints.get(name)
    if isinstance(hint, dict) and hint:
        return copy.deepcopy(hint)
    if name == "qt":
        legacy = {k: state[k] for k in LEGACY_QT_KEYS if state.get(k)}
        return legacy or None
    return None


# ── capture / restore ─────────────────────────────────────────────────────────


def capture(window: typing.Any) -> dict:
    """``{"layout": ..., "backend": {name: hint}}`` of *window*; empty when no front end claims it."""
    backend = backend_for(window)
    if backend is None:
        return {}
    state: dict = {}
    try:
        state["layout"] = normalize(backend.capture(window))
    except Exception as exc:  # noqa: BLE001 - a layout that cannot be read is not saved; the science still is
        logger.warning("window layout not captured: %s", exc)
    if backend.capture_hint is not None:
        try:
            hint = backend.capture_hint(window)
            if hint:
                state["backend"] = {backend.name: hint}
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s layout hint not captured: %s", backend.name, exc)
    return state


def restore(window: typing.Any, state: dict) -> list[str]:
    """Apply a saved layout to *window*: this toolkit's exact hint if there is one, else the neutral layout.

    Returns what could not be applied (empty when everything was); nothing here raises.
    """
    backend = backend_for(window)
    if backend is None or not isinstance(state, dict):
        return ["no front end claims this window"] if backend is None else []
    layout = normalize(state.get("layout"))
    hint = backend_hint(state, backend.name)
    if hint and backend.apply_hint is not None:
        try:
            if backend.apply_hint(window, hint):
                # The hint is the window and its docks; the views are restored from the neutral record.
                layout = {k: v for k, v in layout.items() if k not in ("window", "docks")}
        except Exception as exc:  # noqa: BLE001 - fall back to the neutral layout
            logger.warning("%s layout hint not applied: %s", backend.name, exc)
    if len(layout) <= 1:
        return []
    try:
        return list(backend.apply(window, layout) or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("window layout not applied: %s", exc)
        return [str(exc)]


__all__ = ["LayoutBackend", "backend_for", "backend_hint", "capture", "normalize", "register_backend", "restore"]
