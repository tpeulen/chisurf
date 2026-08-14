"""ChiMol plugin entry point.

Three run modes, of which the **default needs no GUI toolkit**::

    python -m chisurf.plugins.chimol             # Qt-free desktop window
    python -m chisurf.plugins.chimol --qt        # the Qt plugin window
    python -m chisurf.plugins.chimol cli ...     # headless ptpython REPL

The default opens chimol's own window on a ``rendercanvas`` surface and drives
the same viewer and the same command layer the Qt window does; ``--qt`` is the
option, not the assumption.
"""

from __future__ import annotations

import sys

if __name__ == "__main__":
    from chimol.__main__ import _dispatch

    raise SystemExit(_dispatch(sys.argv[1:]))
