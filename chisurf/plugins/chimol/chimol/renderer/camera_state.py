"""Camera, viewport and scene bookkeeping, shared by every non-GL backend.

Why this is its own module
--------------------------
A renderer is two things: something that holds a camera and a scene, and
something that turns them into pixels. Only the second half is backend-specific,
and this port has now paid three times for treating a shared quantity as
something each backend re-derives -- the depth-cue planes, the light rig, and the
shading model itself. The camera is the one that would hurt most: two backends
that frame a scene differently cannot be compared at all, and the comparison is
the only way this port is being verified.

So :class:`CameraState` holds it once. :class:`~.headless.SceneSink` is this and
nothing else; the WebGPU widget is this plus a surface to draw on. Both therefore
answer ``get_view_state()`` with the same eighteen floats for the same commands,
which is what makes a headless replay reproduce a windowed frame.

The camera is PyMOL's 18-float view tuple throughout (:mod:`.view_state`).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .scene import Scene
from .view_state import pack_view_state, unpack_view_state


def trackball_delta(
    last: tuple[float, float],
    cur: tuple[float, float],
    width: float,
    height: float,
    *,
    mouse_scale: float = 1.3,
) -> np.ndarray:
    """PyMOL's virtual-trackball delta rotation, as a camera-space 3x3.

    Projects the previous and current cursor onto a sphere of radius
    ``0.45 * min(W, H)``, takes the rotation carrying one to the other, and damps
    the roll component -- see ``SceneMouse.cpp``. The result **left-multiplies**
    the current world-to-camera rotation.

    Shared rather than reimplemented per backend: two viewers whose drags turn
    the molecule by different amounts are two different programs, and the
    difference is the kind a screenshot comparison never catches because every
    frame is individually correct.

    Parameters
    ----------
    last, cur : tuple of float
        Cursor positions in widget pixels, Qt's top-left origin.
    width, height : float
        Viewport size in the same pixels.
    mouse_scale : float, optional
        PyMOL's ``mouse_scale``.

    Returns
    -------
    numpy.ndarray
        A ``(3, 3)`` rotation.
    """
    scale = 0.45 * min(float(width), float(height))
    if scale <= 0.0:
        return np.eye(3)
    cx, cy = width / 2.0, height / 2.0

    def _sphere(px: float, py: float) -> np.ndarray:
        # Screen vector from centre; y is flipped (Qt top-left origin).
        vx = px - cx
        vy = cy - py
        r2 = vx * vx + vy * vy
        vz = math.sqrt(scale * scale - r2) if r2 < scale * scale else 0.0
        v = np.array([vx, vy, vz], dtype=float)
        n = np.linalg.norm(v)
        return v / n if n > 1e-9 else np.array([0.0, 0.0, 1.0])

    n1 = _sphere(*last)
    n2 = _sphere(*cur)
    axis = np.cross(n1, n2)
    s = float(np.linalg.norm(axis))
    if s <= 1e-9:
        return np.eye(3)
    axis /= s
    angle = float(mouse_scale) * 2.0 * math.asin(min(s, 1.0))
    angle /= 1.0 + abs(axis[2])  # damp the twist component
    # PyMOL applies rotate(angle, ax, ay, -az); the screen axis lives in camera
    # space, so this delta left-multiplies the view rotation.
    ax, ay, az = axis[0], axis[1], -axis[2]
    c, sn = math.cos(angle), math.sin(angle)
    k = np.array([[0.0, -az, ay], [az, 0.0, -ax], [-ay, ax, 0.0]])
    return np.eye(3) + sn * k + (1.0 - c) * (k @ k)

#: Viewport reported when nothing has been requested. Chosen well above the
#: 16-pixel floor that a real widget can clamp to when it has never been laid
#: out, because framing maths divides by it and a degenerate viewport silently
#: produces a scene nothing can be judged from.
DEFAULT_VIEWPORT: tuple[int, int] = (1280, 860)


class CameraState:
    """The state a renderer holds, with no opinion about how it is drawn.

    Attributes
    ----------
    scene : Scene or None
        The most recent scene handed to :meth:`set_scene`.
    """

    def init_camera_state(self, size: tuple[int, int] = DEFAULT_VIEWPORT) -> None:
        """Initialise the camera and viewport.

        A method rather than ``__init__`` because the Qt subclass must run
        ``QWidget.__init__`` first and multiple inheritance through a Qt base is
        the kind of thing that fails at C++ level with no Python traceback.
        """
        self._width, self._height = int(size[0]), int(size[1])
        self.scene: Optional[Scene] = None
        self.internal_gui = None
        self._fov = 20.0
        self._background = (0.0, 0.0, 0.0, 1.0)
        self._grid_visible = False
        self._grid = (0.0, 0.0)
        self._origin = np.zeros(3, dtype=float)
        self._target = np.zeros(3, dtype=float)
        self._distance = 100.0
        self._target_radius = 10.0
        self._rotation = np.eye(3, dtype=float)
        self._near = 10.0
        self._far = 1000.0
        self._orthoscopic = False
        # Three floats, not two: the view tuple carries an x/y/z shift.
        self._shift = np.zeros(3, dtype=float)
        self.lighting_state: dict = {}
        self._mouse_mode = "viewing"
        self.update_count = 0

    # -- what the viewer hands us -------------------------------------------

    def set_scene(self, scene: Optional[Scene]) -> None:
        """Store ``scene``."""
        self.scene = scene

    def clear(self) -> None:
        """Drop the stored scene."""
        self.scene = None

    def set_background_color(self, color) -> None:
        """Store the background colour."""
        self._background = color

    def configure_grid(self, size: float, spacing: float) -> None:
        """Store the ground-grid dimensions."""
        self._grid = (float(size), float(spacing))

    def set_grid_visible(self, visible: bool) -> None:
        """Store ground-grid visibility."""
        self._grid_visible = bool(visible)

    def set_lighting(self, **values) -> None:
        """Merge lighting parameters into :attr:`lighting_state`."""
        self.lighting_state.update(values)

    def set_mouse_mode(self, mode: str) -> None:
        """Store the mouse mode."""
        self._mouse_mode = mode

    def configure_camera(self, **kwargs) -> None:
        """Accept clip configuration; there are no clip controls to drive."""
        return None

    # -- viewport ------------------------------------------------------------

    def width(self) -> int:
        """Viewport width in pixels."""
        return self._width

    def height(self) -> int:
        """Viewport height in pixels."""
        return self._height

    def scene_width(self) -> int:
        """Width of the 3-D column. No panel is reserved, so the full width."""
        return self._width

    def scene_height(self) -> int:
        """Height of the 3-D column. No strip is reserved, so the full height."""
        return self._height

    def resize(self, width: int, height: int) -> None:
        """Set the reported viewport."""
        self._width, self._height = int(width), int(height)

    def _aspect(self) -> float:
        """Aspect ratio of the 3-D column."""
        h = max(1, self.scene_height())
        return float(self.scene_width()) / float(h)

    # -- camera --------------------------------------------------------------

    def fit_to_radius(self, radius: float) -> None:
        """Pull the camera back far enough to frame ``radius``."""
        r = max(float(radius), 1e-6)
        self._target_radius = r
        half = np.radians(max(self._fov, 1e-3)) * 0.5
        self._distance = r / max(np.tan(half), 1e-6)
        self._near = max(self._distance - r, 1e-3)
        self._far = self._distance + r

    def reset_view(self, distance: float, elevation: float, azimuth: float) -> None:
        """Place the camera on a spherical coordinate."""
        self._distance = float(distance)
        el, az = np.radians(float(elevation)), np.radians(float(azimuth))
        ce, se, ca, sa = np.cos(el), np.sin(el), np.cos(az), np.sin(az)
        self._rotation = np.array(
            [[ca, 0.0, -sa], [-se * sa, ce, -se * ca], [ce * sa, se, ce * ca]],
            dtype=float,
        )

    def look_at(self, target: np.ndarray) -> None:
        """Aim the camera at ``target``."""
        self._target = np.asarray(target, dtype=float).reshape(3).copy()

    def set_origin(self, origin: np.ndarray) -> None:
        """Set the rotation origin."""
        self._origin = np.asarray(origin, dtype=float).reshape(3).copy()

    def get_origin(self) -> np.ndarray:
        """Return the rotation origin."""
        return self._origin.copy()

    def get_view_state(self) -> list[float]:
        """Return the camera as an 18-float tuple in PyMOL's ``get_view`` layout."""
        return pack_view_state(
            self._rotation,
            self._distance,
            self._target,
            self._near,
            self._far,
            self._fov,
            self._orthoscopic,
            shift=self._shift,
        )

    def set_view_state(self, view) -> None:
        """Restore an 18-float view tuple; see :mod:`.view_state` for layouts."""
        state = unpack_view_state(view)
        self._rotation = np.asarray(state.rotation, dtype=float).reshape(3, 3).copy()
        self._distance = max(float(state.distance), 0.1)
        self._target = np.asarray(state.target, dtype=float).reshape(3).copy()
        self._shift = np.asarray(state.shift, dtype=float).copy()
        self._near = float(state.near)
        # Stored as given. The Qt/GL backend widens the far plane to protect its
        # depth buffer's precision; doing the same here would make
        # `set_view_state(get_view_state())` return a different camera than it
        # was handed -- and a view tuple that does not survive a round trip
        # cannot be used to reproduce a frame, which is the one job it has.
        self._far = float(state.far)
        self._fov = float(state.fov)
        self._orthoscopic = bool(state.orthoscopic)

    def lighting_parameters(self) -> dict:
        """The lighting overrides the viewer has set, under ChimeraX's names."""
        return dict(self.lighting_state)

    # -- gestures ------------------------------------------------------------

    def camera_axes(self) -> tuple[np.ndarray, np.ndarray]:
        """The camera's right and up axes in world space.

        The world-to-camera rotation keeps them in its *rows*, so they are read
        out rather than computed.
        """
        r = np.asarray(self._rotation, dtype=float)
        return r[0].copy(), r[1].copy()

    def orbit(self, last: tuple[float, float], cur: tuple[float, float]) -> None:
        """Turn the camera by a cursor drag, through PyMOL's trackball."""
        delta = trackball_delta(last, cur, self.scene_width(), self.scene_height())
        self._rotation = delta @ self._rotation

    def pan(self, dx: float, dy: float) -> None:
        """Slide the scene by a cursor delta, one pixel of scene per pixel of mouse.

        PyMOL's ``SceneGetScreenVertexScale`` is ``depth * 2 tan(fov/2) /
        Height`` -- the **same** scale on both axes, which is what keeps the
        molecule under the cursor. Multiplying the horizontal scale by the aspect
        ratio counts the aspect twice, because a perspective frustum is already
        ``height * aspect`` wide; that bug made horizontal panning run 1.7x the
        cursor on a 1278x631 viewport.
        """
        height = max(self.scene_height(), 1)
        half_tan = math.tan(math.radians(float(self._fov)) / 2.0)
        if half_tan <= 0.0:
            return
        scale = 2.0 * self._distance * half_tan / height
        right, up = self.camera_axes()
        self._target = self._target + (-dx * scale) * right + (dy * scale) * up

    def dolly(self, factor: float) -> None:
        """Move the camera along its own axis by a multiplicative ``factor``.

        Multiplicative, not additive: one wheel step has to feel the same on a
        peptide and on a ribosome, and only a ratio does.
        """
        self._distance = float(np.clip(self._distance * float(factor), 1e-3, 1e9))
