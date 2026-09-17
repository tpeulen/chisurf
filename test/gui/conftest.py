import pytest
from pyqtgraph.graphicsItems.ViewBox import ViewBox
from qtpy.QtWidgets import QApplication

import chisurf.gui


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests (reader-heavy PDB, TTTR, etc.)",
    )
    parser.addoption(
        "--run-xfail",
        action="store_true",
        default=False,
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


@pytest.fixture(autouse=True)
def _close_plots_this_test_created():
    """Close the chiplot plots a test builds and forgets.

    A ``Plot`` is a top-level widget owned by Python, while its scene and the
    graphics items in it are owned by Qt. A forgotten one dies whenever the
    garbage collector reaches it -- in the middle of some later test, taking
    its scene and items along while Qt is still delivering layout events to
    them. One of those events then lands on an item whose C++ half has just
    gone ("wrapped C/C++ object of type LabelItem has been deleted"), and the
    event loop that raised it segfaults. Over a whole suite run it took about
    a third of the tests to accumulate, and it surfaced in whichever test was
    running at the time rather than in any that caused it.

    Only plots this test created are closed: destroying what an earlier test
    or a module-scoped fixture still owns just moves the crash.
    """
    from chisurf.gui.chiplot.canvas import Plot

    def _plots():
        app = QApplication.instance()
        return [w for w in app.topLevelWidgets() if isinstance(w, Plot)] if app else []

    existing = {id(plot) for plot in _plots()}
    yield
    for plot in _plots():
        if id(plot) in existing:
            continue
        try:
            plot.close()
            plot.deleteLater()
        except RuntimeError:
            # Its C++ half is already gone -- an owning window took it. Asking
            # the wrapper anything from here is what the fixture is trying to
            # prevent, so leave it alone.
            continue

    # pyqtgraph keeps a registry of every ViewBox ever made, and a ViewBox that
    # dies walks it: `destroyed` -> forgetView -> updateAllViewLists ->
    # menu.setViewList for *each* entry (ViewBox.py 288/1772/1798, 0.14.0).
    # One stale entry whose menu Qt has already deleted turns that into
    # "wrapped C/C++ object of type QComboBox has been deleted" -- raised
    # inside a C++ destructor, which aborts the process rather than failing a
    # test. The registry is bookkeeping for views linked *by name*, which
    # nothing in this suite does. Only the entries Qt has already deleted are
    # dropped: emptying the registry outright releases the last reference to
    # every live ViewBox at once, and destroying that many at a stroke inside
    # a fixture teardown is its own crash (SIGBUS).
    try:
        from PyQt5 import sip
    except ImportError:  # pragma: no cover - a non-PyQt binding
        return
    for view in [v for v in ViewBox.AllViews if sip.isdeleted(v)]:
        ViewBox.AllViews.pop(view, None)
    for name in [n for n, v in ViewBox.NamedViews.items() if sip.isdeleted(v)]:
        ViewBox.NamedViews.pop(name, None)


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
    # Deliberately NOT qtbot.addWidget(window): pytest-qt closes *and*
    # deleteLater()s everything registered with it at the end of each test,
    # and this window is the application's singleton -- ``chisurf.cs`` goes on
    # pointing at it. The next test to use this fixture got the deleted object
    # back from get_app(), registered the dangling wrapper again, and its
    # teardown called close() on freed memory: a segfault inside
    # QWidget::event, raised from a fixture generator, a third of the way
    # through the suite and never in a test that had anything to do with it.
    yield chisurf
    window.hide()
