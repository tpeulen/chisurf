"""chimol's viewport as a Qt widget: the shared renderer, with Qt's events.

What this is
------------
:class:`WgpuRenderer` is the **Qt host** for the viewport. Everything it draws
and every decision it makes about what a gesture means is in
:class:`~.canvas_base.CanvasRenderer`, which knows nothing about a toolkit; what
is left here is the part that genuinely is Qt's:

* being a ``QWidget``, so the viewport can be embedded in a main window;
* translating ``QMouseEvent`` / ``QKeyEvent`` / ``QWheelEvent`` into the
  engine's own ``on_pointer_press`` and friends;
* rasterising the three image-shaped overlays -- 3-D labels, a traced frame and
  the rubber-band box -- with a ``QPainter``, which is the one thing in the
  frame that is not built as quads.

Qt is now **one host among several**. The default desktop window
(:mod:`chimol.host.run`) drives the same renderer through a ``rendercanvas``
surface with no toolkit at all, and a browser page drives it through a canvas;
all three run *the same* ``_draw``, so a picture verified in one is the picture
the others show. Two paths that merely "do the same thing" would drift, and this
port has already found three constants that did.

What it does not do yet
-----------------------
The object panel's pop-up menus and the wizard beyond hover/click/drag routing.
Everything else is here: the molecule, the object panel, the sequence strip,
3-D labels, the depth-outline silhouette, and atom picking. The chrome and the
labels are composited as a textured quad at the end of the render pass rather
than painted over the surface -- see :mod:`..host.qt_overlay` for why the two obvious
Qt arrangements do not work.
"""
from __future__ import annotations

import numpy as np
from qtpy import QtCore, QtWidgets

from .canvas_base import (
    DEFAULT_BACKEND,
    WHEEL_STEP,
    CanvasRenderer,
    Label,
    collect_labels,
    selected_backend,
)

__all__ = [
    "DEFAULT_BACKEND",
    "WHEEL_STEP",
    "Label",
    "WgpuRenderer",
    "default_renderer",
    "is_available",
    "selected_backend",
]

#: Kept importable from here: this module was the only renderer for a long time
#: and both names are used from tests and from the command layer.
_collect_labels = collect_labels


def is_available() -> bool:
    """Whether this machine can create a WebGPU adapter *and* a Qt surface.

    Checked rather than assumed: a viewer that opens to a blank widget is worse
    than one that says it cannot draw.

    Returns
    -------
    bool
    """
    from .gpu import api as wgpu
    from .gpu import native

    if not native.is_available():
        return False
    try:
        import rendercanvas.qt  # noqa: F401
    except Exception:
        return False
    try:
        return wgpu.gpu.request_adapter_sync(power_preference="high-performance") is not None
    except Exception:
        return False


def default_renderer():
    """The renderer class the viewer builds when it is given none.

    :class:`WgpuRenderer` when this machine can create a WebGPU adapter, and
    :class:`~.headless.SceneSink` when it cannot -- a scene-only backend, which
    is honest about having no window rather than opening an empty one. There is
    no OpenGL renderer to fall back to any more; the WGSL one replaced it.

    The refusal is logged rather than silent: "chimol shows nothing today" is a
    much harder question to answer than "chimol said it had no adapter".

    Returns
    -------
    type
    """
    import logging

    if not is_available():
        logging.getLogger(__name__).warning(
            "no WebGPU adapter is available; chimol will build scenes but draw "
            "nothing. Check that `wgpu` and `rendercanvas` are installed and "
            "that this machine has a supported GPU."
        )
        from .headless import SceneSink

        return SceneSink
    return WgpuRenderer


def _make_widget_base():
    """Return ``rendercanvas``'s Qt widget class, importing Qt first.

    ``rendercanvas.qt`` raises on import unless a Qt binding is already
    imported, and the message reads like a missing dependency rather than an
    ordering rule. ``qtpy`` above has done it, so this only has to happen after.

    Returns
    -------
    type
    """
    from rendercanvas.qt import QRenderWidget

    return QRenderWidget


def _qrect(rect) -> QtCore.QRect:
    """Convert one of the engine's rectangles into a ``QRect``.

    Parameters
    ----------
    rect : chimol.host.events.Rect or QtCore.QRect or None
        The engine states the selection box and the scene column in its own
        toolkit-free rectangle; a ``QPainter`` needs Qt's.

    Returns
    -------
    QtCore.QRect or None
    """
    if rect is None or isinstance(rect, QtCore.QRect):
        return rect
    return QtCore.QRect(
        int(round(rect.x())),
        int(round(rect.y())),
        int(round(rect.width())),
        int(round(rect.height())),
    )


class WgpuRenderer(_make_widget_base(), CanvasRenderer):
    """Draw a chimol scene into a Qt widget with WebGPU.

    Parameters
    ----------
    controller : object, optional
        The :class:`~.view.MolView` driving this renderer.
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, controller: object = None, parent: object = None) -> None:
        # Same ceiling as the toolkit-free window, and for the same reason:
        # rendercanvas defaults to **30** fps on demand, which is a ceiling a
        # viewer being dragged around should not have. `QRenderWidget` takes
        # the same keywords as every other rendercanvas backend.
        #
        # It is a ceiling and not a slot: the scheduler sleeps `1/max_fps`
        # *minus the time the frame already took*, so a frame that overshoots
        # simply ticks as soon as it is done -- it is not deferred to the next
        # multiple. (An earlier comment here said it halved. It does not, in
        # this version; the tick period is `max(1/max_fps, draw_time)`.) So a
        # viewport sitting at exactly 30 with this set to 60 is **not** being
        # quantised by the scheduler: switch on nerd mode and read the `wait`
        # figure, which separates "our frame costs 33 ms" from "we are blocked
        # on presentation".
        from .canvas_view import _max_fps  # noqa: PLC0415

        super().__init__(parent=parent, max_fps=_max_fps(), update_mode="ondemand")

        # Nothing is connected to ``destroyed`` here on purpose -- see
        # :meth:`_cpp_alive` for the history and the reason.
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.init_viewport(controller)

    # -- surviving the C++ half's death ---------------------------------------
    #
    # Qt destroys an embedded widget without a ``closeEvent``, so rendercanvas
    # keeps it registered as open; its loop then probes the dead wrapper and
    # PyQt raises ``RuntimeError`` where the loop expects ``AttributeError``,
    # killing shutdown.
    #
    # This was fixed twice by *pushing* the state out from a ``destroyed`` slot
    # -- first with a keyword-only default holding ``self.__dict__``, then with
    # a closure over it. Both are recorded here because both looked right and
    # both were wrong, in ways that only showed up under a full test run:
    #
    # * the default form lost its ``__kwdefaults__`` at interpreter shutdown
    #   and raised ``TypeError`` from inside the signal, which becomes SIGABRT
    #   -- a whole run exiting 134 *after* every test passed;
    # * the closure form survived that, and then segfaulted. The ``destroyed``
    #   signal fires from the C++ destructor, and when the last reference to a
    #   widget is dropped by the *garbage collector* that destructor runs
    #   inside the collection. The slot then mutates a dict mid-collection.
    #   ``Garbage-collecting`` sits directly above ``_mark_closed`` in the
    #   fault report, under an unrelated test that merely allocated enough to
    #   trigger a gen-2 pass.
    #
    # So nothing is pushed. The question is *answered when asked*, at a point
    # of rendercanvas's choosing, on its own stack -- which is the difference
    # that matters: there is no longer any chimol code that can run during a
    # collection.

    def _cpp_alive(self) -> bool:
        """Whether the C++ ``QWidget`` behind this wrapper still exists.

        Returns
        -------
        bool
            False once Qt has destroyed the widget, when every method call on
            it raises. Asked by touching the cheapest C++ accessor there is;
            ``sip.isdeleted`` would be more direct but is PyQt-only, and the
            renderer is built through :func:`_make_widget_base` precisely so it
            does not care which binding is present.
        """
        try:
            self.objectName()
        except RuntimeError:
            return False
        return True

    def _rc_get_closed(self):
        """Report a destroyed widget as closed.

        rendercanvas asks this to decide what is still alive. A widget whose
        C++ half is gone is closed by any useful definition, and saying so here
        is what keeps the loop from calling into it.
        """
        if not self._cpp_alive():
            return True
        return super()._rc_get_closed()

    def _rc_close(self):
        """Close, unless there is nothing left to close.

        The loop closes whatever :meth:`_rc_get_closed` reports as closed, so
        this is reached with a dead widget in the ordinary course of shutdown,
        and ``QWidget.close`` on a dead wrapper is the ``RuntimeError`` this
        whole section exists to prevent.
        """
        if not self._cpp_alive():
            return
        super()._rc_close()

    # -- what a Qt widget answers differently --------------------------------

    def widget(self):
        """This renderer *is* the widget."""
        return self

    def update(self) -> None:  # type: ignore[override]
        """Ask for a repaint.

        Overrides ``QWidget.update`` deliberately, and explicitly rather than by
        inheritance: ``QWidget`` sits before :class:`CanvasRenderer` in the MRO,
        so without this the widget's own repaint would win and the canvas would
        never be asked to draw.
        """
        CanvasRenderer.update(self)

    def _ratio(self) -> float:
        """Device pixels per logical pixel, from the widget's screen."""
        try:
            return float(self.devicePixelRatioF())
        except Exception:
            return 1.0

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Track the framebuffer size the projection is built from."""
        super().resizeEvent(event)
        width, height = self._physical_size()
        self.resize_viewport(width, height)

    # -- the overlays that need a painter ------------------------------------

    def ray_image_rect(self) -> QtCore.QRect:
        """Where a traced frame is shown: the scene column, under the strip.

        Returns
        -------
        QtCore.QRect
            Qt's rectangle rather than the engine's, because this one is handed
            straight to a ``QPainter`` and read by the Qt-side tests.
        """
        return QtCore.QRect(*self.scene_rect())

    def _composite_overlay(self) -> np.ndarray | None:
        """Rasterise the labels, the traced frame and the selection box.

        Returns
        -------
        numpy.ndarray or None
            ``(h, w, 4)`` premultiplied RGBA.
        """
        from ..host.qt_overlay import paint_chrome

        return paint_chrome(
            # The panel is drawn as quads now; what is left here is the traced
            # frame, the labels and the selection box.
            None,
            self._controller,
            self._width,
            self._height,
            self._ratio(),
            labels=self._labels,
            project=self.project_to_screen,
            label_size=self._label_size(),
            # First, so everything else is chrome drawn *over* the traced frame
            # exactly as it is drawn over the live scene.
            ray_image=self._ray_image,
            ray_rect=self.ray_image_rect(),
            select_rect=_qrect(self._select_rect),
        )

    def paint_screen_space(self, painter) -> None:
        """Draw everything that lives in screen space into ``painter``.

        The traced frame, the labels, the panel, the sequence strip and the
        selection box, in that order -- the same order and the same code the
        composited chrome uses, because a screenshot helper that paints them a
        second way is a second thing to keep at parity.

        Parameters
        ----------
        painter : QtGui.QPainter
            An open painter, in the widget's logical pixels.
        """
        from ..host.qt_overlay import paint_chrome_into

        paint_chrome_into(
            painter,
            self._internal_gui,
            self._controller,
            int(self.width()),
            int(self.height()),
            labels=self._labels,
            project=self.project_to_screen,
            ray_image=self._ray_image,
            ray_rect=self.ray_image_rect(),
            select_rect=_qrect(self._select_rect),
        )

    def set_background_image(self, source) -> None:
        """Set a backdrop behind the molecule.

        Transparency is invisible against one flat colour: a surface at alpha
        0.4 over black is merely a darker surface, because there is nothing
        behind it for the eye to catch. Give the background structure and the
        same surface reads as glass immediately.

        Parameters
        ----------
        source : str, QImage, numpy.ndarray or None
            A name from :data:`~.backdrop.BACKDROPS`, a path, an image already
            in hand, or ``None`` / ``"off"`` to clear it.

        Raises
        ------
        ValueError
            If a path was given and cannot be read -- a background that silently
            does not appear is indistinguishable from one that is not supported.
        """
        from qtpy import QtGui

        if source is None or (
            isinstance(source, str) and source.strip().lower() in ("", "off", "none")
        ):
            self._background_source = source
            self._background_image = None
            self.update()
            return

        image = None
        if isinstance(source, QtGui.QImage):
            image = source
        elif isinstance(source, np.ndarray):
            from ..host.qt_overlay import image_from_rgb

            image = image_from_rgb(source)
        elif isinstance(source, str):
            from .backdrop import BACKDROPS

            if source.strip().lower() not in BACKDROPS:
                loaded = QtGui.QImage(source)
                if loaded.isNull():
                    raise ValueError(f"cannot read background image: {source}")
                image = loaded
            # A named backdrop is generated at paint time, at the widget's size.

        # Recorded only once the source has resolved: setting it up front leaves
        # a refused path as the reported background, so `bg_image` names a
        # picture that never loaded and is not on screen.
        self._background_source = source
        self._background_image = image
        self.update()

    # -- Qt's events, translated ---------------------------------------------

    @staticmethod
    def _where(event) -> tuple[float, float]:
        """The event's position in widget pixels, as plain floats."""
        pos = event.pos()
        return float(pos.x()), float(pos.y())

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Hand a press to the engine, and accept it if it was wanted."""
        x, y = self._where(event)
        consumed = self.on_pointer_press(
            x,
            y,
            int(event.button()),
            int(event.modifiers()),
            double=event.type() == QtCore.QEvent.MouseButtonDblClick,
        )
        if consumed:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """A double click is a press that says so; the panel opens menus on it."""
        self.mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Hand a move to the engine."""
        x, y = self._where(event)
        if self.on_pointer_move(x, y, int(event.buttons()), int(event.modifiers())):
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Hand a release to the engine."""
        x, y = self._where(event)
        if self.on_pointer_release(x, y, int(event.button()), int(event.modifiers())):
            event.accept()

    def event(self, event) -> bool:  # noqa: N802 - Qt naming
        """Claim Tab before Qt's focus navigation eats it.

        Qt resolves Tab in `QWidget.event` and moves the focus, so a key
        handler never sees it -- which is why the prompt's completion existed
        and could not be reached. Claimed only while something is being typed;
        otherwise Tab still moves the focus, which is what it is for.
        """
        if event.type() in (
            QtCore.QEvent.KeyPress, QtCore.QEvent.ShortcutOverride
        ) and event.key() in (QtCore.Qt.Key_Tab, QtCore.Qt.Key_Backtab):
            gui = self._internal_gui
            typing = gui is not None and (
                gui.command_line.focused or gui.focused_field is not None
            )
            if typing:
                if event.type() == QtCore.QEvent.KeyPress:
                    self.keyPressEvent(event)
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Hand a key to the engine, then fall back to Qt's own handling."""
        if self.on_key_press(int(event.key()), event.text(), int(event.modifiers())):
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Turn Qt's angle delta into notches and hand them to the engine.

        Whichever axis carries the delta: **macOS turns shift+scroll into a
        horizontal scroll** before the application sees it, so a shifted wheel
        arrives with ``angleDelta().y() == 0`` and everything in ``x()``.
        Reading only ``y`` is why shift+wheel did nothing on a Mac while a
        synthetic event in a test -- which sets ``y`` -- worked perfectly.
        """
        angle = event.angleDelta()
        raw = angle.y() if angle.y() else angle.x()
        if not raw:
            return
        steps = int(raw / 120.0)
        if steps == 0:
            # A trackpad sends many small deltas rather than 120-unit notches;
            # truncating them to zero makes the gesture do nothing at all.
            steps = 1 if raw > 0 else -1

        pos = event.position() if hasattr(event, "position") else event.posF()
        if self.on_wheel(
            float(pos.x()), float(pos.y()), steps, int(event.modifiers())
        ):
            event.accept()
