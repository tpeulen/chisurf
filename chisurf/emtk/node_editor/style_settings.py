"""Node-graph plotting, as the Plot Settings panel drives it.

Every node graph in ChiSurf -- Global View, the light-path simulator, the
provenance inspector, the general node editor -- is an
:class:`~chisurf.emtk.node_editor.control.GraphControl`, and a grid under it is
a background, not a workspace: at the emtk default weight it competes with the
thin ownership edges drawn on top of it. The Plot Settings panel owns a
``node_graph`` section under ``gui.plot`` in ``settings_chisurf.yaml``; this
module is the one place that reads it onto an editor's style, so the panel,
the defaults and the graphs cannot drift apart.

Qt appears nowhere here except in :func:`refresh_open_graphs`, and even there
behind a guarded import, so a Qt-free test can style an editor with these.
"""

from __future__ import annotations

import logging
import typing

from emtk import nodes as emtk_nodes

__all__ = [
    "NODE_GRAPH_DEFAULTS",
    "apply_node_graph_settings",
    "node_graph_settings",
    "refresh_open_graphs",
]

logger = logging.getLogger(__name__)

#: The shipped values, mirrored in ``settings_chisurf.yaml``. A key missing
#: from a user's file -- any file written before the section existed -- reads
#: as one of these.
NODE_GRAPH_DEFAULTS: dict = {
    # The grid: on, and quieter than a workspace grid. Half a pixel draws a
    # hairline on either scaling -- at the integer default a HiDPI screen
    # doubles it to two device pixels, and the background then out-weighs
    # the one-pixel ownership edges it sits under.
    "show_grid": True,
    "grid_line_width": 0.5,
    "grid_opacity": 0.06,
    "grid_spacing": 24.0,
    # The disc radius a new Global View window starts its node-size control
    # at. A window's own slider stays the authority once it is open; this is
    # only where that slider begins.
    "node_size": 13.0,
}

#: The primary grid lines read slightly stronger than the minor ones, the
#: ratio emtk's own palette uses.
_PRIMARY_RATIO = 1.7


def node_graph_settings() -> dict:
    """The node-graph settings, defaults filled in from :data:`NODE_GRAPH_DEFAULTS`.

    Returns
    -------
    dict
        Every key of :data:`NODE_GRAPH_DEFAULTS`, coerced to its default's
        type. Reads the live ``cs_settings`` when ChiSurf's settings are
        importable and the defaults when they are not -- a Qt-free test, or a
        host that has not loaded a settings folder, still gets a styleable
        editor.
    """
    stored: dict = {}
    try:
        from chisurf.core.settings import cs_settings

        stored = dict(cs_settings.get("gui", {}).get("plot", {}).get("node_graph", {}) or {})
    except Exception:  # noqa: BLE001 - no settings folder is no reason to fail a draw
        logger.debug("node graph settings: reading defaults", exc_info=True)

    out = dict(NODE_GRAPH_DEFAULTS)
    for key, default in NODE_GRAPH_DEFAULTS.items():
        if key not in stored:
            continue
        try:
            out[key] = type(default)(stored[key])
        except (TypeError, ValueError):
            logger.warning(
                "node graph setting %s=%r is not a %s; using the default",
                key,
                stored[key],
                type(default).__name__,
            )
    return out


def apply_node_graph_settings(style: typing.Any) -> None:
    """Write the node-graph settings onto an editor style, in place.

    Parameters
    ----------
    style : emtk.nodes.Style
        The style of an editor about to draw, or one whose look should catch
        up with the panel.

    Notes
    -----
    The grid is drawn white at the configured opacity -- primary lines at
    :data:`_PRIMARY_RATIO` times it -- because every ChiSurf graph runs on the
    dark palette; a graph that restyles its background afterwards (Global
    View's is darker than emtk's) keeps these lines, which is the point: the
    setting is *the* grid, wherever it is drawn.
    """
    settings = node_graph_settings()
    style.grid_spacing = max(float(settings["grid_spacing"]), 4.0)
    style.grid_line_width = max(float(settings["grid_line_width"]), 0.0)

    alpha = max(float(settings["grid_opacity"]), 0.0)
    minor = min(int(round(255.0 * alpha)), 255)
    primary = min(int(round(255.0 * alpha * _PRIMARY_RATIO)), 255)
    style.colors[emtk_nodes.Col.GRID_LINE] = (255, 255, 255, minor)
    style.colors[emtk_nodes.Col.GRID_LINE_PRIMARY] = (255, 255, 255, primary)

    if bool(settings["show_grid"]):
        style.flags |= emtk_nodes.StyleFlags.GRID_LINES
    else:
        style.flags &= ~emtk_nodes.StyleFlags.GRID_LINES


def refresh_open_graphs() -> int:
    """Re-apply the settings to every open node graph, and repaint it.

    Returns
    -------
    int
        How many graphs caught up. Zero is normal: it means none is open, not
        that anything failed.

    Notes
    -----
    Found by walking the top-level widgets and asking for an editor -- the
    Graph View window keeps one at ``model.control``, a plain host at
    ``control`` -- rather than by keeping a registry, because a registry
    would have to remember to forget. Windows whose graph is embedded deeper
    (an MDI subwindow's child, say) are not top-level and catch up when they
    are next opened; a style is cheap to rebuild.
    """
    try:
        from qtpy import QtWidgets
    except Exception:  # noqa: BLE001 - no Qt, nothing to walk
        return 0

    touched = 0
    for widget in QtWidgets.QApplication.topLevelWidgets():
        model = getattr(widget, "model", None)
        control = getattr(widget, "control", None) or getattr(model, "control", None)
        editor = getattr(control, "editor", None)
        if editor is None or getattr(editor, "style", None) is None:
            continue
        apply_node_graph_settings(editor.style)
        host = getattr(widget, "host", widget)
        host.update()
        touched += 1
    return touched
