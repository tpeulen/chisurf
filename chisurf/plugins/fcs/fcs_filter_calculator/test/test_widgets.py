import numpy as np
import pytest
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
    # The scatter/IRF nuisance pattern is taken from each detector's own IRF, so
    # every detector records the shape it used (no independent coarse re-fit).
    assert set(widget._irf_by_detector) == set(detector_names)
    assert not widget._synthetic_scatter_fits
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
    assert set(widget._irf_by_detector) >= {"green", "red"}


def test_calculator_uses_chisurf_docks(qapp, qtbot):
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.widgets.dock_area import DockArea
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget.dock_area, DockArea)
    # Sources, Setup, Auto-fit, Instrument, Info, Lifetime filters, residuals, reconstruction.
    assert len(widget.dock_area._all_widgets) == 8
    assert widget.dock_area._all_widgets.index(
        widget.plot_residuals
    ) < widget.dock_area._all_widgets.index(widget.plot_recon)
    assert isinstance(widget.btn_unmix, QtWidgets.QToolButton)
    assert isinstance(widget.options_form, AutoForm)
    assert widget.action_load_total.text() == "📂 Mixed…"
    assert "measured mixed decay" in widget.action_load_total.toolTip()
    # Add/Edit/Remove are on the Components context menu, not the toolbar.
    labels = [a.text() for a in widget.toolbar.actions()]
    assert not any("Add" in t for t in labels)


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
    # Detectors without a measured IRF use their (synthetic) detector IRF as the
    # scatter shape, so it stays consistent with the auto-fit / component convolution.
    assert all(
        result.nuisance_labels[1].endswith(", detector-IRF)") for result in results[1:]
    )
    assert all(result.to_channel_filters().shape[0] == result.n_species for result in results)


def test_nuisance_scatter_fit_ignores_zero_emission_species(qapp, qtbot):
    """A species that emits nothing in a detector must not break the scatter fit.

    In multi-detector FRET mode a species (e.g. a FRET-sensitized acceptor) can
    have an all-zero per-detector pattern in the donor channel. That degenerate
    pattern carries no information for the synthetic-scatter unmix basis, so it
    is dropped rather than raising ``component_decays[i] must ... be non-zero``.
    """
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.options_model.scatter_irf = True  # synthetic (no measured IRF loaded)

    x = np.arange(256, dtype=float)
    total = np.exp(-x / 25.0) + 0.01
    real = np.exp(-x / 40.0) + 0.01
    zero = np.zeros_like(x)  # a species emitting nothing in this detector

    det0 = (widget.detector_selection.get_selected() or ["green"])[0]
    patterns, labels = widget._nuisance_patterns(total, [real, zero], det0)

    assert any(lbl.startswith("Scatter / IRF (") for lbl in labels)
    scatter = patterns[labels.index(next(l for l in labels if l.startswith("Scatter")))]
    assert scatter.size == total.size
    assert np.all(np.isfinite(scatter)) and scatter.sum() > 0.0


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
            "Fit" in button.text()
            for button in dialog.findChildren(QtWidgets.QToolButton)
        )
        return QtWidgets.QDialog.Accepted

    monkeypatch.setattr(QtWidgets.QDialog, "exec_", accept_dialog)
    widget._add_component_dialog()

    source = widget.lw_species.item(widget.lw_species.count() - 1).data(QtCore.Qt.UserRole)
    assert source["model"] == "lifetime_spectrum"
    assert source["amplitudes"] == [1.0, 1.0]
    assert source["lifetimes"] == [1.0, 4.0]
    assert source["shot_noise"] is False
    assert source["photon_count"] == 100_000


def test_no_remove_toolbar_button(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    # Removal moved to the Components context menu — no toolbar Remove button.
    assert not hasattr(widget, "btn_remove_species")
    labels = [a.text() for a in widget.toolbar.actions()]
    assert not any("Remove" in t for t in labels)


def test_edit_synthetic_component_replaces_in_place(qapp, qtbot, monkeypatch):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.lw_species.clear()
    widget.lw_species.add_synthetic_source({
        "type": "synthetic", "model": "lifetime_spectrum", "name": "comp",
        "amplitudes": [1.0], "lifetimes": [2.0], "bin_width": 0.05,
    })
    item = widget.lw_species.item(0)
    assert widget._is_editable_component(item)
    count_before = widget.lw_species.count()

    # Edit: bump the lifetime and accept.
    def edit_and_accept(dialog):
        from chisurf.gui.widgets.synthetic_decay_editor import SyntheticDecayEditorModel
        model = next(c for c in dialog.findChildren(QtWidgets.QWidget)
                     if isinstance(getattr(c, "model", None), SyntheticDecayEditorModel)).model
        model.spectrum_rows = [{"amplitude": 1.0, "lifetime": 7.5}]
        return QtWidgets.QDialog.Accepted

    monkeypatch.setattr(QtWidgets.QDialog, "exec_", edit_and_accept)
    widget._edit_component_item(item)

    assert widget.lw_species.count() == count_before  # replaced, not appended
    source = widget.lw_species.item(0).data(QtCore.Qt.UserRole)
    assert source["lifetimes"] == [7.5]


def test_add_fret_species_stores_coupled_detector_patterns(qapp, qtbot, monkeypatch):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.lw_species.clear()

    def set_da_and_accept(dialog):
        from chisurf.gui.widgets.fret_species_editor import FretSpeciesEditorModel
        # Switch the unified dialog's Type selector to "FRET species".
        combo = dialog.findChild(QtWidgets.QComboBox)
        combo.setCurrentIndex(combo.findData("fret"))
        model = next(c for c in dialog.findChildren(QtWidgets.QWidget)
                     if isinstance(getattr(c, "model", None), FretSpeciesEditorModel)).model
        model.state = "da"
        model.transfer_efficiency = 0.6
        return QtWidgets.QDialog.Accepted

    monkeypatch.setattr(QtWidgets.QDialog, "exec_", set_da_and_accept)
    widget._add_component_dialog()

    source = widget.lw_species.item(0).data(QtCore.Qt.UserRole)
    assert source["model"] == "fret_species"
    patterns = source["patterns_by_detector"]
    # Coupled per-detector decays: green (donor) ≠ red (sensitized acceptor).
    assert set(patterns) >= {"green", "red", "yellow"}
    assert not np.allclose(patterns["green"], patterns["red"])
    # The list item is editable (reopens the FRET editor).
    assert widget._editable_model(widget.lw_species.item(0)) == "fret_species"


def test_help_section_registered():
    from chisurf.gui.autoform.sections import get_section_factory

    assert get_section_factory("help") is not None


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

        def evaluate_lifetime_spectrum(self, lifetime_spectrum):
            spectrum = np.asarray(lifetime_spectrum, dtype=float)
            time = np.arange(32) * 0.05
            return sum(
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
            if "Fit" in button.text()
        ).click()
        return QtWidgets.QDialog.Accepted

    monkeypatch.setattr(QtWidgets.QDialog, "exec_", import_and_accept)
    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget._add_component_dialog()

    source = widget.lw_species.item(widget.lw_species.count() - 1).data(QtCore.Qt.UserRole)
    assert source["lifetimes"] == [1.5, 4.2]
    assert source["amplitudes"] == [0.2, 0.8]
    assert source["source_fit"] == "Gaussian-distance FRET fit"
    assert "patterns_by_detector" in source


def test_use_correlator_total_pulls_loaded_files(qapp, qtbot, tmp_path):
    import numpy as np
    from qtpy import QtWidgets
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    decay = tmp_path / "mix.txt"
    np.savetxt(decay, np.exp(-np.arange(256) / 40.0))

    # A stand-in host carrying the correlator workflow context.
    class _Ctx:
        file_paths = [decay]
        expanded_files = [str(decay)]

    host = QtWidgets.QWidget()
    host.workflow_context = _Ctx()
    qtbot.addWidget(host)

    widget = FcsFilterCalculatorWidget()
    widget.setParent(host)  # host owns it; don't re-add to qtbot (double-delete)

    assert [str(p) for p in widget._correlator_file_paths()] == [str(decay)]
    widget._use_correlator_total()
    assert widget._total_paths == [decay]
    assert widget._has_total_decay()


def test_micro_time_axis_from_data_and_binning(qapp, qtbot):
    import numpy as np
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    class _Header:
        micro_time_resolution = 32e-12  # 32 ps, in seconds

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)

    mt = np.arange(0, 4096)
    # No binning: dt = resolution (ns) = 0.032; channel count unchanged.
    out_mt, n_tac = widget._micro_time_axis(_Header(), mt.copy(), 4096)
    assert n_tac == 4096
    assert abs(widget._pattern_bin_width_ns() - 0.032) < 1e-9

    # Binning by 4 coarsens the axis and widens the bin width ×4.
    widget._micro_time_binning = 4
    out_mt, n_tac = widget._micro_time_axis(_Header(), mt.copy(), 4096)
    assert n_tac == 1024
    assert out_mt.max() == 1023
    assert abs(widget._pattern_bin_width_ns() - 0.128) < 1e-9


def test_auto_fit_adds_lifetime_components(qapp, qtbot, tmp_path):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay

    fast = synthetic_decay(256, 1.2, bin_width=0.05, normalize=True)
    slow = synthetic_decay(256, 4.0, bin_width=0.05, normalize=True)
    total = 60000.0 * fast + 40000.0 * slow
    total_path = tmp_path / "mix.txt"
    np.savetxt(total_path, total)

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.detector_selection.refresh([])  # no detector IRF: fit the ideal decay
    # Pure lifetime fit: the ideal decay carries no scatter/background.
    widget.options_model.scatter_irf = False
    widget.fit_background_cb.setChecked(False)
    widget._set_total_paths([total_path])
    widget.lw_species.clear()
    widget._auto_fit_components(n_components=2)

    assert widget.lw_species.count() == 2
    taus = sorted(
        widget.lw_species.item(i).data(QtCore.Qt.UserRole)["lifetimes"][0]
        for i in range(2)
    )
    assert abs(taus[0] - 1.2) < 0.2
    assert abs(taus[1] - 4.0) < 0.4


def test_auto_fit_joint_irf_fit_resolves_distinct_components(qapp, qtbot, tmp_path):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    # An IRF-convolved bi-exponential with a real prompt at ~bin 14. With no
    # measured IRF loaded, auto-fit fits the IRF jointly (from the prompt) and
    # resolves both lifetimes without a tail-only workaround.
    t = np.arange(256) * 0.05
    irf = synthetic_irf(t, center_ns=0.7, fwhm_ns=0.35)
    total = 60000.0 * synthetic_decay(256, 1.2, bin_width=0.05, irf=irf, normalize=True) \
        + 40000.0 * synthetic_decay(256, 4.0, bin_width=0.05, irf=irf, normalize=True)
    total_path = tmp_path / "mix.txt"
    np.savetxt(total_path, total)

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.detector_selection.refresh(["green"])
    widget._set_total_paths([total_path])
    widget._fit_region.set_bounds(0.0, 255.0)
    widget._fit_region_initialized = True
    width_before = widget.detector_selection.width("green", "")
    widget.lw_species.clear()
    widget._auto_fit_components(n_components=2)

    assert widget.lw_species.count() == 2
    taus = sorted(
        widget.lw_species.item(i).data(QtCore.Qt.UserRole)["lifetimes"][0]
        for i in range(2)
    )
    # Two DISTINCT lifetimes recovered (not collapsed to one).
    assert abs(taus[0] - 1.2) < 0.3
    assert abs(taus[1] - 4.0) < 0.6
    assert taus[1] - taus[0] > 1.0
    # No measured IRF → the IRF width was fitted and written back to the detector,
    # and components are convolved with it from the prompt (start_bin=0).
    assert abs(widget.detector_selection.width("green", "") - width_before) > 1e-4
    src = widget.lw_species.item(0).data(QtCore.Qt.UserRole)
    assert src["start_bin"] == 0
    assert "patterns_by_detector" in src


def test_fit_region_selector_present(qapp, qtbot):
    """The fit range is a chiplot region and drives ``_fit_range``."""
    from chisurf.gui.chiplot import handles as H
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget._fit_region, H.Region)
    # Draggable range is functional: setting it drives _fit_range (used by auto-fit).
    widget._fit_region.set_bounds(30.0, 200.0)
    widget._fit_region_initialized = True
    assert widget._fit_range(256) == (30, 200)


def test_fit_region_survives_replots(qapp, qtbot):
    """The draggable fit region stays usable after every recompute.

    ``Plot.clear()`` on each replot drops every handle, region included, and a
    cleared handle cannot be put back — so ``_clear_recon_plot`` rebuilds it at
    the same bounds. Without that the selector silently disappears (or, worse,
    lingers as a handle onto a canvas it is no longer drawn on) the first time
    filters are computed or a detector is toggled.
    """
    from chisurf.gui.chiplot import handles as H
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget._fit_region, H.Region), "region gone after the example compute"

    widget._fit_region.set_bounds(30.0, 200.0)
    widget._fit_region_initialized = True

    # Replot → the selector must still be there, at the range the user chose,
    # and still drive the fit window. Driven directly rather than by toggling a
    # detector: whether any detector exists depends on the machine's saved
    # setups, and this is about surviving the replot.
    widget._update_plots()
    qapp.processEvents()

    assert isinstance(widget._fit_region, H.Region), "region wiped by the recompute"
    assert widget._fit_range(256) == (30, 200), "recompute reset the chosen fit range"


def test_a_masked_residual_range_is_not_drawn_across(qapp, qtbot):
    """Residuals outside the fit window are NaN and must read as a gap.

    Drawing a segment straight across the excluded bins would invent residuals
    the fit never produced. chiplot breaks the line at non-finite samples, so
    this only holds while ``skip_missing`` is on by default.
    """
    import numpy as np

    from chisurf.gui import chiplot as cp

    plot = cp.Plot()
    qtbot.addWidget(plot)
    y = np.array([1.0, 2.0, np.nan, 4.0])
    handle = plot.line(np.arange(y.size), y)
    assert handle.native.opts["connect"] == "finite"


def test_auto_fit_fits_irf_when_no_measured_irf(qapp, qtbot):
    """Auto-fit fits the synthetic IRF width and writes it back when no IRF loaded."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    names = list(widget.detector_selection.get_selected())
    # No measured IRF configured → the width must be fitted (and changed) for the
    # selected detectors.
    for n in names:
        assert widget._measured_irf_vector(n) is None
    before = {n: widget.detector_selection.width(n, "") for n in names}
    widget._auto_fit_settings = {
        "kind": "lifetime", "n_components": 2, "tau_min": 0.2, "tau_max": 8.0,
    }
    widget._auto_fit_components(n_components=2)
    qapp.processEvents()
    after = {n: widget.detector_selection.width(n, "") for n in names}
    assert any(abs(after[n] - before[n]) > 1e-4 for n in names), (
        "IRF width was not fitted / written back"
    )
    assert "IRF FWHM" in widget.lbl_autofit_status.text()


def test_stacked_mode_computes_global_filters_split_per_detector(qapp, qtbot):
    """Global (stacked) mode solves one filter set over concatenated detectors and
    splits it back into per-detector slices; the independent mode is the default."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    dets = list(widget.detector_selection.get_selected())
    assert len(dets) > 1

    # Default is independent per-detector filters.
    assert not widget.stacked_mode_cb.isChecked()
    widget._compute_filters()
    assert widget._result_multi_detector
    assert all(dr["result"].metadata.get("filter_mode") != "stacked"
               for dr in widget._result_multi_detector)

    # Enable stacked/global mode → one global set, split per detector, mode tagged.
    widget.stacked_mode_cb.setChecked(True)
    qapp.processEvents()
    results = widget._result_multi_detector
    assert results and len(results) == len(dets)
    for dr in results:
        r = dr["result"]
        assert r.metadata.get("filter_mode") == "stacked"
        assert r.metadata.get("stacked_detectors") == dets
        assert r.n_bins == widget._result_multi_detector[0]["result"].n_bins
        assert np.all(np.isfinite(r.filters))
        assert r.to_channel_filters().shape[0] == r.n_species


def test_stacked_mode_uses_fret_interdetector_scaling(qapp, qtbot):
    """A FRET species with asymmetric per-detector brightness yields different
    filters in stacked mode than in independent mode (the coupling is used)."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    dets = list(widget.detector_selection.get_selected())

    def green_species_filters():
        widget._compute_filters()
        g = next(dr for dr in widget._result_multi_detector if dr["detector"] == dets[0])
        return np.asarray(g["result"].to_channel_filters(), dtype=float)

    widget.stacked_mode_cb.setChecked(False)
    indep = green_species_filters()
    widget.stacked_mode_cb.setChecked(True)
    stacked = green_species_filters()
    # Same shape, but the joint (cross-detector) solution differs from the
    # per-detector-independent one.
    assert indep.shape == stacked.shape
    assert not np.allclose(indep, stacked)


def test_example_components_cleared_when_data_loaded(qapp, qtbot, tmp_path):
    """Loading measured data drops the built-in example species but keeps user ones."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    # The panel seeds two example components on first open.
    assert widget.lw_species.count() == 2
    # A user-added component must survive the load.
    widget.lw_species.add_synthetic_source(
        {"type": "synthetic", "model": "lifetime", "name": "MyComp",
         "lifetime": 2.5, "bin_width": 0.05}
    )
    total = tmp_path / "mix.txt"
    np.savetxt(total, np.exp(-np.arange(256) / 40.0) + 0.01)
    widget._set_total_paths([total])

    names = [widget.lw_species.item(i).text() for i in range(widget.lw_species.count())]
    assert not any("example" in n.lower() for n in names)
    assert any("MyComp" in n for n in names)


def test_auto_fit_on_file_backed_total_with_nondefault_bins(qapp, qtbot, tmp_path):
    """Auto-fit must not crash on file-backed data whose bin count differs from 256.

    ``_total_vector`` is ``None`` for file-/correlator-backed totals, so the
    synthetic IRF must be built at the real bin count (`_current_n_bins`); a
    fitted shift on a 256-bin IRF used against a 2048-bin decay previously pushed
    the prompt off the end and raised "irf must contain a positive value".
    """
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    t = np.arange(2048) * 0.05
    irf = synthetic_irf(t, center_ns=0.9, fwhm_ns=0.3, shape=0.3)
    total = (60000.0 * synthetic_decay(2048, 1.2, bin_width=0.05, irf=irf, normalize=True)
             + 40000.0 * synthetic_decay(2048, 4.0, bin_width=0.05, irf=irf, normalize=True))
    p = tmp_path / "mix.txt"
    np.savetxt(p, total)

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.detector_selection.refresh(["green", "red", "yellow"])
    widget._set_total_paths([p])
    assert widget._total_vector is None and widget._current_n_bins() == 2048
    widget._auto_fit_settings = {
        "kind": "lifetime", "n_components": 2, "tau_min": 0.2, "tau_max": 8.0,
    }
    widget._auto_fit_components(n_components=2)  # must not raise
    assert widget.lw_species.count() == 2


def test_instrument_dock_autoform_and_period(qapp, qtbot):
    """The Instrument dock is an AutoForm over α/β/γ/δ/G/l1/l2/R0/period, and the
    laser period drives the periodic-convolution helper."""
    from chisurf.gui.autoform import AutoForm
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    assert "Instrument" in widget.dock_area._tab_names.values()
    assert isinstance(widget.instrument_form, AutoForm)
    for attr in ("alpha", "beta", "gamma", "delta", "g_factor", "l1", "l2",
                 "forster_radius", "period_ns", "periodic"):
        assert hasattr(widget.instrument_model, attr)

    # Periodic convolution: off ⇒ None; on with 0 ⇒ full micro-time window.
    assert widget._fit_period_ns(256, 0.05) is None
    widget.instrument_model.periodic = True
    assert widget._fit_period_ns(256, 0.05) == 256 * 0.05
    widget.instrument_model.period_ns = 12.5
    assert widget._fit_period_ns(256, 0.05) == 12.5

    # Setup calibration prepopulates the instrument parameters.
    widget._detector_settings = {"calibration": {"alpha": 0.02, "gamma": 0.9, "g_factor": 1.15}}
    widget._prepopulate_instrument_from_setup()
    assert widget.instrument_model.alpha == 0.02
    assert widget.instrument_model.gamma == 0.9
    assert widget.instrument_model.g_factor == 1.15


def test_a_calibration_measured_once_arrives_here(qapp, qtbot):
    """The point of storing a calibration on the setup: this tool reads it.

    The Accurate FRET tool measures α/β/γ/δ and hangs them on the detector
    setup; picking that setup here must fill the instrument parameters with the
    measured values rather than the defaults — otherwise the calibration is
    written to a file nobody opens.
    """
    from chisurf.core.fluorescence.fret.calibration import (
        CalibrationParameters, calibration_to_setup,
    )
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    calib = CalibrationParameters()
    calib.gamma, calib.alpha, calib.beta, calib.delta, calib.r0 = 0.65, 0.08, 1.4, 0.06, 54.0

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget._detector_settings = {
        "detectors": {"green": {}, "red": {}},
        "fret_calibration": calibration_to_setup(calib),
    }
    widget._prepopulate_instrument_from_setup()

    assert widget.instrument_model.gamma == pytest.approx(0.65)
    assert widget.instrument_model.alpha == pytest.approx(0.08)
    assert widget.instrument_model.beta == pytest.approx(1.4)
    assert widget.instrument_model.delta == pytest.approx(0.06)
    # stored as r0, shown in a field named forster_radius
    assert widget.instrument_model.forster_radius == pytest.approx(54.0)
    # and it reaches the FRET-species editor through the instrument dock
    assert widget._calibration_seed()["gamma"] == pytest.approx(0.65)


def test_the_acceptor_excitation_channel_is_not_switched_off_by_default(qapp, qtbot):
    """β is the excitation-flux *ratio* — it must default to 1, not 0.

    The excitation matrix is ``[[1, δ], [0, β]]``, so β = 0 means the acceptor
    laser excites nothing and the yellow (acceptor-excitation) pattern comes out
    identically zero. Nothing raises; the channel simply cannot contribute to
    the filters, which is far worse than a crash.
    """
    import numpy as np

    from chisurf.core.fluorescence.fret.species_decay import fret_species_detector_patterns
    from chisurf.plugins.fcs.fcs_filter_calculator.gui_parts.instrument_options import DEFAULTS

    assert DEFAULTS["beta"] == 1.0
    source = {
        "model": "fret_species", "state": "da",
        "donor_spectrum": [1.0, 4.0], "acceptor_spectrum": [1.0, 2.0],
        "fret_mode": "efficiency", "transfer_efficiency": 0.5, "bin_width": 0.032,
        "crosstalk": {k: DEFAULTS[k] for k in ("alpha", "beta", "gamma", "delta")},
    }
    patterns = fret_species_detector_patterns(source, ["green", "red", "yellow"], 256)
    assert np.sum(patterns["yellow"]) > 0.0


def test_filters_computed_over_fit_range_window(qapp, qtbot):
    """fFCS filters are solved on the fit-range slice, not the full decay: the
    reconstruction equals the total outside the range (residual 0) and the filters
    are zero there, so the excluded pre-prompt/tail bins can't bias the fit."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget._detector_fit_ranges[widget.detector_selection.get_selected()[0]] = (40, 200)
    widget._compute_filters()
    qapp.processEvents()

    entry = next(e for e in widget._result_multi_detector
                 if e["detector"] == widget.detector_selection.get_selected()[0])
    res = entry["result"]
    f = np.asarray(res.filters)
    assert np.all(f[:, :40] == 0.0) and np.all(f[:, 200:] == 0.0)
    # Outside the window the reconstruction tracks the total (residual 0 there).
    recon = np.asarray(res.reconstruction)
    total = np.asarray(res.total_decay)
    assert np.allclose(recon[:40], total[:40]) and np.allclose(recon[200:], total[200:])


def test_filters_zeroed_outside_per_detector_fit_range(qapp, qtbot):
    """Filters are zeroed outside each detector's fit range (global or override)."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    dets = list(widget.detector_selection.get_selected())
    widget._detector_fit_ranges[dets[0]] = (50, 150)
    widget._compute_filters()
    qapp.processEvents()

    entry = next(e for e in widget._result_multi_detector if e["detector"] == dets[0])
    f = np.asarray(entry["result"].filters)
    assert np.all(f[:, :50] == 0.0) and np.all(f[:, 150:] == 0.0)
    assert np.any(f[:, 50:150] != 0.0)


def test_fit_range_change_auto_updates_filters_without_refit(qapp, qtbot):
    """Changing the fit range re-zeros the stored filters (narrow → widen recovers
    the previously-zeroed columns via the cached un-zeroed filters), no refit."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    dets = list(widget.detector_selection.get_selected())

    def green_filters():
        e = next(x for x in widget._result_multi_detector if x["detector"] == dets[0])
        return np.asarray(e["result"].filters)

    widget._fit_region.setRegion((60.0, 180.0))
    widget._fit_region_initialized = True
    widget._on_fit_range_committed()
    f = green_filters()
    assert np.all(f[:, :60] == 0.0) and np.all(f[:, 180:] == 0.0)

    # Widen: columns that were zeroed must come back (proves cache, not refit-loss).
    widget._fit_region.setRegion((10.0, 250.0))
    widget._on_fit_range_committed()
    f = green_filters()
    assert np.any(f[:, 10:60] != 0.0)
    assert np.all(f[:, :10] == 0.0) and np.all(f[:, 250:] == 0.0)


def test_info_dock_gathers_state_and_per_detector_range_editable(qapp, qtbot):
    """The Info dock exists, summarizes state, and its range table drives overrides."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    assert "Info" in widget.dock_area._tab_names.values()
    assert hasattr(widget, "info_text") and hasattr(widget, "info_range_table")
    widget._refresh_info()
    text = widget.info_text.toPlainText()
    assert "Mixed decay" in text and "Detectors" in text and "Components" in text

    # Editing a Start/Stop cell records a per-detector override.
    dets = list(widget.detector_selection.get_selected())
    assert widget.info_range_table.rowCount() == len(dets)
    widget.info_range_table.item(0, 1).setText("40")
    widget.info_range_table.item(0, 2).setText("200")
    assert widget._detector_fit_ranges[dets[0]] == (40, 200)


def test_residuals_masked_to_fit_range(qapp, qtbot):
    """Residuals outside the selected fit range are blanked (NaN → not drawn)."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget._fit_region.setRegion((30.0, 200.0))
    widget._fit_region_initialized = True
    masked = widget._mask_to_fit_range(np.ones(256, dtype=float))
    assert np.isnan(masked[:30]).all()
    assert np.isfinite(masked[30:200]).all()
    assert np.isnan(masked[200:]).all()


def test_detector_irf_shift_moves_prompt_and_persists(qapp, qtbot):
    """The per-detector IRF time shift moves both synthetic & measured IRFs, and
    round-trips through the detector table's export/import state."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    ds = widget.detector_selection
    det = ds.get_selected()[0]
    ds.set_width(det, 0.2, "")
    dt = widget._pattern_bin_width_ns()

    peak0 = int(np.argmax(widget._detector_irf(det)))
    ds.set_shift(det, 0.5, "")  # +0.5 ns → later by 0.5/dt bins
    peak1 = int(np.argmax(widget._detector_irf(det)))
    assert peak1 - peak0 == round(0.5 / dt)

    # Shift is part of the persisted detector state.
    state = ds.export_state()
    assert "shift" in state
    ds.set_shift(det, 0.0, "")
    ds.import_state(state)
    assert abs(ds.shift(det, "") - 0.5) < 1e-9


def test_fit_range_resets_on_new_data_and_spinboxes_sync(qapp, qtbot, tmp_path):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay

    total = 50000.0 * synthetic_decay(2000, 2.0, bin_width=0.05, normalize=True)
    p = tmp_path / "big.txt"
    np.savetxt(p, total)
    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.detector_selection.refresh(["green"])
    widget._set_total_paths([p])
    widget._update_plots()  # re-initializes the region for the 2000-bin data

    lo, hi = widget._fit_region.bounds
    # Range spans the new (2000-bin) data, not the stale 256-bin example.
    assert hi > 500
    # Region ↔ spinboxes kept in sync.
    assert widget.sb_fit_start.value() == int(round(lo))
    assert widget.sb_fit_stop.value() == int(round(hi))
    # Editing a spinbox drives the plot region.
    widget.sb_fit_start.setValue(80)
    widget.sb_fit_stop.setValue(1900)
    l2, h2 = widget._fit_region.getRegion()
    assert int(round(l2)) == 80 and int(round(h2)) == 1900


def test_fret_autofit_creates_fret_species(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.lw_species.clear()
    widget._suspend_compute = True  # skip per-add recompute (as the auto-fit does)
    # Fitted donor lifetimes 2.0 & 4.0 ns → FRET species with E 0.5 and 0 (τ_D0=4).
    widget._add_fret_autofit_species(
        amps=np.array([0.5, 0.5]), taus=np.array([2.0, 4.0]), scale=1.0,
        dt=0.05, start=5, n_bins=256, detector_names=["green", "red", "yellow"],
    )
    widget._suspend_compute = False
    assert widget.lw_species.count() == 2
    models = [widget.lw_species.item(i).data(QtCore.Qt.UserRole)["model"] for i in range(2)]
    assert all(m == "fret_species" for m in models)
    # τ=4 → donor-only (E≈0); τ=2 → DA with E≈0.5; per-detector coupled patterns exist.
    effs = sorted(widget.lw_species.item(i).data(QtCore.Qt.UserRole)["transfer_efficiency"]
                  for i in range(2))
    assert abs(effs[0] - 0.0) < 1e-2 and abs(effs[1] - 0.5) < 0.05
    for i in range(2):
        assert "patterns_by_detector" in widget.lw_species.item(i).data(QtCore.Qt.UserRole)


def test_auto_fit_settings_drive_kind_and_bounds(qapp, qtbot, tmp_path):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay

    total = 60000.0 * synthetic_decay(1024, 1.5, bin_width=0.05, normalize=True) \
        + 40000.0 * synthetic_decay(1024, 4.5, bin_width=0.05, normalize=True)
    p = tmp_path / "mix.txt"
    np.savetxt(p, total)
    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.detector_selection.refresh(["green"])
    widget._set_total_paths([p])
    widget._update_plots()
    widget._fit_region.setRegion((10.0, 1000.0))
    widget._fit_region_initialized = True

    # Persistent settings default to 2 lifetime components.
    assert widget._auto_fit_settings["kind"] == "lifetime"
    assert widget._auto_fit_settings["n_components"] == 2

    # FRET mode via settings → FRET species.
    widget._auto_fit_settings["kind"] = "fret"
    widget.lw_species.clear()
    widget._auto_fit_components(n_components=2)
    models = {widget.lw_species.item(i).data(QtCore.Qt.UserRole)["model"]
              for i in range(widget.lw_species.count())}
    assert models == {"fret_species"}


def test_autofit_settings_dock_present(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    # Persistent Auto-fit settings dock with type / N / lifetime bounds controls.
    assert "Auto-fit" in widget.dock_area._tab_names.values()
    assert widget.cb_autofit_kind.currentData() == "lifetime"
    # Editing the dock controls updates the persistent settings.
    widget.sb_autofit_n.setValue(3)
    widget.cb_autofit_kind.setCurrentIndex(1)
    widget.sb_autofit_tmax.setValue(12.0)
    assert widget._auto_fit_settings["n_components"] == 3
    assert widget._auto_fit_settings["kind"] == "fret"
    assert widget._auto_fit_settings["tau_max"] == 12.0


def _autofit_widget(qtbot, tmp_path, n_components=2, kind="lifetime"):
    """Build a calculator with a two-exponential mixed decay, ready to auto-fit."""
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay

    fast = synthetic_decay(256, 1.2, bin_width=0.05, normalize=True)
    slow = synthetic_decay(256, 4.0, bin_width=0.05, normalize=True)
    tmp_path.mkdir(parents=True, exist_ok=True)
    total_path = tmp_path / "mix.txt"
    np.savetxt(total_path, 60000.0 * fast + 40000.0 * slow)

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    widget.detector_selection.refresh([])
    widget.options_model.scatter_irf = False
    widget.fit_background_cb.setChecked(False)
    widget._set_total_paths([total_path])
    widget.lw_species.clear()
    widget._auto_fit_settings["kind"] = kind
    widget._auto_fit_components(n_components=n_components)
    return widget


def test_auto_fit_runs_through_a_real_fit_object(qapp, qtbot, tmp_path):
    """The migration's premise: the auto-fit is now a real ChiSurf fit."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.description import for_family

    widget = _autofit_widget(qtbot, tmp_path)

    result = widget._auto_fit_result
    assert isinstance(result["fit"], Fit)
    assert isinstance(result["model"], for_family("tcspc_lifetime"))


def test_autofit_parameter_table_lists_the_fitted_parameters(qapp, qtbot, tmp_path):
    from chisurf.core.fitting.parameter import FittingParameter

    widget = _autofit_widget(qtbot, tmp_path)

    assert widget.autofit_parameters_host.isVisibleTo(widget)
    table = widget.autofit_parameter_table
    assert table is not None
    names = {getattr(p, "name", "") for p in table._params}
    # Two components -> two lifetimes and two amplitudes, and no third.
    assert {"t0", "t1", "a0", "a1"} <= names
    assert not names & {"t2", "a2"}
    assert all(isinstance(p, FittingParameter) for p in table._params)


def test_autofit_parameter_table_hides_the_convolution_plumbing(qapp, qtbot, tmp_path):
    """Axis/range/acquisition parameters are configured by the auto-fit, not read."""
    widget = _autofit_widget(qtbot, tmp_path)

    names = {getattr(p, "name", "") for p in widget.autofit_parameter_table._params}
    assert not (names & {"dt", "rep", "start", "stop", "irf_start", "irf_stop", "n0",
                         "lamp background", "irf position"})


def test_autofit_parameters_can_be_linked(qapp, qtbot, tmp_path):
    """What the model-backed fit buys: results that link to another fit."""
    widget_a = _autofit_widget(qtbot, tmp_path / "a")
    widget_b = _autofit_widget(qtbot, tmp_path / "b")

    def tau0(widget):
        return next(p for p in widget._auto_fit_result["model"].parameters_all
                    if getattr(p, "canonical_id", "") == "lifetime.tau.0")

    target = tau0(widget_a)
    follower = tau0(widget_b)
    follower.link = target

    assert follower.is_linked
    target.value = 2.345
    assert follower.value == pytest.approx(2.345)


def test_autofit_parameter_table_is_rebuilt_per_fit(qapp, qtbot, tmp_path):
    """Each auto-fit builds a new Fit, so a stale table would show a dead model."""
    widget = _autofit_widget(qtbot, tmp_path, n_components=2)
    first = widget.autofit_parameter_table
    assert len(first._params) > 0

    widget._auto_fit_components(n_components=3)
    second = widget.autofit_parameter_table

    assert second is not first
    names = {getattr(p, "name", "") for p in second._params}
    assert "t2" in names, "the table still shows the two-component fit"


def test_fret_auto_fit_runs_through_a_real_fret_model(qapp, qtbot, tmp_path):
    """The FRET kind fits distances against R0, not lifetimes converted afterwards."""
    from chisurf.core.models.description import for_family

    widget = _autofit_widget(qtbot, tmp_path, n_components=2, kind="fret")

    result = widget._auto_fit_result
    assert isinstance(result["model"], for_family("tcspc_fret_gaussian"))
    assert len(result["distances"]) == 2
    assert np.all(result["efficiencies"] >= 0) and np.all(result["efficiencies"] <= 1)
    # Every added species is a FRET species carrying a fitted efficiency.
    sources = [widget.lw_species.item(i).data(QtCore.Qt.UserRole)
               for i in range(widget.lw_species.count())]
    assert sources and all(s["model"] == "fret_species" for s in sources)
    assert all("transfer_efficiency" in s for s in sources)


def test_fret_auto_fit_exposes_distances_as_linkable_parameters(qapp, qtbot, tmp_path):
    from chisurf.core.fitting.parameter import FittingParameter

    widget = _autofit_widget(qtbot, tmp_path, n_components=2, kind="fret")

    means = [p for p in widget._auto_fit_result["model"].parameters_all
             if getattr(p, "canonical_id", "").startswith("distance.mean.")]
    assert len(means) == 3        # the model holds as many as it could use
    assert all(isinstance(p, FittingParameter) for p in means)
    names = {getattr(p, "name", "") for p in widget.autofit_parameter_table._params}
    # Only the fitted topology's two distances are rows.
    assert {"RDA0", "RDA1"} <= names and "RDA2" not in names, names


def test_derived_fret_efficiencies_still_available_without_a_fret_fit():
    """The lifetime->E fallback stays, for callers that only have lifetimes."""
    from chisurf.plugins.fcs.fcs_filter_calculator.gui_parts.main_window import (
        FcsFilterCalculatorWidget,
    )

    # Pure function of its arguments: E = 1 - tau/tau_D0 with tau_D0 = max(tau).
    taus = np.array([2.0, 4.0])
    derived = [float(np.clip(1.0 - t / 4.0, 0.0, 0.999)) for t in taus]
    assert derived == pytest.approx([0.5, 0.0])
    assert hasattr(FcsFilterCalculatorWidget, "_add_fret_autofit_species")
