"""The 18-float camera view tuple, in PyMOL's layout.

This is the one place that knows how a camera is serialised, so the GL backend
(:mod:`.qtgl`), the offline raytracer (:mod:`.raytracer`) and the ``get_view`` /
``set_view`` commands all agree. It is deliberately Qt-free.

Layout
------
The tuple matches PyMOL's ``cmd.get_view()`` exactly, so a view can be copied
between the two programs::

    0-8    rotation matrix, **camera basis in the columns**
    9-11   camera position in camera space: ``(0, 0, -distance)``
    12-14  origin of rotation (the point the camera orbits), in world space
    15     near clipping plane
    16     far clipping plane
    17     field of view in degrees, **negated for a perspective camera**

The sign of slot 17 is the orthoscopic flag, and it reads backwards from the
obvious guess: PyMOL writes ``-field_of_view`` for its default *perspective*
camera and ``+field_of_view`` when ``orthoscopic`` is on. Verified against
``cmd.get_view()`` with the setting toggled both ways.

The column convention in slots 0-8 is load-bearing and easy to get backwards.
chimol works internally with a **world-to-camera** rotation whose *rows* are the
camera's right/up/back axes in world space; PyMOL's tuple stores the transpose
of that. Reading PyMOL's nine floats straight into a row-major 3x3 and using
its rows yields a camera that is the inverse rotation, which renders the
molecule mirrored — the failure this module exists to prevent.

Two older layouts are still accepted on input, since projects and scripts carry
them:

* **chimol matrix form** — the same rotation but stored row-major (rows are the
  camera basis), with the distance in slot 9 and slots 10-11 zero.
* **chimol legacy angles** — an identity matrix with the distance in slot 9 and
  elevation/azimuth in degrees in slots 10-11.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

DEFAULT_FOV = 20.0
"""Vertical field of view in degrees, matching PyMOL's ``field_of_view`` default."""

__all__ = [
    "ViewState",
    "pack_view_state",
    "unpack_view_state",
    "rotation_from_angles",
    "distance_for_radius",
    "framing_radius",
    "MIN_FRAMING_RADIUS",
]


@dataclass
class ViewState:
    """A decoded camera view.

    Attributes
    ----------
    rotation : np.ndarray
        The ``(3, 3)`` world-to-camera rotation; its rows are the camera's
        right, up and backward axes in world space.
    distance : float
        Distance from the camera to ``target``.
    target : np.ndarray
        World-space point the camera orbits.
    near, far : float
        Clipping planes.
    fov : float
        Vertical field of view in degrees (always positive).
    orthoscopic : bool
        Whether the source tuple asked for an orthoscopic camera. PyMOL encodes
        this as the sign of slot 17; chimol only renders perspective, but the
        flag is carried through so a view round-trips unchanged.
    """

    rotation: np.ndarray
    distance: float
    target: np.ndarray
    near: float
    far: float
    fov: float = DEFAULT_FOV
    orthoscopic: bool = False


def distance_for_radius(
    radius: float,
    fov: float = DEFAULT_FOV,
    *,
    aspect: float | None = None,
) -> float:
    """Camera distance at which a sphere of ``radius`` just fills the view.

    This is PyMOL's framing rule, read from ``SceneWindowSphere`` in its source::

        float dist = 2.f * radius / GetFovWidth(G);          // 2*tan(fov/2)
        if (I->Height > I->Width) dist *= Height / Width;

    which is ``d = radius / tan(fov / 2)``, widened when the viewport is taller
    than it is wide. Framing therefore follows the field of view: widening the
    lens pulls the camera in rather than shrinking the molecule, which is what
    makes a ``zoom`` here and a ``zoom`` there put the molecule at the same size
    on screen.

    Parameters
    ----------
    radius : float
        Bounding radius of what must be visible, in scene units.
    fov : float, optional
        Vertical field of view in degrees.
    aspect : float, optional
        Viewport width divided by height. Only a **portrait** viewport changes
        the result: PyMOL corrects when height exceeds width, because the field
        of view is vertical and the horizontal extent is then the binding one.

    Returns
    -------
    float
        Camera-to-target distance.
    """
    half_tan = math.tan(math.radians(abs(float(fov))) * 0.5)
    if half_tan <= 1e-6:
        return max(float(radius), 1.0)
    distance = float(radius) / half_tan
    if aspect is not None and aspect > 0.0 and aspect < 1.0:
        distance /= aspect
    return max(distance, 1.0)


#: PyMOL floors the zoom radius here (``MAX_VDW`` in ``layer0/Base.h``), so a
#: single atom or a tiny fragment does not put the camera inside it.
MIN_FRAMING_RADIUS = 2.5


def framing_radius(
    points: np.ndarray, *, complete: bool = False, scale: float = 1.0
) -> float:
    """Radius that ``zoom`` should fit, following PyMOL's two modes.

    PyMOL's default (``complete=0``) frames on the **largest half-extent of the
    axis-aligned bounding box**, which is smaller than the bounding sphere and so
    fills the window better while occasionally clipping a corner. ``complete=1``
    guarantees nothing is clipped, and frames on the bounding sphere instead.

    The box is measured on the **world** axes, not the camera's. That looks like
    an oversight but is deliberate and worth preserving: it makes the zoom level
    independent of the current orientation, so turning the molecule does not make
    it breathe. Verified by zooming a 30x5 A bar at 0/30/45/90 degrees of roll —
    PyMOL returns the same distance every time, matching the world-axis extent
    (30 A) rather than the camera-space one (which falls to 21 A at 45 degrees).

    Parameters
    ----------
    points : numpy.ndarray
        ``(N, 3)`` coordinates to fit.
    complete : bool, optional
        Use the bounding sphere so no point can be clipped.
    scale : float, optional
        Scene units per Angstrom, so that PyMOL's ``MAX_VDW`` floor is applied in
        the same units as ``points``.

    Returns
    -------
    float
        Radius in the same units as ``points``; 0.0 when there is nothing to fit.

    Notes
    -----
    PyMOL measures the extent of the *rendered representation*, not of the atom
    centres, so its radius runs a little larger than this one — about 0.7 A on
    148L with a cartoon shown. That padding is representation-dependent and is
    not modelled here; pass ``buffer`` if you want room to spare.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[0] == 0 or pts.shape[1] != 3:
        return 0.0

    lo = pts.min(axis=0)
    hi = pts.max(axis=0)
    if complete:
        centre = (lo + hi) * 0.5
        radius = float(np.max(np.linalg.norm(pts - centre, axis=1)))
    else:
        radius = float(np.max(hi - lo) * 0.5)
    return max(radius, MIN_FRAMING_RADIUS * float(scale))


def rotation_from_angles(elevation: float, azimuth: float) -> np.ndarray:
    """Build a world-to-camera rotation from the legacy elevation/azimuth pair."""
    el = math.radians(float(elevation))
    az = math.radians(float(azimuth))
    ce, se = math.cos(el), math.sin(el)
    ca, sa = math.cos(az), math.sin(az)
    rx = np.array([[1.0, 0.0, 0.0], [0.0, ce, -se], [0.0, se, ce]])
    rz = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
    return rx @ rz


def pack_view_state(
    rotation: np.ndarray,
    distance: float,
    target: Sequence[float],
    near: float,
    far: float,
    fov: float = DEFAULT_FOV,
    orthoscopic: bool = False,
) -> list[float]:
    """Serialise a camera into the 18-float PyMOL tuple.

    Parameters
    ----------
    rotation : np.ndarray
        ``(3, 3)`` world-to-camera rotation, rows being the camera basis.
    distance : float
        Camera-to-target distance.
    target : sequence of float
        World-space orbit point.
    near, far : float
        Clipping planes.
    fov : float, optional
        Vertical field of view in degrees.
    orthoscopic : bool, optional
        Controls the sign of slot 17: positive when orthoscopic, negative for
        the perspective camera, matching PyMOL.

    Returns
    -------
    list of float
        18 values laid out exactly as :func:`pymol.cmd.get_view` returns them.
    """
    r = np.asarray(rotation, dtype=float).reshape(3, 3)
    t = np.asarray(target, dtype=float).reshape(3)
    # Transposed on the way out: PyMOL keeps the camera basis in the columns.
    flat = r.T.reshape(-1)
    return [
        *(float(v) for v in flat),
        0.0, 0.0, -float(distance),
        float(t[0]), float(t[1]), float(t[2]),
        float(near), float(far),
        abs(float(fov)) if orthoscopic else -abs(float(fov)),
    ]


def unpack_view_state(view: Sequence[float]) -> ViewState:
    """Decode an 18-float view tuple, accepting all layouts described above.

    Parameters
    ----------
    view : sequence of float
        18 values in PyMOL's layout, chimol's row-major matrix layout, or the
        legacy elevation/azimuth layout.

    Returns
    -------
    ViewState
        The decoded camera, always with a world-to-camera ``rotation``.

    Raises
    ------
    ValueError
        If ``view`` does not hold 18 values.
    """
    vals = [float(v) for v in view]
    if len(vals) != 18:
        raise ValueError("view must contain 18 floats")

    mat = np.array(vals[0:9], dtype=float).reshape(3, 3)
    slot9, slot10, slot11 = vals[9], vals[10], vals[11]
    target = np.array(vals[12:15], dtype=float)
    near, far = vals[15], vals[16]
    fov = abs(vals[17]) if abs(vals[17]) > 1e-9 else DEFAULT_FOV

    is_identity = np.allclose(mat, np.eye(3), atol=1e-6)

    # PyMOL: the camera sits at (0, 0, -distance) in camera space, so slot 11 is
    # a negative distance and slot 9 is zero. chimol's own older tuples put the
    # (positive) distance in slot 9 instead, which makes the two unambiguous.
    if abs(slot9) < 1e-9 and slot11 < 0.0:
        return ViewState(mat.T, abs(slot11), target, near, far, fov,
                         orthoscopic=vals[17] > 0.0)

    # The older chimol layouts predate the orthoscopic flag and always wrote a
    # positive field of view, so their sign carries no meaning.
    distance = max(slot9, 0.1)
    if is_identity and (abs(slot10) > 1e-9 or abs(slot11) > 1e-9):
        # Legacy: identity matrix with elevation/azimuth in slots 10-11.
        return ViewState(rotation_from_angles(slot10, slot11), distance,
                         target, near, far, fov)

    return ViewState(mat, distance, target, near, far, fov)
