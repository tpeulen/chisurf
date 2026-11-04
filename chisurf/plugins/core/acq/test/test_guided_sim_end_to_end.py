"""A complete guided practice session must write independently readable PTUs."""
import time
import numpy as np
import tttrlib
from chisurf.plugins.microscopy.imaging_emtk.testing import hermetic_env


def test_complete_guided_simulation_acquires_each_stage(tmp_path,monkeypatch):
    hermetic_env(tmp_path,monkeypatch)
    from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
    from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    m=RecordModel(output_dir=tmp_path/'measurements',realtime=False)
    assert m.connect_instrument_simulator()
    app=RecordApp(m);w=app.wizard.model
    try:
        m.operator_name='SIM';m.project_name='SIMULATION';m.sample_name='Practice sample'
        assert w.next_step(),w.message
        assert w.step_id=='optics'
        w.physical_done=True;assert w.next_step(),w.message
        assert w.step_id=='power'
        assert w.set_approved_power(),w.message  # one allow-light gesture chains both heads
        deadline=time.monotonic()+8
        while (w._power_pending or w.power_index<2) and time.monotonic()<deadline:
            if m.power_servo is not None:m.power_servo.settle_s=0
            m.power_poll(force=True);w.poll();time.sleep(.005)
        assert w.next_step() and w.step_id=='water'
        for step in ('water','buffer','fcs','green_reference','red_reference','dna','sample'):
            assert w.step_id==step
            if step=='fcs':w.fcs_seconds=2.
            w.physical_done=True
            assert w.start_measurement(),w.message
            deadline=time.monotonic()+15
            while (m.running or w._owned_session is not None) and time.monotonic()<deadline:
                m.poll(force=True);w.poll();time.sleep(.01)
            assert not m.running
            if step=='dna':
                assert m.session.result.bursts>0, 'DNA practice must populate the burst/E-S view'
            live=m.session.snapshot()['reference_live']
            assert live['stage']==step and live['decays'] and live['correlations']
            assert sum(int(v.sum()) for v in live['decays'].values())==m.session.result.photons
            assert step in w.measurements,(step,w.message,w.quality_rows())
            rec=w.measurements[step];assert rec['simulation'] is True
            data=tttrlib.TTTR(rec['path'],'PTU')
            assert np.sum(np.asarray(data.event_types)==0)==rec['photons']>0
            ticks=np.asarray(data.macro_times)
            assert not np.any(ticks[1:]<ticks[:-1])
            assert 'simulator' in rec['path']
            if step!='sample':
                assert w.step_id!=step,(step,w.step_id,w.message)  # green stages auto-advance
        assert w.step_id=='sample'
        assert w.finish_session(),w.message
        assert w.step_id=='done'
        assert len({r['path'] for r in w.measurements.values()})==7
    finally:app.close()
