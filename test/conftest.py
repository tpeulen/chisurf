import os
import pathlib
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

# ---------------------------------------------------------------------------
# Hermetic test harness (PRD-18)
#
# Redirect chisurf's per-user state directory to a temporary location for the
# whole test session so no test can read or write the real ``~/.chisurf`` — in
# particular the sample database at ``~/.chisurf/flr/sample_management.db`` and
# the object store. This is set *before* any chisurf import resolves a path, via
# the ``CHISURF_SETTINGS_DIR`` override honoured by ``settings.path_utils.get_path``.
# ---------------------------------------------------------------------------

_REAL_SETTINGS_DIR = pathlib.Path.home() / ".chisurf"
_HERMETIC_SETTINGS_DIR = pathlib.Path(tempfile.mkdtemp(prefix="chisurf-test-settings-"))
os.environ["CHISURF_SETTINGS_DIR"] = str(_HERMETIC_SETTINGS_DIR)
os.environ["MMFDB_SETTINGS_DIR"] = str(_HERMETIC_SETTINGS_DIR)

# Matplotlib must not open windows during a test run. The default backend on
# macOS is ``macosx``, a native GUI backend, so any test that draws a figure
# pops a real window onto the user's screen — and a run that is meant to be
# headless becomes interactive, can block on a window manager, and scatters
# windows over whatever else is happening. Qt is already muzzled by
# ``QT_QPA_PLATFORM=offscreen``; that setting does nothing for matplotlib, which
# picks its own backend. Set before any import pulls matplotlib in, because the
# backend is resolved at first import and cannot be changed afterwards.
os.environ.setdefault("MPLBACKEND", "Agg")


@pytest.fixture(scope="session", autouse=True)
def _hermetic_settings_dir():
    """Ensure every test uses the temp settings dir, never the real ~/.chisurf."""
    os.environ["CHISURF_SETTINGS_DIR"] = str(_HERMETIC_SETTINGS_DIR)
    os.environ["MMFDB_SETTINGS_DIR"] = str(_HERMETIC_SETTINGS_DIR)
    # Pre-create a fresh, current-schema user database so resolve_database_path()
    # does not copy the shipped curated source DB (which carries demo data and an
    # older schema). Tests get a clean DB; isolation is preserved.
    try:
        from mmfdb.repository import MFDatabase
        from mmfdb.store.database_resolver import user_database_path

        user_db = user_database_path()
        user_db.parent.mkdir(parents=True, exist_ok=True)
        if not user_db.exists():
            MFDatabase(str(user_db)).close()
    except Exception:
        pass
    yield _HERMETIC_SETTINGS_DIR


@pytest.fixture(autouse=True)
def _guard_real_user_db():
    """Fail loudly if a test resolves chisurf state to the real ~/.chisurf."""
    from mmfdb.store.database_resolver import (
        object_store_root,
        user_database_path,
    )

    from chisurf.core.settings.path_utils import get_path

    real = _REAL_SETTINGS_DIR.resolve()
    assert get_path("settings").resolve() != real, (
        "Test resolved the REAL settings dir; CHISURF_SETTINGS_DIR not in effect."
    )
    assert real not in user_database_path().resolve().parents, (
        f"Test would use the REAL user database at {user_database_path()}."
    )
    assert (
        real not in object_store_root().resolve().parents and object_store_root().resolve() != real
    ), f"Test would use the REAL object store at {object_store_root()}."
    yield


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
