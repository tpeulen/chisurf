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

from typing import Any, Callable

__all__ = ["HAS_QT", "Signal", "Timer", "WidgetBase", "is_widget"]

try:  # pragma: no cover - the branch taken depends on the host
    from qtpy import QtCore as _QtCore
    from qtpy import QtWidgets as _QtWidgets

    HAS_QT = True
except Exception:  # noqa: BLE001 - a browser, or a machine with no display stack
    _QtCore = None
    _QtWidgets = None
    HAS_QT = False


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
    """A timer that never fires.

    Playback and the settle-then-bake pass both want one. A browser drives its
    own frames from ``requestAnimationFrame``, so the host schedules there and
    this exists to keep the construction path from branching.
    """

    def __init__(self, parent: Any = None) -> None:
        self._parent = parent
        self._interval = 0
        self._single_shot = False
        self.timeout = _BoundSignal()

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

    def stop(self) -> None:
        """Stop the timer."""

    def isActive(self) -> bool:  # noqa: N802 - Qt naming
        """Whether the timer is running. It never is."""
        return False


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
