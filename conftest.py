"""Process-wide test isolation shared by ``test/`` and the plugin test directories.

One pytest process runs tens of thousands of tests, so any module-level state a test
changes and does not put back is inherited by every test after it: green alone, red in the
full run. Each fixture below closes one such leak that was found by watching what changes
across tests (a closed server client behind ``cs.fits``, a login cached for the whole
process, a UI language, a server thread that outlived its test). They live here, at the root,
so the plugin directories get them too; ``test/conftest.py`` keeps what only ``test/`` needs
(the hermetic settings folder).

``test/test_process_state_isolation.py`` proves each one still works.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest


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
    """Stop the imaging worker process and drop the TTTR/CLSM caches after each module.

    ``pixel_maps`` keeps one spawned worker (reads hold the GIL, so they run out of process)
    and in-process LRU caches for the app's lifetime; in a test run that lifetime is every
    later module, so each photon file read stayed resident — in the worker and here — for
    the rest of the run (2026-10-19 resource record: +1.2 GB from one module, a child
    process that never ended).
    """
    yield
    pixel_maps = sys.modules.get("chisurf.core.fluorescence.imaging.pixel_maps")
    if pixel_maps is not None:
        pixel_maps.shutdown_proc_pool()
        pixel_maps.clear_imaging_cache()
