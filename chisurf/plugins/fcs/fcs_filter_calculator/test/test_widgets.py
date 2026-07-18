import numpy as np
from qtpy import QtCore, QtWidgets


def test_fcs_filter_calculator_widget(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget
    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert "Filter Calculator" in widget.windowTitle()
    assert widget.lw_species.count() == 2
    assert widget._total_vector is not None
    assert np.all(widget._total_vector == np.floor(widget._total_vector))
    assert abs(widget._total_vector.sum() - 100_000) < 2_000
    assert widget.le_total.text().startswith("Convolved example")
    assert widget.options_model.scatter_irf is True
    detector_names = widget.detector_selection.get_selected() or ["default"]
    assert len(widget._total_vectors_by_detector) == len(detector_names)
    assert set(widget._synthetic_scatter_fits) == set(detector_names)
    assert widget._result is not None or widget._result_multi_detector
    assert not hasattr(widget, "tabs")
    assert isinstance(widget.toolbar, QtWidgets.QToolBar)


def test_preloaded_patterns_are_convolved_per_detector(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.detector_selection.refresh(["green", "red"])
    widget.lw_species.clear()
    widget._populate_example_project()

    totals = list(widget._total_vectors_by_detector.values())
    fast_source = widget.lw_species.item(0).data(QtCore.Qt.UserRole)
    assert not np.array_equal(totals[0], totals[1])
    assert not np.allclose(
        fast_source["patterns_by_detector"]["green"],
        fast_source["patterns_by_detector"]["red"],
    )
    assert set(widget._synthetic_scatter_fits) >= {"green", "red"}


def test_calculator_uses_chisurf_docks(qapp, qtbot):
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.widgets.dock_area import DockArea
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget.dock_area, DockArea)
    assert len(widget.dock_area._all_widgets) == 5
    assert widget.dock_area._all_widgets.index(
        widget.plot_residuals
    ) < widget.dock_area._all_widgets.index(widget.plot_recon)
    assert isinstance(widget.btn_unmix, QtWidgets.QToolButton)
    assert isinstance(widget.options_form, AutoForm)
    assert widget.action_load_total.text() == "📂 Mixed…"
    assert "measured mixed decay" in widget.action_load_total.toolTip()
    assert "measured component decay histograms" in widget.action_add_species.toolTip()


def test_plot_colors_are_stable_when_components_are_toggled(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    slow_color_before = widget._component_color(1)
    widget.lw_species.item(0).setCheckState(QtCore.Qt.Unchecked)
    slow_color_after = widget._component_color(0)

    assert slow_color_after == slow_color_before
    assert widget._stable_plot_color("green") == "#4ade80"
    assert widget._stable_plot_color("red") == "#fb4d4d"


def test_example_mixture_survives_project_roundtrip(qapp, qtbot, tmp_path, monkeypatch):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    project = tmp_path / "example.json"
    source = FcsFilterCalculatorWidget()
    qtbot.addWidget(source)
    expected = source._total_vector.copy()
    irf_path = tmp_path / "scatter_irf.txt"
    np.savetxt(irf_path, [0.0, 1.0, 0.5])
    source.options_model.scatter_irf = True
    det = (source.detector_selection.get_selected() or ["green"])[0]
    source.detector_selection._irf[(det, "")] = str(irf_path)
    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getSaveFileName", lambda *a, **k: (str(project), "")
    )
    source._on_save_project()

    restored = FcsFilterCalculatorWidget()
    qtbot.addWidget(restored)
    restored._total_vector = None
    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getOpenFileName", lambda *a, **k: (str(project), "")
    )
    restored._on_load_project()

    assert np.allclose(restored._total_vector, expected)
    assert restored.lw_species.count() == 2
    assert restored.options_model.fit_background is True
    assert restored.options_model.scatter_irf is True
    assert restored.detector_selection.irf_path(det) == str(irf_path)
    assert set(restored._total_vectors_by_detector) == set(source._total_vectors_by_detector)


def test_no_embedded_detector_editor_uses_setup_selector(qapp, qtbot):
    """The embedded detector wizard is gone; the widget only *selects* saved
    setups (the authoritative editor is the toolbox's Detector Def tool)."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    assert widget.detector_wizard_page is None
    # Uses the shared compact SetupSelector, not a hand-rolled combo.
    from chisurf.gui.widgets.setup_selector import SetupSelector

    assert isinstance(widget.setup_selector, SetupSelector)


def test_widget_unmixes_total_with_synthetic_components(qapp, qtbot, tmp_path):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay

    fast = synthetic_decay(128, 1.0, bin_width=0.1)
    slow = synthetic_decay(128, 4.0, bin_width=0.1)
    total = 7500.0 * fast + 2500.0 * slow
    total_path = tmp_path / "mixed_decay.txt"
    np.savetxt(total_path, total)

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget._set_total_paths([total_path])
    widget.lw_species.clear()
    widget.lw_species.add_synthetic("fast", 1.0, 0.1)
    widget.lw_species.add_synthetic("slow", 4.0, 0.1)
    widget._unmix_total()

    assert widget._unmix_result is not None
    assert np.allclose(widget._unmix_result.fractions, [0.75, 0.25])
    if widget._result is not None:
        results = [widget._result]
    else:
        results = [entry["result"] for entry in widget._result_multi_detector]
    assert results
    assert all("unmixing" in result.metadata for result in results)
    assert hasattr(widget, "btn_add_synthetic")
    assert hasattr(widget, "btn_unmix")


def test_widget_adds_irf_scatter_as_hidden_nuisance_filter(qapp, qtbot, tmp_path):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    irf_path = tmp_path / "irf.txt"
    x = np.arange(256, dtype=float)
    np.savetxt(irf_path, np.exp(-0.5 * ((x - 12.0) / 2.0) ** 2))

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    # Load a measured IRF for the first detector only (the rest stay synthetic).
    det0 = (widget.detector_selection.get_selected() or ["green"])[0]
    widget.detector_selection._irf[(det0, "")] = str(irf_path)
    widget.options_model.scatter_irf = True
    widget._compute_filters()

    results = (
        [widget._result]
        if widget._result is not None
        else [entry["result"] for entry in widget._result_multi_detector]
    )
    assert results
    assert all(result.n_filters == result.n_species + 2 for result in results)
    assert all(result.nuisance_labels[0] == "Afterpulse / constant" for result in results)
    assert all(result.nuisance_labels[1].startswith("Scatter / IRF (") for result in results)
    assert results[0].nuisance_labels[1].endswith(", measured)")
    assert all(
        result.nuisance_labels[1].endswith(", fitted)") for result in results[1:]
    )
    assert all(result.to_channel_filters().shape[0] == result.n_species for result in results)


def test_synthetic_dialog_uses_editable_lifetime_spectrum_table(qapp, qtbot, monkeypatch):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)

    def accept_dialog(dialog):
        table = dialog.findChild(QtWidgets.QTableWidget)
        assert table is not None
        assert table.horizontalHeaderItem(0).text() == "Amplitude"
        assert table.horizontalHeaderItem(1).text() == "Lifetime (ns)"
        assert any(
            button.text().startswith("Read from Fit")
            for button in dialog.findChildren(QtWidgets.QToolButton)
        )
        return QtWidgets.QDialog.Accepted

    monkeypatch.setattr(QtWidgets.QDialog, "exec_", accept_dialog)
    widget._add_synthetic_dialog()

    source = widget.lw_species.item(widget.lw_species.count() - 1).data(QtCore.Qt.UserRole)
    assert source["model"] == "lifetime_spectrum"
    assert source["amplitudes"] == [1.0, 1.0]
    assert source["lifetimes"] == [1.0, 4.0]
    assert source["shot_noise"] is False
    assert source["photon_count"] == 100_000


def test_fit_pattern_source_selects_detector_specific_snapshot(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.lw_species.clear()
    widget.lw_species.add_synthetic_source({
        "type": "synthetic",
        "model": "lifetime_spectrum",
        "name": "fit component",
        "amplitudes": [1.0],
        "lifetimes": [3.0],
        "bin_width": 0.1,
        "patterns_by_detector": {
            "green": [4.0, 2.0, 1.0],
            "red": [1.0, 0.5, 0.25],
            "__default__": [4.0, 2.0, 1.0],
        },
    })
    item = widget.lw_species.item(0)

    green, _ = widget._species_item_pattern(item, 3, ["green"])
    red, _ = widget._species_item_pattern(item, 3, ["red"])

    assert np.allclose(green, [4.0, 2.0, 1.0])
    assert np.allclose(red, [1.0, 0.5, 0.25])


def test_read_from_fit_populates_spectrum_and_model_patterns(qapp, qtbot, monkeypatch):
    from types import SimpleNamespace

    import chisurf as cs
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    class FitModel:
        lifetime_spectrum = np.array([0.2, 1.5, 0.8, 4.2])

        def __init__(self):
            self.y = np.ones(32)

        def update_model(self, lifetime_spectrum=None):
            spectrum = np.asarray(lifetime_spectrum, dtype=float)
            time = np.arange(32) * 0.05
            self.y = sum(
                amplitude * np.exp(-time / lifetime)
                for amplitude, lifetime in zip(spectrum[0::2], spectrum[1::2])
            )

    fit = SimpleNamespace(
        name="Gaussian-distance FRET fit",
        model=FitModel(),
        data=SimpleNamespace(name="green"),
    )
    monkeypatch.setattr(cs, "fits", [fit])
    monkeypatch.setattr(cs, "current_fit", fit, raising=False)
    monkeypatch.setattr(
        QtWidgets.QInputDialog,
        "getItem",
        lambda *args, **kwargs: ("Gaussian-distance FRET fit", True),
    )

    def import_and_accept(dialog):
        next(
            button for button in dialog.findChildren(QtWidgets.QToolButton)
            if button.text().startswith("Read from Fit")
        ).click()
        return QtWidgets.QDialog.Accepted

    monkeypatch.setattr(QtWidgets.QDialog, "exec_", import_and_accept)
    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget._add_synthetic_dialog()

    source = widget.lw_species.item(widget.lw_species.count() - 1).data(QtCore.Qt.UserRole)
    assert source["lifetimes"] == [1.5, 4.2]
    assert source["amplitudes"] == [0.2, 0.8]
    assert source["source_fit"] == "Gaussian-distance FRET fit"
    assert "patterns_by_detector" in source
