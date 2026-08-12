import pytest
from qtpy.QtWidgets import QApplication

import chisurf.gui


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow", action="store_true", default=False,
        help="Run slow tests (reader-heavy PDB, TTTR, etc.)",
    )
    parser.addoption(
        "--run-xfail", action="store_true", default=False,
        help="Run expected-to-fail (xfail) tests",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-slow"):
        skip_slow = pytest.mark.skip(reason="Use --run-slow to include")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
    if not config.getoption("--run-xfail"):
        skip_xfail = pytest.mark.skip(reason="Use --run-xfail to include")
        for item in items:
            if "xfail" in item.keywords:
                item.add_marker(skip_xfail)


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication fixture for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def chisurf_app(qtbot):
    """Bootstrap ChiSurf's main window and register it with qtbot.

    Yields the :mod:`chisurf` module, whose ``cs`` attribute is the main
    window. ``get_app`` returns the :class:`QApplication` and puts the window in
    that global rather than on the application object, so the previous
    ``app.cs`` raised ``AttributeError: 'QApplication' object has no attribute
    'cs'`` -- at *setup*, which turns into an error for every test using this
    fixture rather than a failure anyone would read as "the fixture is wrong".
    """
    chisurf.gui.get_app()
    window = chisurf.cs
    assert window is not None, "get_app did not build a main window"
    qtbot.addWidget(window)
    yield chisurf
