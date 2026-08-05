"""The main window's dock arrangement: default, persistence, and reset.

The layout has two sources — the arrangement authored in
:meth:`Main.apply_default_dock_layout` and whatever the last session saved via
``QSettings``. The saved one is applied *over* the default, so for a year every
change to the default was invisible: the window that opened was always the one
from disk. These tests pin the seam between the two, and the width that keeps
the tab labels from eliding to ``Read…``/``Dat…``.

``QSettings`` is redirected to a per-test ini file; without that the tests would
read the developer's own saved layout and pass or fail by accident.
"""

import pytest
from qtpy import QtCore

import chisurf as cs

DOCKS_IN_THE_STACK = (
    "dockWidgetReadData",
    "dockWidgetDatasets",
    "dockWidgetAnalysis",
    "dockWidgetPlot",
    "dockWidgetHistory",
)


@pytest.fixture
def window(qapp, qtbot, tmp_path, monkeypatch):
    """Build a main window whose saved layout lives in ``tmp_path``, not the user's."""
    ini = tmp_path / "MainWindow.ini"

    class IsolatedSettings(QtCore.QSettings):
        """Answer to the app's ``QSettings("ChiSurf", "MainWindow")`` call."""

        def __init__(self, *args, **kwargs):
            super().__init__(str(ini), QtCore.QSettings.IniFormat)

    monkeypatch.setattr(QtCore, "QSettings", IsolatedSettings)

    import chisurf.gui.widgets  # noqa: F401  (binds cs.gui.widgets for the console below)

    if getattr(cs, "console", None) is None:
        cs.console = cs.gui.widgets.ipython.QIPythonWidget()
        cs.console.history_widget = None

    from chisurf.gui.main import Main

    win = Main()
    qtbot.addWidget(win)
    win.resize(1600, 1000)
    win.init_setups()
    win.define_actions()
    win.arrange_widgets()
    win.show()
    qapp.processEvents()
    yield win
    # qtbot closes the window *after* this finalizer, which is after
    # ``monkeypatch`` has put the real ``QSettings`` back — and ``closeEvent``
    # saves the layout. Writing then lands in the developer's own preferences
    # and replaces the window layout they had, which is exactly the accident
    # this file is about. Take the save off this instance first.
    win._save_window_state = lambda: None
    win.hide()


def _stack(win):
    """Object names of the docks tabbed together with Read data."""
    docks = [win.dockWidgetReadData, *win.tabifiedDockWidgets(win.dockWidgetReadData)]
    return {d.objectName() for d in docks}


def test_the_default_puts_all_five_docks_in_one_tab_stack(window):
    assert _stack(window) == set(DOCKS_IN_THE_STACK)


def test_the_default_column_is_wide_enough_for_the_tab_labels(window):
    """Sized to the read-data widgets alone the five labels elide to ``Dat…``."""
    window._apply_read_data_dock_width()
    window.show()
    tab_bar = window._dock_tab_bar(window.dockWidgetReadData)
    assert tab_bar is not None, "the tabified docks have no tab bar"
    assert window.dockWidgetReadData.width() >= tab_bar.sizeHint().width()


def test_a_layout_saved_by_this_version_is_restored_over_the_default(window):
    window.addDockWidget(QtCore.Qt.RightDockWidgetArea, window.dockWidgetAnalysis)
    window._save_window_state()

    window.apply_default_dock_layout()
    assert window.dockWidgetAnalysis.objectName() in _stack(window)

    assert window._restore_window_state() is True
    assert window.dockWidgetAnalysis.objectName() not in _stack(window)


def test_a_layout_saved_by_an_older_version_is_ignored(window):
    """Otherwise a changed default never reaches a user who has ever run the app."""
    window.addDockWidget(QtCore.Qt.RightDockWidgetArea, window.dockWidgetAnalysis)
    window._save_window_state()
    QtCore.QSettings().setValue("layout_version", window._LAYOUT_VERSION - 1)

    window.apply_default_dock_layout()

    assert window._restore_window_state() is False
    assert window.dockWidgetAnalysis.objectName() in _stack(window)


def test_reset_puts_the_docks_back_and_forgets_the_saved_layout(window):
    window.addDockWidget(QtCore.Qt.RightDockWidgetArea, window.dockWidgetAnalysis)
    window.dockWidgetPlot.setVisible(False)
    window._save_window_state()

    window.onResetWindowLayout()

    assert _stack(window) == set(DOCKS_IN_THE_STACK)
    assert window.dockWidgetPlot.isVisible()
    # Removed from disk as well, or the next start would undo the reset.
    assert QtCore.QSettings().value("state") is None


def test_every_dock_in_the_stack_has_a_tab_colour(window):
    """The colours are keyed by dock *title*; a renamed dock silently loses its own.

    ``History / Log`` outlived the dock it was named for, so the Logging tab
    rendered in the default colour while the other four were coloured.
    """
    colors = cs.core.settings.gui["dock_tab_colors"]
    titles = {getattr(window, name).windowTitle() for name in DOCKS_IN_THE_STACK}
    assert titles <= set(colors), f"no tab colour for {titles - set(colors)}"
