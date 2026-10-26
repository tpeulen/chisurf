"""Process-wide test isolation shared by ``test/`` and the plugin test directories.

One pytest process runs tens of thousands of tests, so any module-level state a test
changes and does not put back is inherited by every test after it: green alone, red in the
full run. Each fixture below closes one such leak that was found by watching what changes
across tests (a closed server client behind ``cs.fits``, a login cached for the whole
process, a UI language, a server thread that outlived its test). They live here, at the root,
so the plugin directories get them too -- including the hermetic settings folder, which once
lived in ``test/conftest.py`` and left every plugin test writing the real ``~/.chisurf``.

``test/test_process_state_isolation.py`` proves each one still works.
"""

from __future__ import annotations

import atexit
import importlib.util
import os
import pathlib
import shutil
import sys
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Hermetic test harness
#
# Redirect chisurf's per-user state directory to a temporary location for the
# whole test session so no test -- under test/ or in a plugin's own test directory --
# can read or write the real ``~/.chisurf`` — in
# particular the sample database at ``~/.chisurf/flr/sample_management.db`` and
# the object store. This is set *before* any chisurf import resolves a path, via
# the ``CHISURF_SETTINGS_DIR`` override honoured by ``settings.path_utils.get_path``.
# ---------------------------------------------------------------------------

_REAL_SETTINGS_DIR = pathlib.Path.home() / ".chisurf"
_HERMETIC_SETTINGS_DIR = pathlib.Path(tempfile.mkdtemp(prefix="chisurf-test-settings-"))
os.environ["CHISURF_SETTINGS_DIR"] = str(_HERMETIC_SETTINGS_DIR)
os.environ["MMFDB_SETTINGS_DIR"] = str(_HERMETIC_SETTINGS_DIR)
# One directory per pytest process, tens of MB each (the user database): without this a day of
# runs fills the disk, and a full disk makes every later test fail with ENOSPC.
atexit.register(shutil.rmtree, _HERMETIC_SETTINGS_DIR, ignore_errors=True)

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



def pytest_configure(config):
    """Load ``test/resource_guard.py``: per-test memory/thread record and a hard memory cap.

    Loaded by path, not as ``test.resource_guard``: the standard library has a ``test``
    package of its own, and which one wins depends on ``sys.path`` order.
    """
    path = pathlib.Path(__file__).parent / "test" / "resource_guard.py"
    if not path.is_file():  # a copy of this file in a pytester sandbox
        return
    spec = importlib.util.spec_from_file_location("chisurf_test_resource_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config.pluginmanager.register(module, "chisurf_test_resource_guard")


@pytest.fixture(autouse=True)
def _restore_api_globals():
    """Hand ``chisurf.fits``, ``imported_datasets``, ``__client__`` and the published server back.

    ``ChiSurfAPI.install_proxies`` swaps the first two for proxies onto a server client.
    A test that does that without monkeypatching leaves proxies onto a *closed* client behind,
    and the next test to touch ``cs.fits`` dies with "this client is closed". Only the
    objects are restored, never their contents: module-scoped fixtures fill those lists.
    """
    chisurf = sys.modules.get("chisurf")
    names = ("fits", "imported_datasets", "__client__", "__chisurf_rpc_server__")
    missing = object()
    saved = {n: getattr(chisurf, n, missing) for n in names} if chisurf is not None else {}
    yield
    chisurf = sys.modules.get("chisurf")
    if chisurf is None:
        return
    for name in names:
        before = saved.get(name, missing)
        if before is missing:
            continue
        if getattr(chisurf, name, missing) is not before:
            setattr(chisurf, name, before)


@pytest.fixture(autouse=True)
def _restore_ui_language():
    """Leave the toolkit language as the test found it.

    A test that switches language (``set_locale("pt")``) and fails before its own reset would
    otherwise hand every later test in the session a Portuguese UI. The "explicitly chosen"
    flag and the provider are restored too: once a test sets a language explicitly, the
    application's own language setting is ignored for the rest of the process.
    """
    i18n = sys.modules.get("emtk.i18n")
    if i18n is None:
        try:
            from emtk import i18n  # noqa: PLC0415
        except Exception:  # noqa: BLE001 - no emtk, nothing to restore
            yield
            return
    before = (i18n.get_locale(), i18n._explicit, i18n._provider)
    yield
    if (i18n.get_locale(), i18n._explicit, i18n._provider) == before:
        return
    locale, explicit, provider = before
    i18n._provider = provider
    i18n.set_locale(locale)
    i18n._explicit = explicit


@pytest.fixture(autouse=True)
def _restore_application_palette_and_font():
    """Leave the ``QApplication`` palette and font as the test found them.

    Building the main window applies the ribbon's dark palette to the *application*
    (white text), which is right in the running program and a leak between tests: every
    later delegate or widget painted with the default palette draws white on white, and a
    test that measures painted ink sees nothing. Only acts when Qt is already imported and
    an application exists; non-GUI tests never pay for it.
    """
    qtwidgets = sys.modules.get("qtpy.QtWidgets")
    app = qtwidgets.QApplication.instance() if qtwidgets is not None else None
    saved = (app.palette(), app.font()) if app is not None else None
    yield
    if saved is None:
        return
    qtwidgets = sys.modules.get("qtpy.QtWidgets")
    app = qtwidgets.QApplication.instance() if qtwidgets is not None else None
    if app is None:
        return
    palette, font = saved
    if app.palette() != palette:
        app.setPalette(palette)
    if app.font() != font:
        app.setFont(font)


@pytest.fixture(autouse=True)
def _restore_mmfdb_login_cache():
    """Forget a login a test cached, so the next test is asked to sign in like a fresh process.

    mmfdb-admin keeps its authenticated session in one module-level dict (and mmfdb a runtime
    token registry) so a second panel does not ask for the password again. That is right in the application and a leak between tests:
    a view test that expects the login prompt silently skips it when an earlier test signed in.
    """
    session = sys.modules.get("chisurf.plugins.core.mmfdb_admin.gui.session")
    saved = dict(session._SESSION) if session is not None else None
    credentials = sys.modules.get("mmfdb.security.credentials")
    tokens = dict(credentials.session_token_registry()) if credentials is not None else None
    yield
    session = sys.modules.get("chisurf.plugins.core.mmfdb_admin.gui.session")
    if session is not None:
        session._SESSION.clear()
        session._SESSION.update(saved or {"user": None, "token": None})
    credentials = sys.modules.get("mmfdb.security.credentials")
    if credentials is not None:
        registry = credentials.session_token_registry()
        registry.clear()
        registry.update(tokens or {})


@pytest.fixture(autouse=True)
def _wait_for_dataset_picker_work():
    """Let a picker's database call finish inside the test that started it.

    A dataset picker browses MMFDB on a worker thread and caches the client it built; closing
    the window does not stop the call. Left running, it opened the *next* test's database
    (each test points ``MMFDB_DATABASE_PATH`` at its own ``tmp_path``) and held the write lock
    while that test saved a setup -- ``database is locked`` in a test that never opened a
    picker. The cached client is reset for the same reason: it belongs to the old database.

    pytest orders autouse fixtures of one conftest by name, and tears them down in reverse:
    the name sorts after ``_restore_*`` so this waits *before* those restore the login cache
    the worker may still be importing.
    """
    yield
    picker = sys.modules.get("chisurf.emtk.dataset_picker")
    if picker is not None:
        picker.wait_for_background_work(timeout=60.0)
        picker.reset_session_client()


@pytest.fixture(autouse=True)
def _restore_mmfdb_runtime_config():
    """Give every test the host-registered mmfdb resolvers the application installs at import.

    ``mmfdb.config.reset_runtime_config()`` also drops the resolvers ``chisurf.core.settings``
    registers once (default user, auth, accounts). A test that resets and does not restore left
    every later test in the process resolving ``user_default`` instead of the configured user.
    """
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
            current = getattr(module, name, None)
            # A snapshot taken before ``chisurf.core.settings`` was imported
            # holds ``None``; restoring it would wipe the host registration the
            # application installed in the meantime. Keep a registration that
            # appeared after the snapshot; only undo values a test changed
            # away from a non-``None`` snapshot.
            if value is None and current is not None:
                continue
            setattr(module, name, value)


@pytest.fixture(scope="module", autouse=True)
def _stop_servers_started_by_the_module():
    """Stop every ``ChiSurfServer`` a test module started and did not stop.

    A server holds two ports, a worker thread and a ZMQ context for as long as it lives; a
    module-level helper that starts one lazily and never stops it left it running beside every
    later module. Per module, not per test, because such helpers share one server across a
    module's tests on purpose.
    """
    app = sys.modules.get("chisurf.server.app")
    before = set(app.ChiSurfServer._active_servers) if app is not None else set()
    yield
    app = sys.modules.get("chisurf.server.app")
    if app is None:
        return
    for server in set(app.ChiSurfServer._active_servers) - before:
        try:
            server.stop()
        except Exception:  # noqa: BLE001 - a half-built server must not fail the module
            pass


@pytest.fixture(scope="module", autouse=True)
def _release_imaging_worker_and_caches():
    """Stop the imaging worker process and drop the TTTR/CLSM and reader caches after each module.

    ``pixel_maps`` keeps one spawned worker (reads hold the GIL, so they run out of process)
    and in-process LRU caches for the app's lifetime; in a test run that lifetime is every
    later module, so each photon file read stayed resident — in the worker and here — for
    the rest of the run (2026-10-19 resource record: +1.2 GB from one module, a child
    process that never ended).
    """
    yield
    from test.process_caches import release_process_caches

    release_process_caches()
