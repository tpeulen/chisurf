#!/usr/bin/env python
"""Regenerate the screenshots of one guide module.

Each module here holds the ``_grab_*`` functions of a range of guides. Run one
module per process -- several grabs start worker threads or servers -- from the
repository root in the GUI environment, with settings isolated so a grab never
writes the user's real preferences::

    CHISURF_SETTINGS_DIR=$(mktemp -d) \
    PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
    python docs/guides/screenshots/run.py guides_26_36 [_grab_name ...]

With no names every ``_grab_*`` function in the module runs. Grabs that need
data outside the repository (``spot_finder`` reads the tttr-data checkout at
``$CHISURF_TTTR_DATA``, default ``~/dev/tttr-data``) are skipped with a message
when it is missing. Read every PNG afterwards: a grab that ran is not a figure
that looks right.
"""

from __future__ import annotations

import importlib
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qtpy.QtWidgets import QApplication  # noqa: E402

import chisurf.core.settings  # noqa: E402,F401


def main(argv: list[str]) -> int:
    """Run the named grabs of one module; return the number that failed."""
    if not argv:
        print(__doc__)
        return 2
    if not os.environ.get("CHISURF_SETTINGS_DIR"):
        print("set CHISURF_SETTINGS_DIR to a scratch directory first")
        return 2
    app = QApplication.instance() or QApplication([])  # noqa: F841
    module = importlib.import_module(argv[0])
    names = argv[1:] or sorted(n for n in dir(module) if n.startswith("_grab_"))
    failed = 0
    for name in names:
        try:
            getattr(module, name)()
        except Exception as exc:  # report and keep going
            failed += 1
            print(f"SKIP {name}: {type(exc).__name__}: {exc}")
    return failed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
