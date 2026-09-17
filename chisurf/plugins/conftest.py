import sys
import pathlib
import pytest
import os

# Matplotlib must not open windows during a test run. The default backend on
# macOS is ``macosx``, a native GUI backend, so any test that draws a figure
# pops a real window onto the user's screen — and a run that is meant to be
# headless becomes interactive, can block on a window manager, and scatters
# windows over whatever else is happening. Qt is already muzzled by
# ``QT_QPA_PLATFORM=offscreen``; that setting does nothing for matplotlib, which
# picks its own backend. Set before any import pulls matplotlib in, because the
# backend is resolved at first import and cannot be changed afterwards.
os.environ.setdefault("MPLBACKEND", "Agg")

_topdir = pathlib.Path(__file__).resolve().parents[2]
if str(_topdir) not in sys.path:
    sys.path.insert(0, str(_topdir))


@pytest.fixture(scope="session")
def qapp():
    from qtpy.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def pytest_sessionfinish(session, exitstatus):
    """Run pyqtgraph's exit cleanup before pytest's final garbage collection.

    Every ViewBox connects its ``destroyed`` signal to a Python lambda.
    pyqtgraph disconnects them in ``pyqtgraph.cleanup()``, registered with
    ``atexit`` and ``aboutToQuit`` -- but a test session never quits the
    application, and pytest collects garbage *before* ``atexit`` runs. Any plot
    still alive then is destroyed through a slot whose Python callable is
    already gone, and the process segfaults after every test has passed.
    """
    pyqtgraph = sys.modules.get("pyqtgraph")
    if pyqtgraph is not None:
        pyqtgraph.cleanup()
