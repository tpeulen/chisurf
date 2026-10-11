"""Known-field producer, pair cache and actual native demo action contracts."""

import json
from pathlib import Path

import pytest


def test_demo_primary_path_and_plugin_settings_folder(tmp_path, monkeypatch):
    """The producer owns one settings folder and returns its primary sample."""
    from chisurf.plugins.microscopy.spot_finder import demo

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    assert demo.demo_folder() == tmp_path / "settings" / "demos" / "spot_finder"
    path = demo.make_demo()
    assert isinstance(path, Path)
    assert path.parent == demo.demo_folder()
    assert path.with_name(demo.IRF_FILENAME).is_file()
    assert json.loads(path.with_suffix(".json").read_text()) == demo.DEMO


@pytest.mark.parametrize("damage", ["sample", "irf", "sidecar", "settings", "overwrite"])
def test_cache_requires_the_whole_pair_and_matching_parameters(tmp_path, monkeypatch, damage):
    """A cached sample cannot hide a missing IRF or stale scanner declaration."""
    from chisurf.core.fluorescence.imaging import simulate
    from chisurf.plugins.microscopy.spot_finder import demo

    path = demo.make_demo(tmp_path)
    calls = []
    original = simulate.simulate_molecule_mixture

    def tracked(*args, **kwargs):
        """Observe regeneration without changing the physical producer."""
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(simulate, "simulate_molecule_mixture", tracked)
    assert demo.make_demo(tmp_path) == path
    assert not calls
    if damage == "sample":
        path.unlink()
    elif damage == "irf":
        path.with_name(demo.IRF_FILENAME).unlink()
    elif damage == "sidecar":
        path.with_suffix(".json").unlink()
    elif damage == "settings":
        path.with_suffix(".json").write_text(json.dumps({**demo.DEMO, "seed": -1}))
    assert demo.make_demo(tmp_path, overwrite=damage == "overwrite") == path
    assert len(calls) == 2  # Sample and matching IRF both use the mixture simulator.
    assert path.with_name(demo.IRF_FILENAME).is_file()
    assert json.loads(path.with_suffix(".json").read_text()) == demo.DEMO


def test_actual_demo_button_releases_tour_only_after_user_click(tmp_path, monkeypatch):
    """Starting a guide waits for the real declared load action and does not compute."""
    from emtk.testing import Driver

    from chisurf.plugins.microscopy.spot_finder.gui.app import make_app

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    app = make_app()
    drv = Driver(app, (1400, 1000))
    drv.frame(3)
    assert "load_example" in drv.ids()
    assert app.tour.steps[1]["target"] == {"name": "load_example"}
    app.tour.start(1)
    drv.frame(2)
    assert app.tour.awaiting
    assert not app.job.busy
    assert not app.model.files
    drv.click("load_example")
    assert not app.tour.awaiting
    if app.job.thread:
        app.job.thread.join(45)
    app.job.poll()
    assert not app.job.error
    assert len(app.model.files) == 1
    assert not app.model.results
    app.tour.stop()
    assert app.start("run")
    app.job.thread.join(45)
    app.job.poll()
    assert not app.job.error
    assert app.model.results[0].n_regions == 4


def test_region_mle_loads_the_matching_explicit_irf(tmp_path, monkeypatch):
    """The neighboring fit loader retains its same pair and detected region settings."""
    from chisurf.plugins.microscopy.region_mle.gui.view_model import RegionMleViewModel
    from chisurf.plugins.microscopy.spot_finder import demo

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    model = RegionMleViewModel()
    sample = Path(model.load_demo())
    assert model.files == [str(sample)]
    assert model.irf_files == [str(sample.with_name(demo.IRF_FILENAME))]
    assert model.settings.regions == str(sample)
    assert model.settings.region_set == "spots"


@pytest.mark.parametrize("overwrite", [False, True])
def test_existing_cache_overwrite_changes_the_actual_photon_streams(
    tmp_path, monkeypatch, overwrite
):
    """Changing a declared seed replaces both existing streams, not just their sidecar."""
    import numpy as np
    import tttrlib

    from chisurf.plugins.microscopy.spot_finder import demo

    sample = demo.make_demo(tmp_path)
    irf = sample.with_name(demo.IRF_FILENAME)
    before = [np.asarray(tttrlib.TTTR(str(p), "PTU").micro_times).copy() for p in (sample, irf)]
    monkeypatch.setitem(demo.DEMO, "seed", demo.DEMO["seed"] + 1)
    monkeypatch.setitem(demo.DEMO, "irf_seed", demo.DEMO["irf_seed"] + 1)
    demo.make_demo(tmp_path, overwrite=overwrite)
    after = [np.asarray(tttrlib.TTTR(str(p), "PTU").micro_times).copy() for p in (sample, irf)]
    assert all(not np.array_equal(a, b) for a, b in zip(before, after))
    reference = demo.make_demo(tmp_path / "fresh")
    for actual_path, fresh_path in zip(
        (sample, irf), (reference, reference.with_name(demo.IRF_FILENAME))
    ):
        actual, fresh = (tttrlib.TTTR(str(p), "PTU") for p in (actual_path, fresh_path))
        for attr in ("macro_times", "micro_times", "routing_channels"):
            assert np.array_equal(
                np.asarray(getattr(actual, attr)), np.asarray(getattr(fresh, attr))
            )
        assert actual.header.micro_time_resolution == fresh.header.micro_time_resolution
        assert actual.header.macro_time_resolution == fresh.header.macro_time_resolution
    assert json.loads(sample.with_suffix(".json").read_text()) == demo.DEMO


@pytest.mark.parametrize("member", ["sample", "irf"])
def test_short_corrupt_cache_member_is_replaced(tmp_path, member):
    """An existing invalid file must be rewritten as readable physical photons."""
    import numpy as np
    import tttrlib

    from chisurf.plugins.microscopy.spot_finder import demo

    sample = demo.make_demo(tmp_path)
    irf = sample.with_name(demo.IRF_FILENAME)
    paths = (sample, irf)
    expected = [np.asarray(tttrlib.TTTR(str(p), "PTU").micro_times).copy() for p in paths]
    damaged = sample if member == "sample" else irf
    damaged.write_bytes(b"corrupted")
    demo.make_demo(tmp_path)
    assert damaged.stat().st_size > 10000
    actual = [np.asarray(tttrlib.TTTR(str(p), "PTU").micro_times).copy() for p in paths]
    assert all(np.array_equal(a, b) for a, b in zip(expected, actual))
