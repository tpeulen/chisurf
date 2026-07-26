class TestPCHApp:
    def test_creation(self, qapp):
        from chisurf.plugins.pch.gui.tool import PCHApp
        widget = PCHApp()
        assert widget is not None

    def test_window_title(self, qapp):
        from chisurf.plugins.pch.gui.tool import PCHApp
        widget = PCHApp()
        assert "PCH" in widget.windowTitle()

    def test_fit_plot_and_results_text(self, qapp):
        """Drawing the fit and scoring it must not raise (RF-208).

        `_plot_fit` and `_update_results_text` both use ``np`` at module scope;
        with numpy imported only inside `_save_outputs` they raised
        ``NameError`` — swallowed into an error dialog by `_on_fit` and silently
        by the region-drag handler, so the model curve and the results box
        stayed empty after every fit.
        """
        from chisurf.plugins.pch.api.models import FitResult, PchResult
        from chisurf.plugins.pch.gui.tool import PCHApp

        widget = PCHApp()
        widget._result = PchResult(
            k_vals=[0, 1, 2, 3],
            p_exp=[0.4, 0.3, 0.2, 0.1],
            hist_counts=[40, 30, 20, 10],
            total_bins=100,
            trace_t=[0.0, 1.0],
            trace_counts=[1.0, 2.0],
        )
        widget._fit_result = FitResult(
            epsilons=[2.0],
            avg_Ns=[3.0],
            fractions=[100.0],
            chi2=1.0,
            reduced_chi2=0.5,
            dof=2,
            fit_low=0,
            fit_high=3,
            p_fit=[0.41, 0.29, 0.21, 0.09],
            n_components=1,
        )
        widget.region.set_bounds(0, 3)

        widget._plot_fit()
        widget._update_results_text()

        text = widget.results_edit.toPlainText()
        assert "Comp1:" in text
        assert "red." in text
