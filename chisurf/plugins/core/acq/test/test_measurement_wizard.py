"""Guided mode is sequential and cannot consume a random measurement."""
from types import SimpleNamespace
import pytest


def config():
    return {'name':'Test approved setup', 'kind':'fret',
            'filters':'TEST green filter A / red filter B', 'splitter':'TEST color splitter C',
            'dyes':'TEST donor / acceptor', 'laser_targets_uw':{'test laser':1},
            'seconds':1, 'min_photons':10, 'irf_fwhm_max_ns':.5,
            'background_max_khz':10}


def record():
    return SimpleNamespace(output_dir=None, running=False, source_kind='device',
                           device=object(), operator_name='TP', project_name='test', sample_name='test',
                           laser=SimpleNamespace(state=lambda:SimpleNamespace(emission_blocked=True)),
                           shutters=SimpleNamespace(get_parameter=lambda *a:0),
                           laser_off=lambda:None, _shutters_at_end=lambda:None,
                           power_servo=None, cancel_power_target=lambda:None)


def test_wizard_requires_approved_setup_and_does_not_skip_physical_checks(tmp_path):
    from chisurf.plugins.core.acq.gui.measurement_wizard import MeasurementWizardModel
    r=record();r.output_dir=tmp_path
    w=MeasurementWizardModel(r)
    assert not w.next_step()
    assert w.step_id=='setup'
    w.protocol=config()
    assert w.next_step()
    assert w.step_id=='optics'
    assert not w.next_step()
    w.physical_done=True
    assert w.next_step()
    assert w.step_id=='power'
    w.physical_done is False
    assert not w.next_step()
    # The novice cannot jump directly to sample by editing a public selector.
    assert not hasattr(w,'step_options')


def test_wizard_refuses_simulation_and_foreign_or_incomplete_runs(tmp_path):
    from chisurf.plugins.core.acq.gui.measurement_wizard import MeasurementWizardModel
    r=record();r.output_dir=tmp_path;r.source_kind='simulator'
    w=MeasurementWizardModel(r);w.protocol=config()
    assert not w.next_step()
    assert 'real' in w.message.lower()
    r.source_kind='device'
    assert w.next_step()
    w._index=w.STEPS.index('water')
    r.saved_path=tmp_path/'unrelated.ptu';r.session=SimpleNamespace(result=object())
    assert not w.accept_measurement()
    assert 'this step' in w.message.lower()


def test_guided_mode_is_modal_and_blocks_background_start(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    m=RecordModel(output_dir=tmp_path,realtime=False);app=RecordApp(m)
    try:
        m.ui_mode='guided';m.ui_mode_changed()
        ui=Driver(app,(1500,950));ui.draw(3)
        assert app.wizard.window.open
        assert not m.enabled('start')
        assert not m.start()
        assert 'start_pause' not in app.form.rects
        assert 'wizard_next' in app.item_rects
        assert 'wizard_abort' in app.item_rects
        assert 'source_kind' not in app.item_rects
    finally:app.close()
