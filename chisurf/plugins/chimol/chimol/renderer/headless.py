"""A renderer that builds the scene and draws nothing.

Why this exists
---------------
``MolView._update_view`` opens with ``if self._renderer is None: return``, so
without a renderer the viewer runs every command and never assembles a
:class:`~.scene.Scene`. That single line is why the Qt-free CLI
(``chimol cli``) can execute the whole PyMOL command language but cannot produce
geometry, and why ``testing/mock_viewer.py`` had to fake object bookkeeping
instead of driving the real thing.

``SceneSink`` is a renderer in every sense the viewer cares about -- it accepts a
scene, holds a camera, and reports a viewport -- except that it rasterises
nothing. With it, scene assembly becomes ordinary library code: importable,
callable without a display, and testable by comparing arrays instead of pixels.

It is also the forcing function for the backend interface. An abstraction that a
windowless renderer can satisfy is one a browser or a ray tracer can satisfy;
``Renderer.widget()`` returning a ``QWidget`` is exactly the assumption that a
second backend cannot meet, and here it returns ``None``.

The camera is the same 18-float PyMOL view tuple every other backend uses
(:mod:`.view_state`), so a scene built here and a scene built through the Qt
renderer are framed identically and can be compared array by array.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .base import Renderer
from .scene import Scene
from .view_state import pack_view_state, unpack_view_state

#: Viewport reported when nothing has been requested. Chosen well above the
#: 16-pixel floor that a real widget can clamp to when it has never been laid
#: out, because framing maths divides by it and a degenerate viewport silently
#: produces a scene nothing can be judged from.
DEFAULT_VIEWPORT: tuple[int, int] = (1280, 860)


class SceneSink(Renderer):
    """Hold the scene and the camera; rasterise nothing.

    Parameters
    ----------
    controller : object, optional
        The :class:`~.view.MolView` driving this renderer. Accepted for
        signature parity with the Qt backend; unused.
    parent : object, optional
        Accepted for signature parity with the Qt backend; unused.
    size : tuple of int, optional
        Viewport in pixels, as ``(width, height)``.

    Attributes
    ----------
    scene : Scene or None
        The most recent scene handed to :meth:`set_scene`.
    """

    def __init__(
        self,
        controller: object = None,
        parent: object = None,
        size: tuple[int, int] = DEFAULT_VIEWPORT,
    ) -> None:
        self._controller = controller
        self._parent = parent
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

    def widget(self):
        """Return ``None``: this backend has no window.

        The viewer guards its Qt chrome on the renderer *being* a widget rather
        than on there being one, so ``None`` is the honest answer and not an
        error.
        """
        return None

    def set_scene(self, scene: Optional[Scene]) -> None:
        """Store ``scene``. This is the whole point of the class."""
        self.scene = scene

    def clear(self) -> None:
        """Drop the stored scene."""
        self.scene = None

    def update(self) -> None:
        """Record that a repaint was requested."""
        self.update_count += 1

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
        """Store the mouse mode; there is no input to route."""
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
        # Stored as given. The Qt backend widens the far plane to protect its
        # depth buffer's precision; there is no depth buffer here, so doing the
        # same would only make `set_view_state(get_view_state())` return a
        # different camera than it was handed -- and a view tuple that does not
        # survive a round trip cannot be used to reproduce a frame, which is the
        # one job this camera has.
        self._far = float(state.far)
        self._fov = float(state.fov)
        self._orthoscopic = bool(state.orthoscopic)
