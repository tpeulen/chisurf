"""Construction smoke tests for the project browser tool window.

The window is built in a test because a missing import or a side effect on construction is
invisible until someone opens the tool; it must not open the metadata store while constructing.
"""

from __future__ import annotations


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
