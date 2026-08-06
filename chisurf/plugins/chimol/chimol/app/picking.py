from __future__ import annotations

import math
from typing import Optional

# Numba is required. The `_HAVE_NUMBA` guard it replaces made every kernel
# here optional and every fallback beside it unexercised -- which is how the
# ray tracer's pure-NumPy twin came to be silently broken while every test
# passed.
import numba as nb
import numpy as np
from qtpy import QtCore, QtGui


@nb.jit(nopython=True, nogil=True, cache=True)
def _pick_from_ray_nb(
    pts: np.ndarray,
    cam: np.ndarray,
    ray_dir: np.ndarray,
    thresh2: float,
) -> int:
    n = pts.shape[0]
    best_i = -1
    best_d2 = thresh2
    for i in range(n):
        x0 = pts[i, 0]
        y0 = pts[i, 1]
        z0 = pts[i, 2]
        vx = x0 - cam[0]
        vy = y0 - cam[1]
        vz = z0 - cam[2]
        proj = vx * ray_dir[0] + vy * ray_dir[1] + vz * ray_dir[2]
        if proj <= 0.0:
            continue
        cx = cam[0] + proj * ray_dir[0]
        cy = cam[1] + proj * ray_dir[1]
        cz = cam[2] + proj * ray_dir[2]
        dx = x0 - cx
        dy = y0 - cy
        dz = z0 - cz
        d2 = dx * dx + dy * dy + dz * dz
        if d2 < best_d2:
            best_d2 = d2
            best_i = i
    return best_i


def _project_points_to_screen(
    coords: np.ndarray,
    view,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Project scene points to widget pixels, through the renderer itself.

    Parameters
    ----------
    coords : numpy.ndarray
        ``(n, 3)`` positions in scene space.
    view : chimol.renderer.qtgl.QtGLRenderer
        The widget that draws them.

    Returns
    -------
    tuple of numpy.ndarray, or None
        ``(x, y, visible)``, or ``None`` when there is nothing to project or the
        renderer cannot answer.

    Notes
    -----
    This used to build a camera basis of its own from ``view.cameraPosition()``
    and a ``view.opts`` dictionary -- pyqtgraph's ``GLViewWidget`` API, left
    behind when the renderer was replaced. The renderer kept an ``opts`` shim
    "for compatibility with picking helpers" whose ``center`` is a
    ``QVector3D``; this function fed it to ``numpy.asarray``, which raises. So
    **every click raised**, the exception was swallowed by the caller, and
    picking did nothing at all.

    A picker must project the way the renderer draws, or it picks where the
    molecule is not -- and the hand-rolled version ignored both the panel column
    and the sequence strip, so even repaired it would have been out by the
    strip's height.
    """
    pts = np.asarray(coords, dtype=float)
    if pts.ndim != 2 or pts.shape[0] == 0:
        return None
    project = getattr(view, "project_to_screen", None)
    if not callable(project):
        return None
    try:
        sx, sy, visible = project(pts)
    except Exception:
        return None
    if sx.shape[0] != pts.shape[0]:
        return None
    return sx, sy, visible


def pick_residue_from_click(
    coords: np.ndarray,
    view,
    ev: QtGui.QMouseEvent,  # type: ignore[name-defined]
    radius_px: float,
) -> Optional[int]:
    """Return index of the residue closest to the click in screen space."""

    projected = _project_points_to_screen(coords, view)
    if projected is None:
        return None

    sx, sy, mask = projected
    if not np.any(mask):
        return None

    try:
        pos = ev.pos()
        click_x = float(pos.x())
        click_y = float(pos.y())
    except Exception:
        click_x = float(ev.x())
        click_y = float(ev.y())

    valid_idx = np.nonzero(mask)[0]
    dx = sx[mask] - click_x
    dy = sy[mask] - click_y
    dist2 = dx * dx + dy * dy
    if dist2.size == 0:
        return None

    i_local = int(np.argmin(dist2))
    if i_local < 0 or i_local >= dist2.shape[0]:
        return None

    try:
        radius2 = float(radius_px) ** 2
    except Exception:
        radius2 = 64.0  # default 8px squared

    if not np.isfinite(dist2[i_local]) or dist2[i_local] > radius2:
        return None

    return int(valid_idx[i_local])


def pick_residues_in_rect(
    coords: np.ndarray,
    view,
    rect,
) -> np.ndarray:
    try:
        if isinstance(rect, QtCore.QRect):
            x0 = float(rect.left())
            x1 = float(rect.right())
            y0 = float(rect.top())
            y1 = float(rect.bottom())
        else:
            x0 = float(getattr(rect, "left", lambda: 0)())
            x1 = float(getattr(rect, "right", lambda: 0)())
            y0 = float(getattr(rect, "top", lambda: 0)())
            y1 = float(getattr(rect, "bottom", lambda: 0)())
    except Exception:
        return np.zeros(0, dtype=int)

    xmin = min(x0, x1)
    xmax = max(x0, x1)
    ymin = min(y0, y1)
    ymax = max(y0, y1)

    projected = _project_points_to_screen(coords, view)
    if projected is None:
        return np.zeros(0, dtype=int)

    sx, sy, mask = projected
    if not np.any(mask):
        return np.zeros(0, dtype=int)

    sel_mask = (
        mask
        & (sx >= xmin)
        & (sx <= xmax)
        & (sy >= ymin)
        & (sy <= ymax)
    )

    if not np.any(sel_mask):
        return np.zeros(0, dtype=int)

    try:
        arr = np.asarray(np.nonzero(sel_mask)[0], dtype=int)
    except Exception:
        arr = np.zeros(0, dtype=int)
    return arr


def pick_atom_from_click(
    coords: np.ndarray,
    view,
    ev: QtGui.QMouseEvent,  # type: ignore[name-defined]
    radius_px: float,
    unpickable: Optional[np.ndarray] = None,
) -> Optional[int]:
    """Return index of the atom closest to the click in screen space.

    Parameters
    ----------
    coords : np.ndarray
        (N, 3) array of atom coordinates.
    view : QtGLRenderer
        The GL view widget.
    ev : QtGui.QMouseEvent
        The mouse event.
    radius_px : float
        Click radius in pixels.
    unpickable : np.ndarray, optional
        Boolean over atoms, from PyMOL's ``mask``. Masked atoms are excluded
        from the search, which is the whole point of the command: with one
        molecule in front of another, it stops the click reaching the one
        behind.

    Returns
    -------
    int or None
        Index of the picked atom, or None if no atom is within the radius.
    """
    projected = _project_points_to_screen(coords, view)
    if projected is None:
        return None

    sx, sy, mask = projected
    if unpickable is not None:
        blocked = np.asarray(unpickable, dtype=bool)
        if blocked.shape[0] == mask.shape[0]:
            mask = mask & ~blocked
    if not np.any(mask):
        return None

    try:
        pos = ev.pos()
        click_x = float(pos.x())
        click_y = float(pos.y())
    except Exception:
        click_x = float(ev.x())
        click_y = float(ev.y())

    valid_idx = np.nonzero(mask)[0]
    dx = sx[mask] - click_x
    dy = sy[mask] - click_y
    dist2 = dx * dx + dy * dy
    if dist2.size == 0:
        return None

    i_local = int(np.argmin(dist2))
    if i_local < 0 or i_local >= dist2.shape[0]:
        return None

    try:
        radius2 = float(radius_px) ** 2
    except Exception:
        radius2 = 64.0  # default 8px squared

    if not np.isfinite(dist2[i_local]) or dist2[i_local] > radius2:
        return None

    return int(valid_idx[i_local])


__all__ = ["pick_residue_from_click", "pick_residues_in_rect", "pick_atom_from_click"]
