"""The FRET calculator's native app builds with computed defaults (the Qt tool tests, ported)."""


class TestFRETCalculator:
    def test_creation(self):
        from chisurf.plugins.calculator.fret_calculator.gui.app import make_app

        app = make_app(restore=False)
        # the hetero tab carries the donor lifetime in ns
        assert app.model.hetero.tau0 == 4.0
        # the tab computed once at construction: a real efficiency is on screen
        assert 0.0 < app.model.hetero.E < 1.0


class TestHomoFRETCalculator:
    def test_creation(self):
        from chisurf.plugins.calculator.fret_calculator.gui.app import make_app

        app = make_app(restore=False)
        # the homo-FRET tab lives inside the same app; k_homo, an output, is computed at construction
        assert app.model.homo.k_homo > 0.0
