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


def test_project_browser_constructs_without_touching_the_store():
    """Opening the window must not open a project database; its first frame may.

    Ported from the retired Qt ``ProjectBrowserTool`` to the emtk app that replaced it.
    """
    from types import SimpleNamespace

    from chisurf.plugins.core.project_browser.gui.app import ProjectBrowserApp
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    app = ProjectBrowserApp(model=ProjectBrowserModel(context=SimpleNamespace()))
    try:
        assert app.model._client is None, "the browser queried projects while constructing"
        assert not app.loaded
    finally:
        app.close()


def test_project_browser_loads_when_shown_too():
    """Drawing the window (showing it, or embedding it in a hub) starts the project list load."""
    from types import SimpleNamespace

    from emtk.testing import RecordingPainter

    from chisurf.plugins.core.project_browser.gui.app import ProjectBrowserApp
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    class Client:
        calls = 0

        def list_projects(self, show_public=True, search=None):
            Client.calls += 1
            return []

    app = ProjectBrowserApp(model=ProjectBrowserModel(client=Client(), context=SimpleNamespace()))
    try:
        assert not app.loaded
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
        assert app.loaded
        if app.jobs.future is not None:
            app.jobs.future.result(timeout=30)
        assert Client.calls == 1
    finally:
        app.close()
