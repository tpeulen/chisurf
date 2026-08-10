"""Construction smoke tests for the tools moved onto ``ChisurfDockTool``.

PRD-23's rule is that a tool window is built offscreen in a test, because a
missing import or a side effect on construction is invisible until someone
opens the tool. These are the windows migrated onto the shared base after the
reference transformers: each must build, must actually be a ``ChisurfDockTool``
(so the migration cannot be silently reverted), and must not open the metadata
store while constructing.
"""

from __future__ import annotations

import pytest
from qtpy import QtWidgets

from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool


@pytest.fixture
def app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _assert_is_tool(widget) -> None:
    """Assert *widget* is a shared-base tool that opened no store on init."""
    assert isinstance(widget, ChisurfDockTool)
    assert getattr(widget, "_mmfdb_db", None) is None, (
        "the tool opened a metadata-store connection while constructing"
    )


def test_navigation_panel_tool_is_a_dock_tool(app):
    """The navigation shell is a tool window, not a parallel kind of window."""
    from chisurf.gui.widgets.navigation import NavigationPanelTool

    assert issubclass(NavigationPanelTool, ChisurfDockTool)
    shell = NavigationPanelTool(title="Smoke", panels=[])
    _assert_is_tool(shell)
    # The base's drag-drop hook is inherited and harmless without a handler.
    shell.on_paths_dropped([])


def test_project_browser_constructs_without_touching_the_store(app):
    """Opening the widget must not open a project database; showing it may."""
    from chisurf.plugins.core.project_browser.gui.tool import ProjectBrowserTool

    tool = ProjectBrowserTool()
    _assert_is_tool(tool)
    assert tool._client is None, "the browser queried projects while constructing"
    assert not tool._refreshed
    # Deferring the load must not lose it: one turn of the event loop populates
    # the tree even without showing the window, because a tool embedded in a hub
    # panel is never shown as a window of its own.
    QtWidgets.QApplication.processEvents()
    assert tool._refreshed


def test_project_browser_loads_when_shown_too(app):
    """Showing the window loads the list even if the posted load has not run."""
    from chisurf.plugins.core.project_browser.gui.tool import ProjectBrowserTool

    tool = ProjectBrowserTool()
    assert not tool._refreshed
    tool.show()
    assert tool._refreshed
    tool.close()


def test_maxent_decay_constructs(app):
    """The MaxEnt window builds on the shared base."""
    from chisurf.plugins.fluorescence_decay.maxent_decay.gui.gui import MaxentDecayWidget

    _assert_is_tool(MaxentDecayWidget())


def test_chimol_window_constructs(app):
    """The molecular viewer window builds on the shared base."""
    pytest.importorskip("OpenGL")
    from chisurf.plugins.chimol.chimol.app.molview_main_window import MolViewPluginWindow

    _assert_is_tool(MolViewPluginWindow())
