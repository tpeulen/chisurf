"""Decay display toggles tttrlib's two accumulators without changing acquisition."""
import numpy as np
import pytest


def test_decay_display_uses_total_or_selected_burst_photons(monkeypatch):
    from emtk import implot
    from chisurf.plugins.core.acq.gui.record_app import _plot_decays
    captured = {}
    monkeypatch.setattr(implot, 'begin_plot', lambda *a, **k: True)
    for name in ('setup_axes', 'setup_axis_scale', 'setup_axis_limits',
                 'set_next_line_style', 'plot_inf_lines', 'end_plot'):
        monkeypatch.setattr(implot, name, lambda *a, **k: None)
    monkeypatch.setattr(implot, 'plot_line', lambda name, x, y: captured.update({name: np.array(y)}))
    snapshot = {'decays': {'green': np.array([10., 20., 30.])},
                'burst_decays': {'green': np.array([1., 2., 3.])}}
    _plot_decays(snapshot, None, (600, 220), 3, bursts_only=False)
    np.testing.assert_array_equal(captured['green'], [10, 20, 30])
    _plot_decays(snapshot, None, (600, 220), 3, bursts_only=True)
    np.testing.assert_array_equal(captured['green'], [1, 2, 3])
    np.testing.assert_array_equal(snapshot['decays']['green'], [10, 20, 30])


def test_burst_decay_mode_never_falls_back_to_total(monkeypatch):
    from emtk import implot
    from chisurf.plugins.core.acq.gui.record_app import _plot_decays
    captured = []
    monkeypatch.setattr(implot, 'begin_plot', lambda *a, **k: True)
    for name in ('setup_axes', 'setup_axis_scale', 'setup_axis_limits',
                 'set_next_line_style', 'plot_inf_lines', 'end_plot'):
        monkeypatch.setattr(implot, name, lambda *a, **k: None)
    monkeypatch.setattr(implot, 'plot_line', lambda *a, **k: captured.append(a))
    _plot_decays({'decays': {'green': [100, 200]}}, None, (600, 220), bursts_only=True)
    assert not captured


def test_decay_toggle_is_clickable_and_saved(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    app = RecordApp(RecordModel(output_dir=tmp_path, realtime=False))
    try:
        ui = Driver(app, (1500, 950))
        app.focus_dock('plot_decays')
        ui.draw(3)
        assert app.model.decay_bursts_only is False
        ui.click('decay_bursts_only')
        assert app.model.decay_bursts_only is True
        saved = app.export_settings()
        assert saved['decay_bursts_only'] is True
        app.model.decay_bursts_only = False
        app.restore_settings(saved)
        assert app.model.decay_bursts_only is True
    finally:
        app.close()
