"""The in-viewport chrome's drawing layer.

:mod:`.painter` is the interface the chrome draws against; :mod:`.qt_painter`
is the reference implementation and the before-half of the port. Neither is
imported eagerly -- ``qt_painter`` needs a GUI toolkit, and the point of this
package is that the chrome does not.
"""
from __future__ import annotations

from .painter import (
    ALIGN_CENTER,
    ALIGN_HCENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    ALIGN_VCENTER,
    Colour,
    Painter,
)

__all__ = [
    "ALIGN_CENTER",
    "ALIGN_HCENTER",
    "ALIGN_LEFT",
    "ALIGN_RIGHT",
    "ALIGN_VCENTER",
    "Colour",
    "Painter",
]
