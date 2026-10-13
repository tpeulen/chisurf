"""ChiMol plugin entry point.

chimol's own run modes, none of which needs a GUI toolkit::

    python -m chisurf.plugins.chimol             # the desktop window
    python -m chisurf.plugins.chimol cli ...     # headless ptpython REPL

The default opens chimol's own window on a ``rendercanvas`` surface, driving
the same viewer and command layer ChiSurf's emtk surface does. The Qt window
(``--qt``) was retired with chimol's ``hosts/qt/``.
"""

from __future__ import annotations

import sys

if __name__ == "__main__":
    from chimol.__main__ import _dispatch

    raise SystemExit(_dispatch(sys.argv[1:]))
