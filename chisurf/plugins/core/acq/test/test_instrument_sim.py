"""Complete instrument simulation: PIE heads, shutters, diode, and wizard."""
import time
import pytest


def test_pie_simulator_has_green_red_heads_and_complete_shutter_readback(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    m=RecordModel(output_dir=tmp_path,realtime=False)
    try:
        assert m.connect_instrument_simulator()
        state=m.laser.state()
        assert [(h.name,h.wavelength_nm) for h in state.heads]==[('Green 488 nm',488.),('Red 640 nm',640.)]
        assert state.oscillator is not None
        assert state.oscillator.output_enabled[:2]==[True,True]
        assert m.shutters.get_parameter('reported_excitation',-1)==0
        assert m.set_shutter('Excitation',True)
        assert m.shutters.get_parameter('reported_excitation',-1)==1
        assert m.shutter_form is not None
        assert 'simulator' in str(m.output_dir)
    finally:m.close()


def test_simulated_diode_follows_both_heads_and_shutter(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    m=RecordModel(output_dir=tmp_path,realtime=False)
    try:
        assert m.connect_instrument_simulator()
        m.laser.set_head(200,intensity_pct=20);m.laser.set_head(300,intensity_pct=30)
        m.set_shutter('Excitation',True);m.laser.set_emission(True)
        both=m.shutters.get_parameter('diode_raw',-1)
        m.laser.set_head(300,intensity_pct=0)
        green=m.shutters.get_parameter('diode_raw',-1)
        assert both>green>0
        m.set_shutter('Excitation',False)
        assert m.shutters.get_parameter('diode_raw',-1)<green
    finally:m.close()


def test_editing_simulated_protocol_preserves_its_provenance_and_scientific_bounds(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
    m=RecordModel(output_dir=tmp_path);assert m.connect_instrument_simulator()
    app=RecordApp(m)
    try:
        w=app.wizard.model
        w.protocol['reference_limits']={'green_reference':{'amplitude':[.01,100]}}
        assert w.save_protocol(),w.message
        assert w.protocol.get('simulation') is True
        assert w.protocol['reference_limits']['green_reference']['amplitude']==[.01,100]
    finally:app.close()


def test_guided_simulation_can_set_both_powers_without_real_hardware(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
    m=RecordModel(output_dir=tmp_path,realtime=False);assert m.connect_instrument_simulator()
    app=RecordApp(m);w=app.wizard.model
    try:
        assert w.protocol.get('simulation') is True
        m.operator_name='SIM';m.project_name='simulation';m.sample_name='simulated sample'
        assert w.next_step(),w.message
        assert w.step_id=='optics'
        w.physical_done=True;assert w.next_step(),w.message
        assert w.step_id=='power'
        assert w.set_approved_power(),w.message  # one allow-light gesture chains both heads
        deadline=time.monotonic()+8
        while (w._power_pending or w.power_index<2) and time.monotonic()<deadline:
            if m.power_servo is not None:m.power_servo.settle_s=0
            m.power_poll(force=True);w.poll();time.sleep(.005)
        assert w.power_index==2,w.message
        assert w.next_step() and w.step_id=='water'
    finally:app.close()
