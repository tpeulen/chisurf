import logging
import sys
import traceback

from chisurf.gui import QtCore

# basic logger functionality
log = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stdout)
log.addHandler(handler)


_qt_version = getattr(QtCore, "QT_VERSION", None)
if _qt_version is not None and _qt_version >= 0x50501:

    def excepthook(type_, value, traceback_):
        traceback.print_exception(type_, value, traceback_)
        QtCore.qFatal("")

    sys.excepthook = excepthook


def show_exception_box(log_msg):
    """Report an uncaught exception to the user.

    Routed through :mod:`chisurf.gui.dialogs`, which logs unconditionally and
    raises the modal box only when someone can dismiss it — an un-dismissable
    dialog on the crash path is how a headless run hangs instead of reporting.

    Parameters
    ----------
    log_msg : str
        Formatted traceback and exception message.
    """
    from chisurf.gui import dialogs

    dialogs.error(
        None, "Unexpected error", "Oops. An unexpected error occured.", detail=str(log_msg)
    )


class UncaughtHook(QtCore.QObject):
    _exception_caught = QtCore.Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # this registers the exception_hook() function as hook with the Python interpreter
        sys.excepthook = self.exception_hook

        # connect signal to execute the message box function always on main thread
        self._exception_caught.connect(show_exception_box)

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
            self._exception_caught.emit(log_msg)


# create a global instance of our class to register the hook
qt_exception_hook = UncaughtHook()
