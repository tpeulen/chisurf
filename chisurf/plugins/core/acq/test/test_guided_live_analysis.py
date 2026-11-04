"""Live reference curves and scalar checks use generated photons, not fixtures of results."""
import numpy as np
from chisurf.plugins.core.acq.live.sources import PhotonBatch


def test_live_reference_analysis_accumulates_rates_decays_correlations_and_honest_checks():
    from chisurf.plugins.core.acq.live.guided_analysis import GuidedLiveAnalysis
    rng=np.random.default_rng(9)
    ticks=np.cumsum(rng.integers(1,100,8000)).astype(np.uint64)
    micro=np.clip(rng.exponential(80,8000),0,999).astype(np.uint16)
    channel=np.arange(8000,dtype=np.int8)%2
    a=GuidedLiveAnalysis(1e-6,8e-12,1000,'green_reference')
    a.push(PhotonBatch(ticks,micro,channel))
    snap=a.snapshot()
    assert snap['stage']=='green_reference'
    assert sum(int(h.sum()) for h in snap['decays'].values())==8000
    assert all(v['tau_s'].size>0 for v in snap['correlations'].values())
    assert all(v>0 for v in snap['rates_hz'].values())
    assert snap['quality']
    assert any(r['status']=='unverified' for r in snap['quality']), 'unconfigured scientific limits must never pass'


def test_rate_trace_uses_each_bin_while_summary_uses_the_whole_acquisition():
    from chisurf.plugins.core.acq.live.guided_analysis import GuidedLiveAnalysis
    a=GuidedLiveAnalysis(1e-6,8e-12,1000,'buffer')
    a.push(PhotonBatch(np.asarray([100,200,300],dtype=np.uint64),np.ones(3,dtype=np.uint16),np.zeros(3,dtype=np.int8)))
    a.push(PhotonBatch(np.asarray([400],dtype=np.uint64),np.ones(1,dtype=np.uint16),np.zeros(1,dtype=np.int8)))
    snap=a.snapshot()
    np.testing.assert_allclose(snap['rate_curves_hz'][0],[15000.,10000.])
    np.testing.assert_allclose(snap['rates_hz'][0],4/.0003)


def test_bad_scientific_bounds_are_rejected_before_any_light_change(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
    m=RecordModel(output_dir=tmp_path);assert m.connect_instrument_simulator()
    app=RecordApp(m)
    try:
        w=app.wizard.model;w._index=w.STEPS.index('water')
        w.power_index=2;w.power_drives={'Green 488 nm':20,'Red 640 nm':20}
        w._approved_connected_heads=[name for _,name in m.power_head_options()]
        w.physical_done=True
        w.protocol['reference_limits']={'water':{'rate_khz':[.1]}}
        events=list(m.laser.events)
        assert not w.start_measurement()
        assert m.laser.events==events
        assert m.laser.state().emission_blocked
    finally:app.close()


def test_recording_and_every_guided_stage_keep_live_plots_present(tmp_path,monkeypatch):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
    from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    m=RecordModel(output_dir=tmp_path);assert m.connect_instrument_simulator()
    app=RecordApp(m)
    try:
        m.ui_mode='guided';m.ui_mode_changed()
        ui=Driver(app,(1500,950))
        for step in ('setup','water','buffer','green_reference','red_reference','dna','sample'):
            app.wizard.model._index=app.wizard.model.STEPS.index(step)
            ui.draw(2)
            assert 'SIMULATION' in app.wizard.window.title
            for key in ('guided_count_plot','guided_corr_plot','guided_decay_plot','guided_stage_plot'):
                assert key in app.item_rects,(step,key)
            assert 'wizard_next' in app.item_rects
    finally:app.close()


def test_compact_sample_keeps_es_marginals_readable_and_footer_visible(tmp_path,monkeypatch):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
    from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
    from chisurf.plugins.core.acq.live import devices
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    monkeypatch.setattr(devices,'attached_devices',lambda *args,**kwargs:[])
    model=RecordModel(output_dir=tmp_path);assert model.connect_instrument_simulator()
    app=RecordApp(model)
    try:
        model.ui_mode='guided';model.ui_mode_changed()
        app.wizard.model._index=app.wizard.model.STEPS.index('sample')
        from unittest.mock import MagicMock
        model.session=MagicMock();app.wizard.model._display_session=model.session
        model.snapshot={'histograms':[{'x':'E','y':'S','counts':np.ones((4,4)),
                                       'x_edges':np.linspace(0,1,5),'y_edges':np.linspace(0,1,5)}]}
        ui=Driver(app,(1000,700));ui.draw(3)
        assert app.item_rects['guided_stage_plot'][3]>=220
        x,y,w,h=app.item_rects['wizard_next']
        assert 0<=y and y+h<=700
    finally:
        model.session=None
        app.close()


def test_dna_and_sample_show_empty_es_axes_and_do_not_reuse_previous_stage(tmp_path,monkeypatch):
    from emtk import implot
    from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
    from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
    from chisurf.plugins.core.acq.live import devices
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    monkeypatch.setattr(devices,'attached_devices',lambda *args,**kwargs:[])
    calls=[]
    monkeypatch.setattr(implot,'plot_heatmap',lambda *args,**kwargs:calls.append(args))
    model=RecordModel(output_dir=tmp_path);assert model.connect_instrument_simulator()
    app=RecordApp(model)
    try:
        model.ui_mode='guided';model.ui_mode_changed()
        ui=Driver(app,(1000,700))
        for step in ('dna','sample'):
            app.wizard.model._index=app.wizard.model.STEPS.index(step)
            model.snapshot=None
            strings=ui.draw(2).strings
            assert 'E marginal' in strings and 'S marginal' in strings
            assert app.item_rects['guided_stage_plot'][3]>=220
        from unittest.mock import MagicMock
        model.session=MagicMock();app.wizard.model._display_session=model.session
        model.snapshot={'reference_live':{'stage':'dna'},'histograms':[
            {'x':'E','y':'S','counts':np.ones((2,2)),
             'x_edges':np.linspace(0,1,3),'y_edges':np.linspace(0,1,3)}]}
        ui.draw(2)
        assert not calls, 'sample must not draw the preceding DNA histogram'
    finally:
        model.session=None
        app.close()


def test_wizard_does_not_show_old_stage_or_previous_sample_counts(tmp_path,monkeypatch):
    from unittest.mock import MagicMock
    from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
    from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
    from chisurf.plugins.core.acq.live import devices
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    monkeypatch.setattr(devices,'attached_devices',lambda *args,**kwargs:[])
    model=RecordModel(output_dir=tmp_path);assert model.connect_instrument_simulator()
    app=RecordApp(model)
    try:
        model.ui_mode='guided';model.ui_mode_changed();wizard=app.wizard.model
        model.session=MagicMock();model.session.running=False;wizard._display_session=model.session
        monkeypatch.setattr(model,'_poll_runs',lambda *args,**kwargs:None)
        model.snapshot={'bursts':43,'photons':16885,'elapsed_s':3.,
                        'reference_live':{'stage':'dna'}}
        wizard._index=wizard.STEPS.index('dna');wizard.measurements['dna']={'path':'x'}
        assert wizard.next_step() and wizard.step_id=='sample'
        ui=Driver(app,(1000,700));strings=ui.draw(2).strings
        assert not any('16885' in line or 'Bursts: 43' in line for line in strings)
        assert not wizard.display_snapshot()
        wizard._display_session=model.session
        model.snapshot={'bursts':7,'photons':932,'elapsed_s':5.,
                        'reference_live':{'stage':'sample'}}
        wizard.measurements['sample']={'path':'x'}
        assert wizard.next_sample()
        strings=ui.draw(2).strings
        assert not any('932' in line or 'Bursts: 7' in line for line in strings)
        assert not wizard.display_snapshot()
    finally:
        model.session=None
        app.close()
