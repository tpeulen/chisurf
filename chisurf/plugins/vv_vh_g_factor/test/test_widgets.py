"""The retained Qt caller surface hosts the actual native calibration app."""

from chisurf.plugins.vv_vh_g_factor.gui.app import GFactorApp, create_host


class TestNativeVvVhGFactorHost:
    def test_creation(self, qapp, qtbot):
        widget = create_host()
        qtbot.addWidget(widget)
        try:
            assert isinstance(widget.control, GFactorApp)
            assert widget.control.model.g_factor is None
        finally:
            widget.close()

    def test_window_title(self, qapp, qtbot):
        widget = create_host()
        qtbot.addWidget(widget)
        try:
            assert widget.windowTitle() == "VV/VH G-Factor Calculator"
        finally:
            widget.close()
