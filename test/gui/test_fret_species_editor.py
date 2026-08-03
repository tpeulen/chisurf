"""Tests for the FRET-species editor and its Filter-Calculator integration."""

from __future__ import annotations


def _model(**kw):
    from chisurf.gui.widgets.fret_species_editor import FretSpeciesEditorModel

    return FretSpeciesEditorModel(**kw)


def test_editor_builds_autoform(qapp, qtbot):
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.help_section import HelpButton
    from chisurf.gui.widgets.dock_area import DockArea

    form = AutoForm(_model())
    qtbot.addWidget(form)
    assert form.findChildren(HelpButton)
    # Parameters + preview plot live in a dock area (plot docked to the right).
    assert form.findChildren(DockArea)


def test_component_roundtrip():
    m = _model()
    m.state = "da"
    m.transfer_efficiency = 0.6
    m.alpha = 0.03
    comp = m.component()
    assert comp["model"] == "fret_species"
    assert comp["state"] == "da"
    assert comp["crosstalk"]["alpha"] == 0.03

    m2 = _model()
    m2.load_component(comp)
    assert m2.state == "da"
    assert m2.transfer_efficiency == 0.6
    assert m2.alpha == 0.03


def test_channel_series_has_three_colors(qapp, qtbot):
    m = _model()
    series = m.channel_series()
    names = {s["name"] for s in series}
    assert names == {"green", "red", "yellow"}


def test_polarized_series_splits_channels(qapp, qtbot):
    m = _model()
    m.polarized = True
    names = {s["name"] for s in m.channel_series()}
    assert "green_parallel" in names and "red_perpendicular" in names


def test_seed_from_calibration():
    m = _model()
    m.set_calibration_seed(lambda: {"alpha": 0.05, "gamma": 0.8, "forster_radius": 60.0})
    m.seed_from_calibration()
    assert m.alpha == 0.05 and m.gamma == 0.8 and m.forster_radius == 60.0


def test_detector_patterns_map_channels():
    from chisurf.core.fluorescence.fret.species_decay import fret_species_detector_patterns

    m = _model()
    m.state = "da"
    comp = m.component()
    patterns = fret_species_detector_patterns(comp, ["green", "red", "yellow"], 256)
    assert set(patterns) >= {"green", "red", "yellow", "__default__"}
    # Donor (green) and sensitized-acceptor (red) decays differ.
    import numpy as np

    assert not np.allclose(patterns["green"], patterns["red"])


def test_detector_patterns_apply_per_detector_irf():
    import numpy as np

    from chisurf.core.fluorescence.fret.species_decay import fret_species_detector_patterns
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    m = _model()
    t = np.arange(256) * m.bin_width

    def irf_for(name):
        # Unnormalized IRF on purpose — the expander must normalize it to unity.
        return synthetic_irf(t, 0.5, 0.3, norm=False) * 1234.0

    ideal = fret_species_detector_patterns(m.component(), ["green"], 256)
    conv = fret_species_detector_patterns(m.component(), ["green"], 256, irf_for_detector=irf_for)
    # Per-detector IRF delays the peak; independent of the (large) IRF scale.
    assert np.argmax(conv["green"]) > np.argmax(ideal["green"])


def test_donor_only_yellow_is_zero():
    from chisurf.core.fluorescence.fret.species_decay import fret_species_detector_patterns

    m = _model()
    m.state = "d_only"
    patterns = fret_species_detector_patterns(m.component(), ["green", "red", "yellow"], 256)
    assert patterns["yellow"].sum() == 0.0


def test_distance_distribution_edit():
    m = _model()
    m.fret_mode = "distance"
    m.update_distance_cell(0, "mean", 45.0)
    m.update_distance_cell(0, "sigma", 8.0)
    m.add_distance_row()
    comp = m.component()
    assert comp["distance_rows"][0]["mean"] == 45.0
    assert len(comp["distance_rows"]) == 2


def test_period_and_shift_flow_to_detector_patterns():
    import numpy as np

    from chisurf.core.fluorescence.fret.species_decay import fret_species_detector_patterns
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    m = _model()
    m.period_ns = 12.5
    m.time_shift_ns = 0.3
    comp = m.component()
    assert comp["period_ns"] == 12.5 and comp["time_shift_ns"] == 0.3
    t = np.arange(256) * m.bin_width

    def irf_for(_name):
        return synthetic_irf(t, 0.5, 0.3)

    aperiodic = dict(comp); aperiodic["period_ns"] = 0.0
    p_periodic = fret_species_detector_patterns(comp, ["green"], 256, irf_for_detector=irf_for)
    p_aperiodic = fret_species_detector_patterns(aperiodic, ["green"], 256, irf_for_detector=irf_for)
    # Periodic (laser-period) convolution differs from the aperiodic result.
    assert not np.allclose(p_periodic["green"], p_aperiodic["green"])


def test_plot_refreshes_even_when_dock_reparents_it(qapp, qtbot):
    """A dock can reparent/float the preview plot out of the AutoForm's child
    tree; refresh_plots must still reach it (regression: table edits stopped
    recomputing the curves once the plot lived in a dock)."""
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.builtin import PlotWidget

    m = _model()
    form = AutoForm(m)
    m.set_changed_callback(form.refresh_plots)
    qtbot.addWidget(form)
    plot = form.findChildren(PlotWidget)[0]
    # Simulate a floated dock: detach the plot from the AutoForm's child tree.
    plot.setParent(None)
    assert plot not in form.findChildren(PlotWidget)

    calls = {"n": 0}
    orig = plot.refresh
    plot.refresh = lambda: (calls.__setitem__("n", calls["n"] + 1), orig())[1]
    m.field_changed()
    # Still refreshed via the tracked-target registry.
    assert calls["n"] >= 1


def test_anisotropy_spectrum_edit_and_roundtrip():
    m = _model()
    # Two-component donor anisotropy spectrum.
    m.update_donor_aniso_cell(0, "amplitude", 0.25)
    m.update_donor_aniso_cell(0, "rho", 0.6)
    m.add_donor_aniso_row()
    m.update_donor_aniso_cell(1, "amplitude", 0.1)
    m.update_donor_aniso_cell(1, "rho", 9.0)
    comp = m.component()
    an = comp["anisotropy"]
    assert an["donor_spectrum"][0] == {"amplitude": 0.25, "rho": 0.6}
    assert len(an["donor_spectrum"]) == 2

    m2 = _model()
    m2.load_component(comp)
    assert m2.donor_aniso_rows[1]["rho"] == 9.0
    # Flows through to the coupled decay generator.
    from chisurf.core.fluorescence.fret.species_decay import fret_species_from_dict
    sp = fret_species_from_dict(comp)
    assert len(sp.anisotropy._rows("donor")) == 2
