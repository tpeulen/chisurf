"""chimol builds without a toolkit: the viewer and the ChiSurf plugin window.

These used to assert the opposite -- that ``Viewer`` is a ``QWidget`` and the
plugin window a ``QMainWindow``. ChiSurf now shows chimol on an emtk surface
(``chisurf.plugins.chimol.app``) around a toolkit-free viewer, so what is worth
holding is that both build and that neither is a Qt object.
"""

import pytest


def test_molview():
    """The viewer a host builds is toolkit-free and has a renderer."""
    from native_window import native_viewer

    viewer = native_viewer()
    try:
        assert viewer.uses_toolkit is False
        assert viewer.renderer is not None
    finally:
        viewer.native_window.close()


def test_molview_plugin_window():
    """The plugin's window is the emtk app, holding a toolkit-free viewer."""
    from emtk.app import ImApp
    from emtk.testing import RecordingPainter

    from chisurf.plugins.chimol.app import make_app

    app = make_app()
    try:
        assert isinstance(app, ImApp)
        app.draw(RecordingPainter(), 0, 0, 900, 600)
        if app._chimol_error:
            pytest.skip(f"chimol unavailable: {app._chimol_error}")
        assert app._chimol.viewer.uses_toolkit is False
    finally:
        app.close()
