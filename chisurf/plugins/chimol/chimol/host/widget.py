"""The three things ``MolView`` needs from a toolkit, and stand-ins for them.

Why this exists
---------------
``MolView`` is the viewer: the object store, the scene builder, the camera, the
selection, and the hundred-odd commands' entire idea of what a viewer *is*
(``cmd/`` reaches sixty-seven of its methods). It is also, incidentally, a
``QWidget`` — and that incidental fact is what stopped a browser from having a
command layer at all, because a page that cannot import Qt cannot import the
viewer, and a viewer it cannot import is one it has to reimplement.

Reimplementing it was the wrong answer, and it was tried: a parallel command set
bound to a browser-only viewer. Two command layers means two spellings, two sets
of defaults and two places every future command has to be written. **One code
path** is the requirement, so the toolkit dependency moves here instead.

What a viewer actually needs from a widget is small — measured, not assumed:

* a **base class**, because ``MolView`` is one;
* **signals**, four of them, which the host connects to;
* a **timer**, for playback and for the settle-then-bake pass.

Everything else Qt-shaped in ``view.py`` builds *child widgets* — the info
overlay, the disabled-label — and is already guarded on the renderer being a
widget, because a windowless backend has been supported since ``SceneSink``.

The stand-ins are deliberately minimal. ``_Signal`` connects and emits and does
nothing else: no queued connections, no threads, no argument checking. A browser
frame is one thread, and a stand-in that pretended otherwise would be a second
implementation of Qt rather than the absence of one.
"""
from __future__ import annotations

import os
from typing import Any, Callable

__all__ = ["HAS_QT", "QT_AVAILABLE", "Signal", "Timer", "WidgetBase", "is_widget"]

try:  # pragma: no cover - the branch taken depends on the host
    from qtpy import QtCore as _QtCore
    from qtpy import QtWidgets as _QtWidgets

    QT_AVAILABLE = True
except Exception:  # noqa: BLE001 - a browser, or a machine with no display stack
    _QtCore = None
    _QtWidgets = None
    QT_AVAILABLE = False


#: Whether a toolkit is *importable*. Availability, not choice -- and keeping
#: the two apart is the whole point of this block.
#:
#: The two were the same thing once, and it was wrong in the one case that
#: matters. chimol ships as a plugin **inside** a PyQt application, so within
#: that process Qt always imports; deciding the base class from that alone made
#: ``MolView`` a ``QWidget`` even when the caller had deliberately chosen the
#: toolkit-free host. Running ``python -m chisurf.plugins.chimol.chimol`` then
#: died with *"QWidget: Must construct a QApplication before a QWidget"* --
#: a hard ``SIGABRT``, before a single frame, because a widget was built for a
#: toolkit nobody had started.
#:
#: So ``CHIMOL_TOOLKIT`` selects, and importability only constrains:
#:
#: ``auto`` (default)
#:     Use Qt when it imports. What an embedded plugin gets.
#: ``none``
#:     Never use Qt, even where it imports. What the Qt-free host sets before
#:     anything can reach :mod:`chimol.renderer.view`.
#: ``qt``
#:     Demand Qt; the same as ``auto`` except that it is a stated intention.
#:
#: It is an environment variable rather than a function because the choice has
#: to be made *before* ``view.py`` is imported: ``class MolView(WidgetBase)``
#: binds its base at class-definition time, so anything settable afterwards is
#: settable too late.
_TOOLKIT = os.environ.get("CHIMOL_TOOLKIT", "auto").strip().lower()

#: Whether Qt is actually to be used. This is what the rest of chimol reads.
HAS_QT = QT_AVAILABLE and _TOOLKIT != "none"


class _BoundSignal:
    """One instance's end of a :class:`_Signal`."""

    __slots__ = ("_slots",)

    def __init__(self) -> None:
        self._slots: list[Callable[..., Any]] = []

    def connect(self, slot: Callable[..., Any]) -> None:
        """Register *slot* to be called on emit."""
        self._slots.append(slot)

    def disconnect(self, slot: Callable[..., Any] | None = None) -> None:
        """Remove *slot*, or every slot when none is given."""
        if slot is None:
            self._slots.clear()
        elif slot in self._slots:
            self._slots.remove(slot)

    def emit(self, *args: Any) -> None:
        """Call every connected slot.

        A slot that raises is not allowed to stop the others: a signal has
        several independent listeners by construction, and one broken panel
        must not silence the rest.
        """
        for slot in list(self._slots):
            try:
                slot(*args)
            except Exception:  # noqa: BLE001 - one listener's failure
                pass


class _Signal:
    """A class-level signal, bound per instance on first access.

    Mirrors what ``QtCore.Signal`` does at the call sites that matter --
    ``obj.thing.connect(...)`` and ``obj.thing.emit(...)`` -- and nothing else.
    """

    def __init__(self, *types: Any) -> None:
        self._types = types
        self._name = f"_signal_{id(self):x}"

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = f"_signal_{name}"

    def __get__(self, instance: Any, owner: type | None = None):
        if instance is None:
            return self
        bound = instance.__dict__.get(self._name)
        if bound is None:
            bound = _BoundSignal()
            instance.__dict__[self._name] = bound
        return bound


class _Widget:
    """What is left of a widget when there is no window system.

    Every method here is called by ``MolView`` or by something it hands itself
    to. They answer rather than raise, because the alternative is a viewer that
    works until some path asks it whether it is visible.
    """

    def __init__(self, parent: Any = None) -> None:
        self._parent = parent
        self._layout = None
        #: ``QObject.destroyed``. The viewer connects its own teardown to it --
        #: it registers a display-config listener and has to unregister -- so a
        #: stand-in without it fails at construction rather than at teardown.
        self.destroyed = _BoundSignal()

    # -- the handful of QWidget methods the viewer calls on itself ---------
    def update(self) -> None:
        """Request a repaint. There is no window, so there is nothing to do."""

    def repaint(self) -> None:
        """As :meth:`update`."""

    def window(self):
        """Return the top-level window -- itself, there being nothing above."""
        return self

    def parent(self):
        """Return the parent passed at construction."""
        return self._parent

    def isVisible(self) -> bool:  # noqa: N802 - Qt naming
        """Whether the widget is on screen. It is not."""
        return False

    def setVisible(self, visible: bool) -> None:  # noqa: N802 - Qt naming
        """Show or hide. Nothing to show."""

    def show(self) -> None:
        """Show the widget."""

    def hide(self) -> None:
        """Hide the widget."""

    def close(self) -> bool:
        """Close the widget."""
        return True

    def width(self) -> int:
        """Widget width in pixels."""
        return 0

    def height(self) -> int:
        """Widget height in pixels."""
        return 0

    def layout(self):
        """Return the layout, of which there is none."""
        return self._layout

    def setLayout(self, layout) -> None:  # noqa: N802 - Qt naming
        """Set the layout."""
        self._layout = layout


class _Timer:
    """A timer for a host with no toolkit, driven by the canvas' own loop.

    Playback and the settle-then-bake pass both want a clock. This used to be a
    timer that *never fired* -- a construction stub so the code path did not
    branch -- which meant ``mplay`` on the toolkit-free host started a movie
    that never advanced a frame.

    ``rendercanvas`` already owns an event loop with ``call_later``, and it is
    the loop the window is being pumped by, so a callback scheduled on it runs
    on the same thread as the drawing. Where even that is missing (a bare
    import, a browser driving its own frames from ``requestAnimationFrame``)
    this degrades to the old do-nothing behaviour rather than raising.
    """

    def __init__(self, parent: Any = None) -> None:
        self._parent = parent
        self._interval = 0
        self._single_shot = False
        self._active = False
        self._generation = 0
        self.timeout = _BoundSignal()

    @staticmethod
    def _loop():
        """The canvas event loop, or ``None`` when there is not one."""
        try:
            from rendercanvas.asyncio import loop  # noqa: PLC0415

            return loop
        except Exception:  # noqa: BLE001 - no canvas loop here
            return None

    def _fire(self, generation: int) -> None:
        """Emit one tick, and reschedule unless single-shot or stopped.

        Parameters
        ----------
        generation : int
            Which ``start`` this callback belongs to. A stop or a restart bumps
            the counter, so a callback already queued on the loop is ignored
            rather than delivering a tick for a timer that was stopped -- the
            loop has no way to cancel one.
        """
        if not self._active or generation != self._generation:
            return
        if self._single_shot:
            self._active = False
        else:
            self._schedule(generation)
        self.timeout.emit()

    def _schedule(self, generation: int) -> None:
        """Queue the next tick on the canvas loop, if there is one."""
        loop = self._loop()
        if loop is None:
            return
        try:
            loop.call_later(max(self._interval, 0) / 1000.0, self._fire, generation)
        except Exception:  # noqa: BLE001 - a clock is not worth the frame
            pass

    def setSingleShot(self, single: bool) -> None:  # noqa: N802 - Qt naming
        """Fire once rather than repeatedly."""
        self._single_shot = bool(single)

    def setInterval(self, msec: int) -> None:  # noqa: N802 - Qt naming
        """Set the interval, in milliseconds."""
        self._interval = int(msec)

    def start(self, msec: int | None = None) -> None:
        """Start the timer."""
        if msec is not None:
            self._interval = int(msec)
        self._generation += 1
        self._active = True
        self._schedule(self._generation)

    def stop(self) -> None:
        """Stop the timer."""
        self._active = False
        self._generation += 1

    def isActive(self) -> bool:  # noqa: N802 - Qt naming
        """Whether the timer is running."""
        return bool(self._active)


#: The base class for the viewer, and the two helpers it needs.
WidgetBase: Any = _QtWidgets.QWidget if HAS_QT else _Widget
Signal: Any = _QtCore.Signal if HAS_QT else _Signal
Timer: Any = _QtCore.QTimer if HAS_QT else _Timer


def is_widget(obj: Any) -> bool:
    """Whether *obj* is a real toolkit widget that can be laid out.

    Parameters
    ----------
    obj : object

    Returns
    -------
    bool
        ``False`` everywhere Qt is absent, which is what makes the viewer take
        its windowless branch rather than trying to embed a renderer in a
        layout that does not exist.
    """
    return bool(HAS_QT and isinstance(obj, _QtWidgets.QWidget))
