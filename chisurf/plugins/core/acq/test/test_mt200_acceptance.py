"""Owner acceptance regressions, independently exercising the delivered GUI."""
import numpy as np


def test_mirrored_trace_keeps_acceptor_below_zero(monkeypatch):
    from emtk import implot
    from chisurf.plugins.core.acq.gui.record_app import _plot_mirrored_trace
    captured = {}
    monkeypatch.setattr(implot, 'begin_plot', lambda *a, **k: True)
    for name in ('setup_axes', 'setup_axis_limits', 'set_next_line_style',
                 'set_next_fill_style', 'plot_stairs', 'plot_line', 'end_plot'):
        monkeypatch.setattr(implot, name, lambda *a, **k: None)
    monkeypatch.setattr(implot, 'plot_shaded', lambda name, x, y, **k: captured.update({name: np.asarray(y)}))
    trace = {'t': np.arange(4.), 'bin_s': 1., 'streams': [
        {'name': 'DD', 'counts': [1, 4, 8, 2], 'sign': 1, 'colour': (0, 1, 0, 1), 'run_mean_per_bin': 3.},
        {'name': 'DA', 'counts': [2, 3, 5, 1], 'sign': -1, 'colour': (1, 0, 0, 1), 'run_mean_per_bin': 2.},
    ]}
    _plot_mirrored_trace(trace, (600, 200))
    assert np.all(captured['DD'] >= 0)
    assert np.all(captured['DA'] <= 0), 'red photons must stay below the baseline'
    assert np.any(captured['DA'] < 0)


def test_power_and_guided_workflows_are_in_the_record_app(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    app = RecordApp(RecordModel(output_dir=tmp_path, realtime=False))
    try:
        ui = Driver(app, (1500, 950))
        app.focus_dock('power_calibration')
        ui.draw(3)
        assert 'add_point' in app.item_rects
        assert 'laser_name' in app.item_rects
        assert 'rep_rate_mhz' not in app.item_rects
        app.model.ui_mode = 'guided'
        app.model.ui_mode_changed()
        ui.draw(3)
        assert app.wizard.window.open
        assert 'wizard_next' in app.item_rects
        assert 'wizard_quality' in app.item_rects
    finally:
        app.close()


def test_view_ranges_are_hidden_until_requested(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    app = RecordApp(RecordModel(output_dir=tmp_path, realtime=False))
    try:
        ui = Driver(app, (1500, 950))
        for dock in ('plot_hist', 'plot_trace', 'plot_decays'):
            sections = app._panels(dock)[0]['sections']
            fold = next(i for i, s in enumerate(sections) if s.get('collapsed'))
            plot = next(i for i, s in enumerate(sections) if s.get('type') == 'custom')
            assert fold < plot, 'range header must precede the height-filling plot to remain reachable'
        ui.draw(3)
        for attr in ('rates_x_min', 'rates_x_max', 'rates_y_max',
                     'decays_x_min', 'decays_x_max', 'decays_y_max',
                     'hist_x_min', 'hist_x_max', 'hist_y_max'):
            assert attr not in app.form.rects, 'range settings must not occupy plot space by default'
        assert 'Trace range.fold' not in app.form.rects
        app.model.ui_mode='advanced';app.model.ui_mode_changed()
        app.focus_dock('plot_trace');ui.draw(2)
        ui.click('Trace range.fold')
        ui.draw(2)
        assert 'rates_x_max' in app.form.rects
        assert 'decays_x_max' not in app.form.rects, 'each plot must expand independently'
        assert 'hist_x_max' not in app.form.rects
    finally:
        app.close()


def test_sync_is_visible_alongside_running_detector_rates(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.device_rates_hz = [20e6, 1234, 0, 5678]
    model.snapshot = {'bursts': 0, 'burst_rate_hz': 0, 'photons': 10, 'elapsed_s': 1.,
                     'trace': {'bin_width_s': .001, 'first_bin': 0,
                                'counts': {'green': np.array([2, 2]),
                                           'red': np.array([3, 3])}}}
    app = RecordApp(model)
    try:
        ui = Driver(app, (1500, 950))
        app.focus_dock('rates')
        ui.draw(3)
        # Tables paint through the shared painter, not the im.text wrapper.
        seen = ui.strings()
        assert any('sync' in text.lower() for text in seen), seen
        assert '20.00' in seen and 'MHz' in seen, seen
    finally:
        app.close()
