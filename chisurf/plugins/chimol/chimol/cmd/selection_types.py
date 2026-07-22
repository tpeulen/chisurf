"""Argument-annotation marker types for the command language.

These are used purely as *type annotations* on ``@command`` functions so the
argument binder (:mod:`argparse2`) knows how to treat a parameter. They carry no
runtime behaviour of their own.
"""

from __future__ import annotations


class Selection(str):
    """Marks a parameter as a PyMOL-style selection expression.

    The binder does not coerce ``Selection`` parameters — the raw selection
    string is passed through unchanged (as PyMOL does), and the command resolves
    it against the viewer via the shared selection resolver. Subclassing ``str``
    means a plain default like ``"all"`` is a valid value and annotations read
    naturally (``sel: Selection = "all"``).
    """


__all__ = ["Selection"]
