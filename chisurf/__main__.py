"""Launch ChiSurf and retain startup failures in the diagnostic log."""

from __future__ import annotations

import logging
from collections.abc import Callable


def _run_with_crash_log(launch: Callable[[], int]) -> int:
    """Run *launch* with a native crash log open, logging and re-raising any failure.

    A start that fails -- in the emtk shell, its splash included -- leaves one record: the traceback in the diagnostic
    log (``logging.exception``), a ``crash_<time>.log`` in the settings folder for faults in
    native code, and the original exception re-raised, so the terminal shows it too.

    Parameters
    ----------
    launch : callable
        Opens the window and returns its exit code when it closes.

    Returns
    -------
    int
        The exit code *launch* returned.
    """
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
            frame_handler = _record_frame_errors(crash_file)
            try:
                return int(launch() or 0)
            finally:
                _forget_frame_errors(frame_handler)
                # Never leave the signal handler referencing a closed file.
                try:
                    faulthandler.disable()
                except Exception:
                    logging.exception("Failed to disable ChiSurf crash reporting")
    except Exception:
        logging.exception("ChiSurf encountered an error during startup")
        raise


def _record_frame_errors(crash_file):
    """Copy every distinct emtk frame error into *crash_file*; return the handler (or None).

    emtk draws an error panel and logs the traceback when a frame raises (the event loop
    would otherwise swallow it and present an empty surface); this puts the same
    traceback in the crash log the user is asked for.
    """
    try:
        from emtk.frame_errors import add_frame_error_handler
    except ImportError:
        return None

    def handler(record) -> None:
        crash_file.write(f"emtk frame error\n{record.text}\n")
        crash_file.flush()

    add_frame_error_handler(handler)
    return handler


def _forget_frame_errors(handler) -> None:
    """Undo :func:`_record_frame_errors`."""
    if handler is None:
        return
    from emtk.frame_errors import remove_frame_error_handler

    remove_frame_error_handler(handler)


def _require_emtk() -> None:
    """Refuse to start against an emtk older than ChiSurf needs, saying which and why."""
    import sys

    from chisurf.emtk.requirement import EmtkTooOld, check_emtk

    try:
        check_emtk()
    except EmtkTooOld as error:
        logging.error("%s", error)
        print(f"ChiSurf cannot start.\n{error}", file=sys.stderr)
        raise SystemExit(2) from None


USAGE = """usage: python -m chisurf [--size WxH] [--screenshot PATH [--backend offscreen]]

Open the ChiSurf window (the emtk shell).

options:
  -h, --help         show this message and exit
  --size WxH         the main window's size in pixels
  --screenshot PATH  render one frame of the window offscreen to PATH and exit
  --backend offscreen
                     draw offscreen (implied by --screenshot)
"""


def main() -> None:
    """Run the application, logging and re-raising any startup failure.

    The emtk main surface (``chisurf.emtk.main_app``) is the ChiSurf window; it does not import
    Qt. ``--emtk-shell`` is still accepted and selects it; ``-h`` / ``--help`` prints
    :data:`USAGE` without opening a window.
    """
    import sys

    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(USAGE, end="")
        raise SystemExit(0)
    _require_emtk()
    argv = [arg for arg in args if arg != "--emtk-shell"]

    def launch_emtk() -> int:
        from chisurf.emtk.main_app import main as emtk_shell

        return emtk_shell(argv)

    raise SystemExit(_run_with_crash_log(launch_emtk))


if __name__ == "__main__":
    main()
