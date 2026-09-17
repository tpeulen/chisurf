import pytest


class TestVvVhGFactorCalculator:
    def test_creation(self, qapp, qtbot):
        pytest.importorskip("pyqtgraph")
        from chisurf.plugins.vv_vh_g_factor import VvVhGFactorCalculator

        widget = VvVhGFactorCalculator()
        qtbot.addWidget(widget)
        assert widget is not None

    def test_window_title(self, qapp, qtbot):
        pytest.importorskip("pyqtgraph")
        from chisurf.plugins.vv_vh_g_factor import VvVhGFactorCalculator

        widget = VvVhGFactorCalculator()
        qtbot.addWidget(widget)
        assert widget.windowTitle() == "VV/VH G-Factor Calculator"
