"""The desktop surface, embedded from QuEst.

`quest/gui/` stays in QuEst: it is generated from QuEst's own parameter catalog
and is what makes the package usable standalone. The plugin embeds it.
"""

from .tool import QuEstTool

__all__ = ["QuEstTool"]
