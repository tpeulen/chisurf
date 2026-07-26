"""Run an interactive ChiSurf example script without a ChiSurf window (PRD-46).

The ``console`` and ``ipython`` endpoints inject a ``cs`` name into the script's
namespace and expect :data:`chisurf.experiment` to be populated with readers and
model classes.  Both are available head-lessly:
:func:`chisurf.core.experiments.bootstrap.ensure_experiments_registered` performs
the same registration the main window does, and ``chisurf`` itself is the ``cs``
namespace the endpoints hand out.

This module is executed as a subprocess by ``test_scripts.py`` -- never in the
pytest process itself -- because registering the Qt model classes needs an
off-screen ``QApplication`` that must not leak into the Qt-free test suite.

Exit codes
----------
0
    The script ran to completion.
:data:`EXIT_NO_QT`
    No Qt binding / off-screen application is available; the caller skips.
"""

from __future__ import annotations

import os
import pathlib
import sys

#: Exit code telling the caller that this machine cannot provide Qt.
EXIT_NO_QT = 77


def main(argv: list[str]) -> int:
    """Execute the example script named by ``argv[0]`` with ``cs`` injected.

    Parameters
    ----------
    argv : list of str
        Command-line arguments; the first is the path of the script to run.

    Returns
    -------
    int
        Process exit code (see the module docstring).
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    script = pathlib.Path(argv[0]).resolve()

    import chisurf as cs
    from chisurf.core.experiments.bootstrap import (
        ensure_experiments_registered,
        ensure_qt_application,
    )

    # Most reader and model classes are QWidget subclasses; without an
    # application they are silently dropped and the script cannot resolve its
    # models by name.
    if not ensure_qt_application():
        return EXIT_NO_QT
    ensure_experiments_registered(allow_widgets=True)

    namespace = {"__name__": "__main__", "__file__": str(script), "cs": cs}
    source = script.read_text(encoding="utf-8")
    exec(compile(source, str(script), "exec"), namespace)  # noqa: S102 - the point
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
