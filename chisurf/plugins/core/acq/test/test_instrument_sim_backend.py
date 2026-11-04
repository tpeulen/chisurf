"""Instrument simulator tests use generated photons, never an instrument."""
import time
import numpy as np


def test_shutters_and_diode_follow_selected_heads_and_emission():
    from chisurf.plugins.core.acq.live.instrument_sim import SimulationRig
    rig=SimulationRig()
    try:
        assert [h.wavelength_nm for h in rig.laser.state().heads]==[488,640]
        rig.laser.set_head(200,intensity_pct=20);rig.laser.set_head(300,intensity_pct=20)
        dark=rig.shutters.get_parameter('diode_raw')
        rig.shutters.set_parameter('open_excitation',1);rig.laser.set_emission(True)
        both=rig.shutters.get_parameter('diode_raw')
        rig.laser.set_head(300,intensity_pct=0)
        assert both>rig.shutters.get_parameter('diode_raw')>dark
        rig.shutters.set_parameter('diode_mark',1)
        assert rig.shutters.get_parameter('diode_mean')==-1
        time.sleep(.02)
        assert rig.shutters.get_parameter('diode_mean')>dark
    finally:rig.close()


def _collect(source):
    batches=[];source.start();deadline=time.monotonic()+8
    try:
        while not source.finished and time.monotonic()<deadline:
            b=source.read(.1)
            if b is not None and len(b):batches.append(b)
        assert source.finished
        assert not source.status().get('error')
        return batches
    finally:source.stop()


def test_generated_photons_obey_both_detector_shutters():
    from chisurf.plugins.core.acq.live.instrument_sim import SimulationRig
    r=SimulationRig()
    try:
        r.laser.set_head(200,intensity_pct=50);r.laser.set_head(300,intensity_pct=50)
        r.laser.set_emission(True);r.shutters.set_parameter('open_excitation',1)
        for name in ('green','red'):r.shutters.set_parameter('open_'+name,1)
        bright=_collect(r.source(stage='sample',seed=9,realtime=False,duration_s=.2))
        assert bright and {0,1} <= set(np.concatenate([b.channel for b in bright]).tolist())
        r.shutters.set_parameter('open_green',0);r.shutters.set_parameter('open_red',0)
        dark=_collect(r.source(stage='sample',seed=9,realtime=False,duration_s=.2))
        assert not dark
    finally:r.close()
