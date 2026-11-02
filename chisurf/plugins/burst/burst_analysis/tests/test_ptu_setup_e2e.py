"""A PTU analysed from the burst hub: with no setup (one is proposed from the file) and with a setup
created in ChiSurf Settings (the library every tool shares, Record included)."""

from __future__ import annotations

import pytest

from chisurf.plugins.emtk_test_input import Driver


@pytest.fixture(scope="module")
def ptu(tmp_path_factory):
    from chisurf.plugins.core.acq.live.session import RecordSession
    from chisurf.plugins.core.acq.live.sources import SimulatedPieSource

    out = tmp_path_factory.mktemp("ptu")
    session = RecordSession(
        SimulatedPieSource(duration_s=None, realtime=False, seed=11),
        duration_s=6.0,
        ptu_path=out / "sim_pie.ptu",
        name="sim_pie",
    )
    session.start()
    result = session.wait(120)
    assert result is not None and not session.error, session.error
    return result.ptu


@pytest.fixture
def env(tmp_path, monkeypatch):
    for key, folder in (("CHISURF_SETTINGS_DIR", "s"), ("MMFDB_SETTINGS_DIR", "m")):
        monkeypatch.setenv(key, str(tmp_path / folder))
        (tmp_path / folder).mkdir()
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))


def test_a_definition_without_detectors_is_proposed_from_the_measurement(env, ptu):
    from chisurf.core.setup_channel_definition import ChannelDefinition

    model = ChannelDefinition()
    model.read_tttr(ptu)
    # two-colour PIE: donor and acceptor on the prompt window, the acceptor again on the delayed
    assert {n: d["chs"] for n, d in model.data["detectors"].items()} == {
        "green": [0], "red": [1], "yellow": [1]
    }
    windows = model.data["windows"]
    assert set(windows) == {"prompt", "delayed"}
    assert windows["prompt"][0] < 300  # the pulse is inside its window (instrument delay)
    gates = {n: d["micro_time_ranges"] for n, d in model.data["detectors"].items()}
    assert gates == {"green": [windows["prompt"]], "red": [windows["prompt"]],
                     "yellow": [windows["delayed"]]}

    kept = ChannelDefinition({"detectors": {"mine": {"chs": [1]}}})
    kept.read_tttr(ptu)
    assert list(kept.data["detectors"]) == ["mine"]  # a proposal never overwrites a definition


def test_a_ptu_is_analysed_without_any_stored_setup(env, ptu):
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app, receive_photons
    from chisurf.plugins.burst.burst_analysis.tests.test_emtk_native_hub import settle

    hub = create_app()
    try:
        drv = Driver(hub)
        drv.draw(3)
        receive_photons(hub, {"files": [str(ptu)]})
        drv.draw(2)
        assert list(hub.children["setup"].selected_setup_data()["detectors"]) == [
            "green", "red", "yellow"
        ]
        hub.select("selection")
        drv.draw(2)
        drv.click(hub.item_rects["next"])
        settle(drv)
        assert hub.children["selection"].model.n_bursts > 20, hub.status
        assert not hub.errors
    finally:
        hub.close()


def test_a_setup_made_in_settings_is_chosen_in_the_hub_and_in_record(env, ptu, tmp_path):
    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app
    from chisurf.plugins.core.acq.gui.record_app import RecordModel

    settings = ChannelDefinition()
    settings.read_tttr(ptu)
    settings.save_setup("lab_pie")

    hub = create_app()
    try:
        Driver(hub).draw(3)
        assert hub.children["setup"].selected_setup_name() == "lab_pie"
    finally:
        hub.close()

    record = RecordModel(output_dir=tmp_path)
    assert ("library:lab_pie", "Setup: lab_pie") in record.setup_options()
    record.setup_address = "library:lab_pie"
    exp = record.make_experiment(4096, 8e-12)
    assert set(exp.setup["detectors"]) == {"green", "red", "yellow"} and exp.preset == "pie"


def test_a_recorded_ptu_carries_its_micro_time_channels_and_laser_period(ptu):
    """Without them every reader took one channel per period and each lifetime fit of it failed."""
    import tttrlib

    from chisurf.plugins.burst.burst_mle_analysis.engine import header_time_ns

    tttr = tttrlib.TTTR(str(ptu))
    assert tttr.header.number_of_micro_time_channels == 4000
    dt, period = header_time_ns(tttr, 1)
    assert dt == pytest.approx(0.008) and period == pytest.approx(32.0)


def test_a_container_older_than_its_file_is_set_aside(env, ptu, tmp_path):
    import os
    import shutil

    from chisurf.core.fio.fluorescence.burst_container import container_for, open_measurement

    raw = tmp_path / "m.ptu"
    shutil.copy(ptu, raw)
    with open_measurement(raw):
        pass
    target = container_for(raw)
    os.utime(raw, (target.stat().st_mtime + 10, target.stat().st_mtime + 10))  # re-recorded
    with open_measurement(raw):
        pass
    assert len(list(tmp_path.glob("m.stale-*.pto"))) == 1 and target.exists()


def test_burst_mle_fits_inside_the_gates_of_the_step0_setup(env, ptu):
    """Step 0's PIE gate bounds the MLE fit of each detector, both polarisations, one channel or two."""
    from chisurf.plugins.burst.burst_mle_analysis import engine

    session = engine.MleSession()
    session.set_definition(
        {
            "detectors": {
                "Donor": {"chs": [0], "micro_time_ranges": [[0, 2000]]},
                "Acceptor": {"chs": [1], "micro_time_ranges": [[2000, 4000]]},
            }
        }
    )
    assert list(session.detectors) == ["Donor", "Acceptor"]
    cfg = session.batch_config("Donor")
    assert (cfg["sb"], cfg["eb"], cfg["vh_sb"], cfg["vh_eb"]) == (0, 2000, 0, 2000)
    cfg = session.batch_config("Acceptor")
    assert (cfg["sb"], cfg["eb"]) == (2000, 4000)


def test_a_saved_setup_keeps_its_detector_order(env):
    from chisurf.core.setup_channel_definition import ChannelDefinition

    saved = ChannelDefinition()
    saved.data["detectors"] = {"Donor": {"chs": [0]}, "Acceptor": {"chs": [1]}}
    saved.save_setup("ordered")
    loaded = ChannelDefinition()
    loaded.refresh_setups()
    assert list(loaded.setups["ordered"]["detectors"]) == ["Donor", "Acceptor"]
