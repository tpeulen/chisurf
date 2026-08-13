"""The demos chimol ships, and the material they run on.

The ``.pml`` scripts beside this file are the demos themselves; :mod:`.catalog`
says which ones ship and where each finds its structure, and :mod:`.data`
generates the material for the ones that cannot open a file that already
exists.

Both used to live in ``app/`` -- the ChiSurf/Qt integration layer -- purely
because the Qt script editor that *presents* the demos lives there. That put
engine code behind a window system: the command language's ``demo`` loader, the
toolkit-free host and the debug window all had to reach into ``app/`` to find
out which demos exist. They are here now, next to the scripts they describe,
and nothing about a demo needs a toolkit.
"""
from __future__ import annotations

__all__: list[str] = []
