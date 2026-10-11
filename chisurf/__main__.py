"""Launch ChiSurf and retain startup failures in the diagnostic log."""

from __future__ import annotations

import logging
import os


def main() -> None:
    """Run the application, logging and re-raising any startup failure.

    The emtk main surface (``chisurf.emtk.main_app``) is the ChiSurf window; it does not import Qt.
    ``--qt`` opens the Qt main window instead, kept as the reference the emtk window is measured
    against until it reaches parity. ``--emtk-shell`` is accepted and selects the default.
    """
    import sys

    args = sys.argv[1:]
    if "--qt" not in args:
        from chisurf.emtk.main_app import main as emtk_shell

        argv = [arg for arg in args if arg != "--emtk-shell"]
        raise SystemExit(emtk_shell(argv))
    sys.argv = [sys.argv[0], *(arg for arg in args if arg != "--qt")]
    try:
        import faulthandler
        from datetime import datetime

        from chisurf.core.settings.path_utils import get_path

        # Keep the file open while native code runs: the signal handler cannot
        # allocate a file when reporting a crash. get_path honors scratch settings.
        crash_log = get_path("settings") / f"crash_{datetime.now():%Y%m%d_%H%M%S}.log"
        with crash_log.open("w") as crash_file:
            # enable already registers fatal signals; registering them twice fails.
            faulthandler.enable(file=crash_file, all_threads=True)
            try:
                from chisurf.gui import get_app

                exit_code = get_app().exec()
            finally:
                # Never leave the signal handler referencing a closed file.
                try:
                    faulthandler.disable()
                except Exception:
                    logging.exception("Failed to disable ChiSurf crash reporting")
    except Exception:
        logging.exception("ChiSurf encountered an error during startup")
        raise

    # Keep the existing hard exit until native extension shutdown is retired:
    # interpreter finalization can crash while tearing down Qt object graphs.
    os._exit(exit_code)


if __name__ == "__main__":
    main()
