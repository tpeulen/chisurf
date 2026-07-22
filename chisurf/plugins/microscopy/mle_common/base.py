"""Shared Qt-free view-model plumbing for the MLE imaging tools.

Both MLE view-models proxy their AutoForm scalar fields onto a settings
dataclass with an identical descriptor factory, and carry an identical
observer/notify hook. Those pieces live here so each view-model only declares
its own fields and logic.
"""

from __future__ import annotations

import logging
import typing

logger = logging.getLogger(__name__)


def scalar(name: str, cast: typing.Callable, doc: str) -> property:
    """Build a property proxying ``self.settings.<name>`` with a cast.

    Used in a view-model class body: ``tau = scalar("tau", float, "…")``.
    """

    def getter(self):
        return cast(getattr(self.settings, name))

    def setter(self, value):
        setattr(self.settings, name, cast(value))

    getter.__doc__ = doc
    return property(getter, setter)


class MleObserverMixin:
    """Observer hook shared by the MLE view-models.

    The view-model's ``__init__`` must create ``self._observers = []`` (kept in
    the subclass so the rest of its state initialises alongside it).
    """

    _observers: list

    def add_observer(self, cb: typing.Callable[[str], None]) -> None:
        """Register *cb*, called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("MLE view-model observer failed", exc_info=True)
