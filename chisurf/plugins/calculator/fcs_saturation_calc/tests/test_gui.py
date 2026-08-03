import os

import pytest
from qtpy import QtWidgets

from chisurf.gui.autoform.sections.builtin import PlotWidget
from chisurf.plugins.calculator.fcs_saturation_calc.gui.tool import SaturationCalculatorTool


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app


def test_saturation_calculator_tool_instantiation(qapp):
    """Test that the SaturationCalculatorTool can be instantiated without errors."""
    tool = SaturationCalculatorTool()

    # Verify the tool has the expected attributes
    assert tool.form is not None, "AutoForm was not created."
    assert hasattr(tool, "fcs_curves_series"), "fcs_curves_series property is missing."

    # Ensure plots are initialized with non-empty curves
    series = tool.fcs_curves_series
    assert len(series) == 2, "Expected 2 series (unperturbed & saturated)."
    assert len(series[0]["x"]) == 300
    assert len(series[1]["x"]) == 300

    # FCS, Volume vs Power, Volume Profile, Diffusion Time vs Power
    plot_widgets = tool.form.findChildren(PlotWidget)
    assert len(plot_widgets) == 4, f"Expected 4 PlotWidgets in form, found {len(plot_widgets)}."
    for pw in plot_widgets:
        assert len(pw.plot._canvas.native.items) >= 1, "Expected plot curves to be drawn."

    # Ensure toolbar buttons (Compute, Guide & Help) exist
    assert tool.toolbar is not None
    actions = [a.text() for a in tool.toolbar.actions()]
    assert any("Compute" in a for a in actions), (
        f"Compute action missing from toolbar. Found: {actions}"
    )

    btn_texts = [w.text() for w in tool.toolbar.findChildren(QtWidgets.QToolButton)]
    assert any("Guide" in t for t in btn_texts), (
        f"Guide button missing from toolbar. Found: {btn_texts}"
    )
    assert any(t in ("?", "Help") for t in btn_texts), (
        f"Help button missing from toolbar. Found: {btn_texts}"
    )


def test_power_sweep_series(qapp):
    """Assert power sweep properties generate valid volume and diffusion time series."""
    tool = SaturationCalculatorTool()
    tool.power_mW = 5.0
    v_series = tool.volume_power_series
    tau_series = tool.tau_d_power_series

    assert len(v_series) == 2
    assert len(tau_series) == 2
    assert len(v_series[0]["x"]) > 10
    assert len(tau_series[0]["x"]) > 10
    assert v_series[1]["x"][0] == 5.0
    assert tau_series[1]["x"][0] == 5.0


def test_state_change_updates_rate_matrices(qapp):
    """Assert that changing the number of states resizes the rate matrix in model and GUI."""
    from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget

    tool = SaturationCalculatorTool()
    matrices = tool.form.findChildren(RateMatrixWidget)
    assert len(matrices) == 2, "dark-rate and excitation matrices must both be editable"
    assert matrices[0].table.rowCount() == 3

    # Change n_states to 4
    tool.saturation.n_states = 4
    tool.form.sync_fields()
    tool.form.refresh_plots()

    assert tool.saturation.n_states == 4
    assert len(tool.saturation.dark.matrix) == 16  # 4x4
    assert len(tool.saturation.exc.matrix) == 16  # 4x4
    for m in matrices:
        assert m.table.rowCount() == 4
        assert m.table.columnCount() == 4


def test_compute_updates_info_text(qapp):
    """Assert that clicking compute populates summary info text."""
    tool = SaturationCalculatorTool()
    tool._on_compute()
    info = tool.info_text()
    assert "FCS saturation summary" in info
    assert "Volume expansion" in info
    assert "Peak focal rate" in info


def test_bunching_toggle_affects_curves(qapp):
    """Assert that toggling bunching dynamics changes the initial saturated curve value."""
    tool = SaturationCalculatorTool()
    tool.power_mW = 2.0
    tool.include_bunching = True
    series_bunching = tool.fcs_curves_series
    g_sat_bunching_0 = series_bunching[1]["y"][0]

    tool.include_bunching = False
    series_nobunching = tool.fcs_curves_series
    g_sat_nobunching_0 = series_nobunching[1]["y"][0]

    assert g_sat_bunching_0 != g_sat_nobunching_0
    assert g_sat_bunching_0 > g_sat_nobunching_0


def test_rate_matrix_widgets_stretch_and_style(qapp):
    """Assert RateMatrixWidget uses stretch mode and compact styling."""
    from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget

    tool = SaturationCalculatorTool()
    matrices = tool.form.findChildren(RateMatrixWidget)
    assert len(matrices) == 2
    for m in matrices:
        assert m.table.horizontalHeader().sectionResizeMode(0) == QtWidgets.QHeaderView.Stretch
        assert m.table.verticalHeader().sectionResizeMode(0) == QtWidgets.QHeaderView.Stretch


def test_rate_unit_switching(qapp):
    """Assert that switching rate_unit rescales dark rates and updates header label."""
    from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget

    tool = SaturationCalculatorTool()
    tool.rate_unit = "1/ms"
    k21_ms = tool.saturation.dark.rates_by_name()["k2_1"].value

    tool.rate_unit = "1/us"
    k21_us = tool.saturation.dark.rates_by_name()["k2_1"].value
    assert abs(k21_us - (k21_ms / 1000.0)) < 1e-6

    matrices = tool.form.findChildren(RateMatrixWidget)
    assert "(1/us)" in matrices[0]._header_label.text()


def test_scheme_presets_and_state_scheme_widget(qapp):
    """Assert scheme preset loading updates state count, labels, rates, and HMM graph widget."""
    from chisurf.gui.autoform.sections.state_scheme_section import StateSchemeWidget

    tool = SaturationCalculatorTool()

    scheme_widgets = tool.form.findChildren(StateSchemeWidget)
    assert len(scheme_widgets) == 1, "StateSchemeWidget missing from AutoForm layout."

    tool.scheme_preset = "Cyanine 5 (4-state, isomer + triplet)"
    assert tool.saturation.n_states == 4
    assert tool.saturation.state_labels == ["S0", "S1", "P", "T1"]

    tool.scheme_preset = "Two-state (ground + excited)"
    assert tool.saturation.n_states == 2

    tool.scheme_preset = "Rhodamine 6G (3-state, triplet)"
    assert tool.saturation.n_states == 3
    # The excitation matrix must come from the scheme too, not survive by luck.
    assert tool.saturation.exc.rates_by_name()["sigma1_2"].value == 1.0


def test_save_and_load_kinetics_scheme(tmp_path, qapp):
    """Assert saving and loading a custom kinetics scheme JSON restores all rates and parameters."""
    tool = SaturationCalculatorTool()
    tool.saturation.n_states = 3
    tool.saturation.dark.rates_by_name()["k2_3"].value = 12.34

    file_path = str(tmp_path / "my_custom_scheme.json")
    tool.save_scheme_to_file(file_path)
    assert os.path.exists(file_path)

    # Reset tool state
    tool2 = SaturationCalculatorTool()
    tool2.saturation.dark.rates_by_name()["k2_3"].value = 0.0
    tool2.load_scheme_from_file(file_path)
    assert abs(tool2.saturation.dark.rates_by_name()["k2_3"].value - 12.34) < 1e-5


def test_user_settings_persistence(tmp_path, monkeypatch, qapp):
    """Assert tool settings are saved to and restored from user settings directory."""
    settings_file = str(tmp_path / "settings.json")
    monkeypatch.setattr(
        SaturationCalculatorTool, "get_user_settings_path", lambda self: settings_file
    )

    tool = SaturationCalculatorTool()
    tool.saturation._power.value = 0.55  # 550 mW
    tool.normalize_fcs = True
    tool.save_user_settings()

    assert os.path.exists(settings_file)

    tool2 = SaturationCalculatorTool()
    assert abs(tool2.saturation._power.value - 0.55) < 1e-5
    assert tool2.normalize_fcs is True


def test_guided_tour_raises_target_dock_tab(qapp):
    """Assert guided tour steps raise the referenced dock tab to foreground."""
    import sys

    from chisurf.gui.widgets.tools.guided_tour import GuidedTour, load_tour

    tool = SaturationCalculatorTool()
    mod = sys.modules[tool.__module__]
    guide_file = os.path.join(os.path.dirname(mod.__file__), "guide.json")
    steps = load_tour(guide_file)
    assert len(steps) >= 5

    tour = GuidedTour(tool, steps, model=tool)
    assert tour.start(index=0) is True

    # Advance through steps targeting different docks
    for i in range(1, len(steps)):
        tour.next()
        target_widget = tour.resolve_target(tour.steps[tour.index].target)
        if target_widget is not None:
            assert target_widget.parentWidget() is not None
    tour.stop()


def test_number_of_states_updates_brightness_and_form_tables(qapp):
    """Assert changing n_states updates brightness parameters and table sizes."""
    tool = SaturationCalculatorTool()
    assert tool.saturation.n_states == 3
    assert len(tool.saturation.brightness.parameters_all) == 3
    assert tool.saturation.state_labels == ["S0", "S1", "T1"]

    # Change n_states to 4 (e.g. Cy5 4-state scheme)
    tool.saturation.n_states = 4
    assert len(tool.saturation.brightness.parameters_all) == 4
    assert tool.saturation.dark.n_states == 4
    assert len(tool.saturation.state_labels) == 4

    # Change n_states to 6
    tool.saturation.n_states = 6
    assert len(tool.saturation.brightness.parameters_all) == 6
    assert tool.saturation.dark.n_states == 6


def test_wavelength_and_dye_are_exposed(qapp):
    """The excitation wavelength must be settable and reach the computation."""
    tool = SaturationCalculatorTool()
    tool.power_mW = 2.0
    blue = list(tool.fcs_curves_series[1]["y"])
    tool.wavelength_nm = 640.0
    assert tool.wavelength_nm == 640.0
    red = list(tool.fcs_curves_series[1]["y"])
    assert blue != red
    assert isinstance(tool.dye_names(), list)


def test_state_profile_series_has_one_curve_per_state(qapp):
    """The profile plot must follow the scheme size, not a fixed S0/S1/T1 trio."""
    tool = SaturationCalculatorTool()
    tool.power_mW = 2.0
    tool.scheme_preset = "Cyanine 5 (4-state, isomer + triplet)"
    names = [s["name"] for s in tool.volume_profile_series]
    assert sum(n.startswith("P") for n in names) == 4
    tool.show_state_profiles = False
    hidden = [s["name"] for s in tool.volume_profile_series]
    assert not any(n.startswith("P") for n in hidden)


def test_zero_power_leaves_the_two_curves_identical(qapp):
    """P = 0 is unsaturated by definition; the GUI must not fake a power."""
    import numpy as np

    tool = SaturationCalculatorTool()
    tool.power_mW = 0.0
    series = tool.fcs_curves_series
    np.testing.assert_allclose(series[0]["y"], series[1]["y"], rtol=1e-12)
