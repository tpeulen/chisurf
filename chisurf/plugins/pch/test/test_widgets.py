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


class TestPCHMessages:
    """The tool's preconditions are declared conditions, not modal boxes.

    Each of these used to raise a `QMessageBox` that said the thing once and
    left nothing behind, so the tool looked ready while still being unusable —
    and the only way to test it was to intercept a dialog.
    """

    def test_compute_without_a_file_states_the_condition(self, qapp):
        from chisurf.plugins.pch.gui.tool import PCHApp

        widget = PCHApp()
        widget._on_compute()
        assert widget.Error.no_file.is_shown
        assert widget.Error.no_file.text == "Load a TTTR file first."

    def test_fit_and_save_without_a_histogram(self, qapp):
        from chisurf.plugins.pch.gui.tool import PCHApp

        widget = PCHApp()
        widget._on_fit()
        assert widget.Error.no_histogram.is_shown
        widget.Error.no_histogram.clear()
        widget._on_save()
        assert widget.Error.no_histogram.is_shown

    def test_the_condition_is_retracted_once_it_is_met(self, qapp):
        from chisurf.plugins.pch.gui.tool import PCHApp

        widget = PCHApp()
        widget._on_compute()
        assert widget.Error.no_file.is_shown
        widget._filename = "some.ptu"
        widget._on_compute()          # fails later, but not on the precondition
        assert not widget.Error.no_file.is_shown

    def test_every_condition_is_declared(self, qapp):
        from chisurf.plugins.pch.gui.tool import PCHApp

        widget = PCHApp()
        declared = {m.name for m in widget.Error.messages}
        assert declared == {
            "no_file",
            "no_histogram",
            "load_failed",
            "compute_failed",
            "fit_failed",
            "save_failed",
        }
