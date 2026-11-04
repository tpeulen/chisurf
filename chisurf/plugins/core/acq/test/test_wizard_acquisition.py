"""Integration of modal-stage recording with real synthetic photons and PTU reader.

Hardware collaborators are in-memory. No measured lab calibration is fabricated.
"""
import time
from types import SimpleNamespace
import tttrlib
from chisurf.plugins.core.acq.gui.record_app import RecordModel
from chisurf.plugins.core.acq.gui.measurement_wizard import MeasurementWizardModel
from chisurf.plugins.core.acq.live.laser import SimLaser
from chisurf.plugins.core.acq.live.sources import SimulatedPieSource


def setup(tmp_path):
    m=RecordModel(output_dir=tmp_path,realtime=False)
    m.source_kind='device';m.device=SimpleNamespace(close=lambda:None)
    m.apply_device_settings=lambda *a:None
    m.make_source=lambda:SimulatedPieSource(duration_s=3,realtime=False,seed=7)
    m._run_shutters=lambda *a:None
    m.laser=SimLaser();m.laser.open()
    m.shutters=SimpleNamespace(get_parameter=lambda *a:0,close=lambda:None)
    m.ui_mode='guided'
    w=MeasurementWizardModel(m)
    names=[h.name for h in m.laser.state().heads]
    w.protocol={'name':'Synthetic integration only','kind':'fret','filters':'test','splitter':'test',
                'dyes':'test','laser_targets_uw':{names[0]:1},'seconds':.2,'min_photons':1,
                'irf_fwhm_max_ns':100,'background_max_khz':1e9}
    w.power_index=1;w.power_drives={names[0]:10};w._approved_connected_heads=names
    w._index=w.STEPS.index('sample');w.physical_done=True
    return m,w


def test_wizard_owns_sample_acquisition_file_and_accepts_it(tmp_path):
    m,w=setup(tmp_path)
    try:
        assert w.start_measurement(),w.message
        assert w.physical_done is False
        assert m.stop_after is True
        assert m._guided_start_authorized is False
        assert m.session.wait(15) is not None
        m.poll(force=True)
        assert w.accept_measurement(),w.message
        p=w.measurements['sample']['path']
        t=tttrlib.TTTR(p,'PTU')
        assert sum(t.event_types==0)==m.session.result.photons>0
        assert w.next_step()
        assert w.step_id=='done'
    finally:m.close()


def test_interrupted_sample_is_retained_but_not_accepted(tmp_path):
    m,w=setup(tmp_path)
    m.make_source=lambda:SimulatedPieSource(duration_s=30,realtime=True,seed=7)
    try:
        assert w.start_measurement(),w.message
        m.stop();m.session.wait(15);m.poll(force=True)
        assert m.saved_path.exists()
        assert not w.accept_measurement()
        assert 'sample' not in w.measurements
        assert not w.next_step()
    finally:m.close()
