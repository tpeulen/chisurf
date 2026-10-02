"""The desktop surfaces of QuEst: the Qt dock tool and the native emtk window.

`quest/gui/` stays in QuEst: it is generated from QuEst's own parameter catalog and is what makes the package usable
standalone. The Qt tool embeds it; the native window (``app.py``) hosts the QuEst card of Structure Tools. Nothing here
imports Qt: ``QuEstTool`` is resolved on first use (PEP 562), so ``gui.app`` can be imported Qt-free.
"""

__all__ = ["QuEstTool"]


def __getattr__(name: str):
    """Load the Qt tool lazily: ``from ...gui import QuEstTool`` still works."""
    if name == "QuEstTool":
        from .tool import QuEstTool

        return QuEstTool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
