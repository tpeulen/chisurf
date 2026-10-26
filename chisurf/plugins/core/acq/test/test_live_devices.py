"""The device path: a simulated MultiHarp's records, decoded and recorded as a real one's are.

The owner's MultiHarp may be attached and in use: nothing here opens a real device.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest
import tttrlib

from chisurf.core.fluorescence.burst import burst_filter
from chisurf.plugins.core.acq.live import devices
from chisurf.plugins.core.acq.live.analyzer import analyze_offline
from chisurf.plugins.core.acq.live.session import RecordSession

pqusb = pytest.importorskip("pqusb")


def _sim(speed=1000.0, seed=3):
    dev = devices.PieSimDevice(seed=seed, speed=speed)
    dev.initialize(pqusb.MODE_T3)
    return dev


def test_the_simulated_multiharp_speaks_generic_t3_that_both_decoders_read_alike():
    dev = _sim()
    chunks = []
    stream = dev.stream(chunk_bytes=1 << 14)
    try:
        for words in stream:
            if len(words):
                chunks.append(np.frombuffer(words, dtype=np.uint32).copy())
            if sum(map(len, chunks)) > 20000:
                break
    finally:
        stream.close()  # stops the measurement and its reader thread
    assert dev.record_type() == 0x00010307
    state, data = tttrlib.TTTRDecodeState(), tttrlib.TTTR()
    for c in chunks:
        tttrlib.decode_records(c, devices.tttr_record_type(dev.record_type()), state, data)
    dec = pqusb.Decoder(dev.record_type())
    photons = [e for c in chunks for e in dec.feed(c.tolist()) if e[0] == "photon"]
    assert len(data) == len(photons) > 1000
    assert np.array_equal(np.asarray(data.macro_times), [p[2] for p in photons])
    assert np.array_equal(np.asarray(data.micro_times), [p[3] for p in photons])
    assert np.array_equal(np.asarray(data.routing_channels), [p[1] for p in photons])


@pytest.fixture(scope="module")
def device_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("dev")
    source = devices.DeviceSource(_sim(seed=7))
    session = RecordSession(source, duration_s=6.0, ptu_path=out / "sim.ptu", name="sim")
    session.start()
    result = session.wait(120)
    assert result is not None and not session.error, session.error
    return session, result


def test_the_device_timer_ends_the_run_and_the_ptu_holds_its_records(device_run):
    session, result = device_run
    assert result.stop_reason == "duration reached"
    tttr = tttrlib.TTTR(str(result.ptu))
    assert len(tttr) == result.photons
    assert tttr.header.macro_time_resolution == pytest.approx(32e-9)
    assert tttr.header.micro_time_resolution == pytest.approx(80e-12)
    assert session.source.info.n_micro == 400
    assert session.source.status()["stalls"] == 0


def test_live_equals_offline_and_burst_selection_on_the_device_recording(device_run):
    session, result = device_run
    tttr = tttrlib.TTTR(str(result.ptu))
    exp = session.experiment
    p = exp.burst
    off = analyze_offline(
        tttr,
        exp.setup,
        exp.preset,
        min_photons=p.min_photons,
        window_photons=p.window_photons,
        window_time=p.window_time_s,
    )
    assert np.array_equal(off["First Photon"], result.table["First Photon"])
    assert np.allclose(off["Proximity Ratio"], result.table["Proximity Ratio"])
    mask = burst_filter(tttr, p.min_photons, p.window_photons, p.window_time_s)
    live = np.zeros(len(tttr), bool)
    for a, b in zip(result.table["First Photon"], result.table["Last Photon"]):
        live[a : b + 1] = True
    assert np.array_equal(mask, live)
    e = result.table["Proximity Ratio"][result.table["Number of Photons"] >= 40]
    assert np.median(e[e < 0.5]) == pytest.approx(0.2, abs=0.06)
    assert np.median(e[e >= 0.5]) == pytest.approx(0.8, abs=0.06)


def test_stop_from_another_thread_ends_the_stream_and_its_reader(tmp_path):
    source = devices.DeviceSource(_sim(speed=1.0))
    session = RecordSession(source, ptu_path=tmp_path / "stop.ptu")
    session.start()
    time.sleep(1.0)
    session.stop()  # as the UI does
    result = session.wait(30)
    assert result is not None and result.stop_reason == "stopped"
    assert not any("pqusb" in t.name for t in threading.enumerate())
    assert len(tttrlib.TTTR(str(result.ptu))) == result.photons


def test_a_record_type_tttrlib_cannot_decode_is_refused():
    with pytest.raises(Exception):
        devices.tttr_record_type(0x12345678)
