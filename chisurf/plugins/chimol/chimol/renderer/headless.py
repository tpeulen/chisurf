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

Everything but that rasterise-nothing decision lives in
:class:`~.camera_state.CameraState`, which the WebGPU widget shares -- so a scene
built here and a scene built there are framed identically and can be compared
array by array.
"""
from __future__ import annotations

from .base import Renderer
from .camera_state import DEFAULT_VIEWPORT, CameraState

__all__ = ["DEFAULT_VIEWPORT", "SceneSink"]


class SceneSink(CameraState, Renderer):
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
        self.init_camera_state(size)

    def widget(self):
        """Return ``None``: this backend has no window.

        The viewer guards its Qt chrome on the renderer *being* a widget rather
        than on there being one, so ``None`` is the honest answer and not an
        error.
        """
        return None

    def update(self) -> None:
        """Record that a repaint was requested."""
        self.update_count += 1
