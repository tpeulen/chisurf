class TestKappa2Dist:
    def test_creation(self):
        from chisurf.plugins.calculator.kappa2_dist.gui.app import make_app

        app = make_app()
        assert app is not None

    def test_creation_with_kappa2(self):
        from chisurf.plugins.calculator.kappa2_dist.gui.app import make_app

        app = make_app(kappa2=0.667)
        assert app.tool._model.kappa2_true == 0.667
