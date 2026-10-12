import os
import pathlib
import sys

import pytest

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


@pytest.fixture(autouse=True)
def _restore_ui_language():
    """Leave the toolkit language as the test found it.

    A test that switches language (``set_locale("pt")``) and fails before its own reset would
    otherwise hand every later test in the session a Portuguese UI.
    """
    try:
        from emtk import i18n
    except Exception:
        yield
        return
    before = i18n.get_locale()
    yield
    if i18n.get_locale() != before:
        i18n.set_locale(before)


@pytest.fixture(autouse=True)
def _restore_mmfdb_runtime_config():
    """Give every test the host-registered mmfdb resolvers the application installs at import.

    ``mmfdb.config.reset_runtime_config()`` also drops the resolvers ``chisurf.core.settings``
    registers once (default user, auth, accounts). A test that resets and does not restore left
    every later test in the process resolving ``user_default`` instead of the configured user.
    """
    import sys

    module = sys.modules.get("mmfdb.config")
    names = (
        "_CONFIG",
        "_DEFAULT_USER_ID_RESOLVER",
        "_AUTH_CONFIG_RESOLVER",
        "_ADMIN_BOOTSTRAP_RESOLVER",
        "_DEFAULT_ACCOUNTS_RESOLVER",
    )
    saved = (
        {name: getattr(module, name) for name in names if hasattr(module, name)} if module else {}
    )
    yield
    if module is not None:
        for name, value in saved.items():
            setattr(module, name, value)


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
