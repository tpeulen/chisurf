class TestVvVhAnisotropyCalculator:
    def test_creation(self, qapp, qtbot):
        from chisurf.plugins.vv_vh_anisotropy import VvVhAnisotropyCalculator

        widget = VvVhAnisotropyCalculator()
        qtbot.addWidget(widget)
        assert widget is not None

    def test_window_title(self, qapp, qtbot):
        from chisurf.plugins.vv_vh_anisotropy import VvVhAnisotropyCalculator

        widget = VvVhAnisotropyCalculator()
        qtbot.addWidget(widget)
        assert "VV/VH" in widget.windowTitle()
