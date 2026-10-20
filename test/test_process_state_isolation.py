"""The root ``conftest.py`` hands process-wide state back after each test.

Each case runs a two-test module in a throwaway pytest session that has only the root
conftest: the first test leaks, the second asserts it sees the original again. If a fixture
is dropped or stops restoring, the inner second test fails and so does the case here.
"""

from __future__ import annotations

import pathlib

import pytest

pytest_plugins = ["pytester"]

ROOT_CONFTEST = (pathlib.Path(__file__).resolve().parent.parent / "conftest.py").read_text()


@pytest.fixture
def isolated(pytester):
    """A pytester session carrying the root conftest (and its own rootdir)."""
    pytester.makeconftest(ROOT_CONFTEST)
    return pytester


def _passes(pytester, source: str):
    pytester.makepyfile(source)
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider", "-q")
    result.assert_outcomes(passed=2)


def test_proxies_installed_by_a_test_are_taken_back(isolated):
    _passes(
        isolated,
        '''
        import chisurf as cs

        REAL = (cs.fits, cs.imported_datasets)

        def test_a_leaks_proxies_onto_a_client_it_then_closes():
            cs.fits = "proxy on a closed client"
            cs.imported_datasets = "proxy on a closed client"

        def test_b_meets_the_real_lists_again():
            assert (cs.fits, cs.imported_datasets) == REAL
            assert cs.fits is REAL[0]
        ''',
    )


def test_a_language_chosen_by_a_test_is_taken_back(isolated):
    _passes(
        isolated,
        '''
        from emtk import i18n

        BEFORE = (i18n.get_locale(), i18n._explicit)

        def test_a_picks_a_language():
            i18n.set_locale("pt")

        def test_b_has_the_original_language_and_no_explicit_choice():
            assert (i18n.get_locale(), i18n._explicit) == BEFORE
        ''',
    )


def test_a_cached_mmfdb_login_is_forgotten(isolated):
    _passes(
        isolated,
        '''
        from chisurf.plugins.core.mmfdb_admin.gui import session

        def test_a_signs_in():
            session.cache_session("admin", "a-token")
            assert session.cached_user() == "admin"

        def test_b_is_asked_to_sign_in():
            assert session.cached_user() is None
            assert session.cached_token() is None
        ''',
    )


def test_a_server_a_module_leaves_running_is_stopped_with_the_module(isolated):
    isolated.makepyfile(
        test_one='''
        import threading
        from chisurf.server.app import ChiSurfServer
        from test_process_state_isolation_ports import find_free_port

        def test_a_starts_a_server_and_never_stops_it():
            server = ChiSurfServer(cmd_port=find_free_port(), pub_port=find_free_port())
            threading.Thread(target=server.serve_forever, daemon=True).start()
            assert server.wait_ready()
        ''',
        test_two='''
        from chisurf.server.app import ChiSurfServer

        def test_b_the_next_module_runs_beside_no_leftover_server():
            assert not ChiSurfServer._active_servers
        ''',
        test_process_state_isolation_ports='''
        import socket

        def find_free_port():
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                return s.getsockname()[1]
        ''',
    )
    result = isolated.runpytest_subprocess("-p", "no:cacheprovider", "-q", "test_one.py", "test_two.py")
    result.assert_outcomes(passed=2)


def test_a_runtime_mmfdb_token_is_forgotten(isolated):
    _passes(
        isolated,
        '''
        from mmfdb.security import credentials

        def test_a_stores_a_token():
            credentials.store_runtime_session_token("127.0.0.1", 8765, "admin", "secret")
            assert credentials.load_runtime_session_token("127.0.0.1", 8765, "admin") == "secret"

        def test_b_finds_none():
            assert credentials.load_runtime_session_token("127.0.0.1", 8765, "admin") is None
        ''',
    )


def test_a_dataset_picker_call_finishes_inside_the_test_that_started_it(isolated):
    _passes(
        isolated,
        '''
        import threading

        from chisurf.emtk import dataset_picker

        RELEASE = threading.Event()
        FINISHED = threading.Event()

        def slow_browse():
            RELEASE.wait(10)
            FINISHED.set()

        def test_a_leaves_a_database_call_running():
            dataset_picker._SESSION_CLIENT = "client of this test's database"
            dataset_picker._submit(slow_browse)
            threading.Timer(0.3, RELEASE.set).start()

        def test_b_starts_after_it_finished_and_builds_its_own_client():
            assert FINISHED.is_set()
            assert dataset_picker._SESSION_CLIENT is None
        ''',
    )
