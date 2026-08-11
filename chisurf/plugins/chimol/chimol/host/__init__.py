"""What chimol needs from whatever is hosting it.

The engine -- the renderer, the shaders, the scene builders, the panel's layout
and hit-testing -- knows nothing about windows. What is left is a small set of
things only a host can provide: an event vocabulary, a surface, a file chooser,
a clock.

:mod:`.events` is the vocabulary, and it is deliberately not a translation
layer: the values *are* the engine's, so a Qt host passes its events through
unchanged and a browser host converts into them.

Nothing is imported eagerly, so importing this package costs no toolkit.
"""
from __future__ import annotations

from . import events

__all__ = ["events"]
