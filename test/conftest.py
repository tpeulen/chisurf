import atexit
import os
import pathlib
import shutil
import sys
import tempfile

import pytest

# Add the project root to sys.path so 'chisurf' can be imported in all tests
TOPDIR = pathlib.Path(__file__).parent.parent
if str(TOPDIR) not in sys.path:
    sys.path.insert(0, str(TOPDIR))

# Add 'test' directory to sys.path so 'utils' can be imported by tests in subfolders
TESTDIR = TOPDIR / "test"
if str(TESTDIR) not in sys.path:
    sys.path.insert(0, str(TESTDIR))

# The hermetic settings folder (CHISURF_SETTINGS_DIR / MMFDB_SETTINGS_DIR, a fresh user
# database, the guard against the real ~/.chisurf) lives in the root conftest.py, so the
# plugin test directories are hermetic too.


@pytest.fixture(autouse=True)
def _forget_recent_projects():
    """Start every test with an empty recent-projects list.

    The hermetic settings folder is shared by the whole session, so a project one test opened
    or saved used to reach every later test: a shell drawn after it showed that project under
    File > Recent instead of "No recent projects", and its Qt-inventory parity failed by
    test order alone.
    """
    yield
    try:
        (pathlib.Path(os.environ["CHISURF_SETTINGS_DIR"]) / "recent_projects.json").unlink(missing_ok=True)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _enforce_c_numeric_locale():
    """Ensure LC_NUMERIC stays 'C' even if a test or Qt initializes the user locale."""
    import locale

    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
    except Exception:
        pass
    yield
    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
    except Exception:
        pass


# Import utils and setup paths (backward compatibility for tests that still use it)
try:
    import utils

    utils.set_search_paths(TOPDIR)
except ImportError:
    pass


def pytest_sessionfinish(session, exitstatus):
    """Run exit cleanup before pytest's final garbage collection.

    1. pyqtgraph: Every ViewBox connects its ``destroyed`` signal to a Python lambda.
       pyqtgraph disconnects them in ``pyqtgraph.cleanup()``, registered with
       ``atexit`` and ``aboutToQuit`` -- but a test session never quits the
       application, and pytest collects garbage *before* ``atexit`` runs. Any plot
       still alive then is destroyed through a slot whose Python callable is
       already gone, and the process segfaults after every test has passed.

    2. ChiSurfServer: Server instances running in background threads must be stopped
       and joined, otherwise the daemon thread running zmq.Poller.poll segfaults
       when Python unloads native C-extensions on exit.
    """
    pyqtgraph = sys.modules.get("pyqtgraph")
    if pyqtgraph is not None:
        pyqtgraph.cleanup()

    chisurf_app = sys.modules.get("chisurf.server.app")
    if chisurf_app is not None:
        server_cls = getattr(chisurf_app, "ChiSurfServer", None)
        if server_cls is not None:
            for s in list(getattr(server_cls, "_active_servers", [])):
                try:
                    s.stop()
                except Exception:
                    pass

    chisurf = sys.modules.get("chisurf")
    if chisurf is not None:
        for attr in ("__chisurf_rpc_server__", "__mmfdb_rpc_server__"):
            srv = getattr(chisurf, attr, None)
            if srv is not None:
                try:
                    srv.stop()
                except Exception:
                    pass
        thread = getattr(chisurf, "__chisurf_rpc_server_thread__", None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
