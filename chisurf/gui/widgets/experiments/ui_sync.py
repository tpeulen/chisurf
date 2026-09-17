from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any


class SignalBlocker:
    """Context manager to temporarily block signals on a Qt widget.

    Usage:
        with SignalBlocker(widget):
            widget.setValue(123)
    """

    def __init__(self, widget: Any):
        self.widget = widget
        self._was_enabled = None

    def __enter__(self):
        self._was_enabled = self.widget.signalsBlocked()
        self.widget.blockSignals(True)
        return self.widget

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.widget.blockSignals(self._was_enabled)
        return False


def block_signals(*widgets: Any) -> SignalBlocker:
    """Create a SignalBlocker for multiple widgets."""
    if len(widgets) == 1:
        return SignalBlocker(widgets[0])
    else:
        return _MultiSignalBlocker(widgets)


class _MultiSignalBlocker:
    """Context manager to temporarily block signals on multiple Qt widgets."""

    def __init__(self, widgets: tuple):
        self.widgets = widgets
        self._was_enabled = [w.signalsBlocked() for w in widgets]

    def __enter__(self):
        for w in self.widgets:
            w.blockSignals(True)
        return self.widgets

    def __exit__(self, exc_type, exc_val, exc_tb):
        for w, was_enabled in zip(self.widgets, self._was_enabled):
            w.blockSignals(was_enabled)
        return False


class ReentrancyGuard:
    """Decorator/context manager that suppresses reentrant execution.

    The use it exists for is a two-way UI sync: writing a value into a widget
    emits the signal that writes it back into the model, which updates the
    widget again. The guard breaks that loop by skipping the inner call.

    Usage as decorator -- a reentrant call returns ``None`` without running the
    body. The flag lives on the instance, so two objects never block each
    other::

        @ReentrancyGuard()
        def update_ui(self):
            ...

    Usage as context manager -- ``__enter__`` reports whether it acquired, so
    the caller decides what to skip::

        guard = ReentrancyGuard()
        with guard as acquired:
            if acquired:
                ...

    Skipping, not raising, is deliberate: these run inside Qt slots, where an
    exception escapes into the event loop rather than to a caller who could
    handle it.
    """

    def __init__(self, key: str | None = None):
        self.key = key or "default"
        self._lock_attr = f"_reentrancy_guard_{self.key}"
        #: acquisitions of *this* guard object, for context-manager use. A list
        #: rather than a flag so a nested ``with`` releases at the right depth.
        self._acquired: list[bool] = []

    def __call__(self, func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            obj = args[0] if args else None
            if obj is None:
                return func(*args, **kwargs)
            if getattr(obj, self._lock_attr, False):
                return None  # already running: this is the loop
            setattr(obj, self._lock_attr, True)
            try:
                return func(*args, **kwargs)
            finally:
                # Always release, or one raised exception wedges the method
                # shut for the rest of the object's life.
                setattr(obj, self._lock_attr, False)

        return wrapper

    def __enter__(self) -> bool:
        acquired = not any(self._acquired)
        self._acquired.append(acquired)
        return acquired

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._acquired:
            self._acquired.pop()
        return False


def connected_signals_blocked(widget: Any, signal_name: str) -> bool:
    """Check if a signal is connected and blocked."""
    try:
        signal = getattr(widget, signal_name, None)
        if signal is None:
            return False
        return widget.signalsBlocked()
    except AttributeError:
        return False


class UiSyncMixin:
    """Mixin class to provide common UI synchronization patterns.

    Subclasses should implement:
        - updateUI(): reads from reader, updates widgets
        - onParametersChanged(): reads from widgets, updates reader

    The mixin provides:
        - _sync_ui_from_reader(): calls updateUI with signal blocking
        - _sync_reader_from_ui(): calls onParametersChanged with guard
    """

    _ui_sync_in_progress: bool = False

    def _sync_ui_from_reader(self, *widget_names: str) -> None:
        """Call updateUI with signals blocked for specified widgets.

        Args:
            *widget_names: Names of widget attributes to block signals on.
                          If empty, blocks signals on self.
        """
        if getattr(self, "_ui_sync_in_progress", False):
            return

        self._ui_sync_in_progress = True
        try:
            widgets_to_block = []
            if widget_names:
                for name in widget_names:
                    w = getattr(self, name, None)
                    if w is not None:
                        widgets_to_block.append(w)
            else:
                widgets_to_block = [self]

            with block_signals(*widgets_to_block):
                self.updateUI()
        finally:
            self._ui_sync_in_progress = False

    def _sync_reader_from_ui(self) -> None:
        """Call onParametersChanged with reentrancy guard."""
        if getattr(self, "_sync_in_progress", False):
            return

        self._sync_in_progress = True
        try:
            self.onParametersChanged()
        finally:
            self._sync_in_progress = False


__all__ = [
    "SignalBlocker",
    "block_signals",
    "ReentrancyGuard",
    "UiSyncMixin",
]
