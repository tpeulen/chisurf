"""What a selection looks like, built where every host can build it.

Why this is not in the widget
-----------------------------
It was. ``renderer/view.py`` -- the **Qt** viewer -- held both the marker
geometry and the rule for how big a marker is, so a browser had no path to
either: a selection made in the sequence strip highlighted nothing in 3-D, and
there was nowhere to put the fix that did not mean copying the code. Two viewers
that disagree about what a selection looks like are two programs.

The rule is PyMOL's, and both halves of it are here: the size in pixels
(``ExecutiveGetAdjustedSelectionWidth``) and the marker itself
(``ExecutiveSetupIndicatorPassMultipassImmediate`` -- three concentric squares,
the selection colour outside, black, then white). The squares are drawn by
``wgsl/marker.wgsl``; this module only says where they go and how wide they are.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .scene import Geometry, SceneObject

__all__ = [
    "SELECTION_COLOR",
    "atoms_in_columns",
    "marker_width",
    "screen_vertex_scale",
    "selection_markers",
]

#: PyMOL's selection pink, from its own indicator pass.
SELECTION_COLOR: tuple[float, float, float, float] = (1.0, 0.2, 0.6, 1.0)

#: The clamp band and the scale, PyMOL's ``selection_width``,
#: ``selection_width_max`` and ``selection_width_scale``. The reference radius
#: is its ``stick_radius``, which is what the marker is measured against.
#:
#: The band is **wider than PyMOL's** (3-10), deliberately: a three-pixel marker
#: cannot show a three-band marker -- the white core is a fifth of a pixel --
#: so at the floor a selection resolved to one pink speck per atom, which is
#: what "the selection is a scatter of dots" was looking at. Migration 14
#: carries the change to profiles that already exist.
DEFAULT_WIDTH = 7.0
DEFAULT_WIDTH_MAX = 16.0
DEFAULT_WIDTH_SCALE = 2.0
DEFAULT_REFERENCE_RADIUS = 0.25


def screen_vertex_scale(fov_deg: float, distance: float, height: float) -> float:
    """Return the scene units one pixel covers at the pivot's depth.

    Parameters
    ----------
    fov_deg : float
        Vertical field of view, in degrees.
    distance : float
        Camera distance to the pivot.
    height : float
        Viewport height, in pixels.

    Returns
    -------
    float
        PyMOL's ``SceneGetScreenVertexScale``. Zero when the inputs cannot
        describe a viewport, which :func:`marker_width` reads as "no camera
        yet" rather than dividing by it.
    """
    try:
        rows = max(float(height), 1.0)
        half = math.radians(max(float(fov_deg), 1e-3)) * 0.5
        return 2.0 * float(distance) * math.tan(half) / rows
    except (TypeError, ValueError):
        return 0.0


def marker_width(v_scale: float, config: dict | None = None) -> float:
    """Return the indicator's width in **pixels**, by PyMOL's rule.

    Parameters
    ----------
    v_scale : float
        Scene units per pixel, from :func:`screen_vertex_scale`.
    config : dict, optional
        The display configuration's ``selection`` section.

    Returns
    -------
    float
        ``width_scale * |reference radius| / v_scale``, clamped to
        ``[width, width_max]`` -- so the marker grows as you zoom in and stops
        at sixteen pixels. With no usable camera the clamp's upper end is returned:
        a marker too large is visible and a marker of zero pixels is a
        selection that silently did not draw.
    """
    cfg = config or {}
    try:
        low = float(cfg.get("width", DEFAULT_WIDTH))
        high = float(cfg.get("width_max", DEFAULT_WIDTH_MAX))
        scale = float(cfg.get("width_scale", DEFAULT_WIDTH_SCALE))
        radius = float(cfg.get("width_reference_radius", DEFAULT_REFERENCE_RADIUS))
    except (TypeError, ValueError):
        low, high, scale, radius = (
            DEFAULT_WIDTH, DEFAULT_WIDTH_MAX,
            DEFAULT_WIDTH_SCALE, DEFAULT_REFERENCE_RADIUS,
        )
    if not (v_scale > 0.0):
        return high
    return float(min(max(scale * abs(radius) / v_scale, low), high))


def atoms_in_columns(atom_residues, residue_numbers, columns) -> np.ndarray:
    """Mask the atoms belonging to the residues at the given strip columns.

    Parameters
    ----------
    atom_residues : array_like
        ``(n,)`` residue number **per atom**.
    residue_numbers : sequence of int
        The residue number of each column of the sequence strip.
    columns : sequence of int
        Column indices the strip selected.

    Returns
    -------
    numpy.ndarray
        ``(n,)`` bool.

    Notes
    -----
    The mapping is the whole point, and getting it wrong is silent. A strip
    column is a *position in the sequence*; an atom carries a *residue number*,
    and the two coincide only for a chain numbered from one with no gaps. T4
    lysozyme has 164 residues and 1363 atoms, so treating a column as an atom
    index marks the first 164 atoms -- a plausible-looking pink smear near the
    N-terminus.
    """
    residues = np.asarray(atom_residues, dtype=np.int64).reshape(-1)
    if not residues.size:
        return np.zeros(0, dtype=bool)
    wanted = {
        int(residue_numbers[index])
        for index in (int(c) for c in (columns or []))
        if 0 <= index < len(residue_numbers)
    }
    if not wanted:
        return np.zeros(residues.shape[0], dtype=bool)
    return np.isin(residues, np.fromiter(wanted, dtype=np.int64, count=len(wanted)))


def selection_markers(
    centers,
    width: float,
    colour: Sequence[float] | None = None,
    *,
    object_id: str = "selection",
) -> list[SceneObject]:
    """Build the indicator geometry for a set of selected positions.

    Parameters
    ----------
    centers : array_like
        ``(n, 3)`` positions of the selected atoms.
    width : float
        Marker width in pixels, from :func:`marker_width`.
    colour : sequence of float, optional
        RGBA in ``0..1``; defaults to PyMOL's selection pink.
    object_id : str, optional
        Scene-object id, so a second marker set can coexist.

    Returns
    -------
    list of SceneObject
        Empty when there is nothing selected.

    Notes
    -----
    ``render_mode="overlay"``, as PyMOL's ``selection_overlay`` defaults to on:
    the marker is drawn over the representation rather than hidden by it. A
    marker you can only see when nothing is in front of it does not tell you
    what is selected on the far side of the molecule -- which is exactly where a
    box select reaches.

    ``meta["glyph"]`` is what routes this to ``marker.wgsl``. Without it the
    backend draws point geometry as sphere impostors, and a selection comes out
    as a scatter of shaded pink dots -- which is how the missing glyph was
    reported.
    """
    points = np.ascontiguousarray(centers, dtype=np.float32).reshape(-1, 3)
    if not len(points):
        return []

    rgba = np.asarray(
        SELECTION_COLOR if colour is None else colour, dtype=np.float32
    ).reshape(-1)
    if rgba.shape[0] != 4:
        rgba = np.asarray(SELECTION_COLOR, dtype=np.float32)

    geometry = Geometry(
        kind="points",
        positions=points,
        colors=np.tile(rgba, (points.shape[0], 1)),
        meta={
            "glyph": "selection",
            "size": float(width),
            # Stated, though it is the default: this is a size in *pixels*, and
            # the flag that says otherwise is the one thing that would turn
            # every marker into a sphere that grows as the camera approaches.
            "world_radius": False,
        },
    )
    return [SceneObject(id=object_id, geometry=geometry, render_mode="overlay")]
