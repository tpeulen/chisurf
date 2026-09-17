"""
https://timlehr.com/python-exception-hooks-with-qt-message-box/
"""

import logging
import sys
import traceback

from qtpy import QtCore

log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler(stream=sys.stdout))


class UncaughtHook(QtCore.QObject):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # this registers the exception_hook() function as hook with the Python interpreter
        sys.excepthook = self.exception_hook

    @staticmethod
    def show_exception_box(log_msg):
        """Report an uncaught exception to the user.

        Routed through :mod:`chisurf.gui.dialogs`, which logs unconditionally
        and raises the modal box only when someone can dismiss it — an
        un-dismissable dialog on the crash path is how a headless run hangs
        instead of reporting.

        Parameters
        ----------
        log_msg : str
            Formatted traceback and exception message.
        """
        from chisurf.gui import dialogs

        dialogs.error(
            None,
            "Critical error occurred",
            "Oops. An unexpected error occurred.",
            detail=str(log_msg),
        )

    def exception_hook(self, exc_type, exc_value, exc_traceback):
        """Function handling uncaught exceptions.
        It is triggered each time an uncaught exception occurs.
        """
        if issubclass(exc_type, KeyboardInterrupt):
            # ignore keyboard interrupt to support console applications
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        else:
            exc_info = (exc_type, exc_value, exc_traceback)
            log_msg = "\n".join(
                ["".join(traceback.format_tb(exc_traceback)), f"{exc_type.__name__}: {exc_value}"]
            )
            log.critical(f"Uncaught exception:\n {log_msg}", exc_info=exc_info)

            # trigger message box show
            self.show_exception_box(log_msg)


# create a global instance of our class to register the hook
qt_exception_hook = UncaughtHook()
