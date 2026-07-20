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


def test_auto_fit_tail_range_resolves_distinct_components(qapp, qtbot, tmp_path):
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    # An IRF-convolved bi-exponential with a real prompt at ~bin 14 — fitting the
    # whole trace collapses; fitting the *tail range* resolves both lifetimes.
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
    # Tail range: from just past the prompt to the end.
    widget._fit_region.setRegion((25.0, 255.0))
    widget._fit_region_initialized = True
    widget.lw_species.clear()
    widget._auto_fit_components(n_components=2)

    assert widget.lw_species.count() == 2
    taus = sorted(
        widget.lw_species.item(i).data(QtCore.Qt.UserRole)["lifetimes"][0]
        for i in range(2)
    )
    # Two DISTINCT lifetimes recovered (not collapsed to one), and each species is
    # aligned to the fit-range start.
    assert abs(taus[0] - 1.2) < 0.3
    assert abs(taus[1] - 4.0) < 0.6
    assert taus[1] - taus[0] > 1.0
    src = widget.lw_species.item(0).data(QtCore.Qt.UserRole)
    assert src["start_bin"] == 25


def test_fit_region_selector_present(qapp, qtbot):
    import pyqtgraph as pg
    from chisurf.plugins.fcs.fcs_filter_calculator import FcsFilterCalculatorWidget

    widget = FcsFilterCalculatorWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget._fit_region, pg.LinearRegionItem)
    # Draggable range is functional: setting it drives _fit_range (used by auto-fit).
    widget._fit_region.setRegion((30.0, 200.0))
    widget._fit_region_initialized = True
    assert widget._fit_range(256) == (30, 200)


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

    lo, hi = widget._fit_region.getRegion()
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
