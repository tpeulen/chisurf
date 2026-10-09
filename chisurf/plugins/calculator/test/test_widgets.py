class TestFRETCalculator:
    def test_creation(self, qapp):
        from chisurf.plugins.calculator.fret_calculator import FretCalculatorTool

        widget = FretCalculatorTool()
        assert widget is not None
        # two calculator tabs, the hetero one carrying the donor lifetime in ns
        assert widget.tabs.count() == 2
        assert widget._hetero_model.tau0 == 4.0
        # the tab computed once at construction: a real efficiency is on screen
        assert 0.0 < widget._hetero_model.E < 1.0


class TestHomoFRETCalculator:
    def test_creation(self, qapp):
        from chisurf.plugins.calculator.fret_calculator import FretCalculatorTool

        widget = FretCalculatorTool()
        assert widget is not None
        # the homo-FRET tab lives inside the same tool, and its k_homo -- an
        # output, read-only under Qt -- is computed at construction
        assert widget._homo_model.k_homo > 0.0
