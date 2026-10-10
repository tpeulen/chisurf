"""The shipped demo has a known answer: twelve planted bursts."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_selection.demo import (
    N_BURSTS,
    PHOTONS_PER_BURST,
    RED_FRACTION,
    SETUP,
    make_demo,
)


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    return tmp_path


def test_demo_is_cached_and_regenerated_on_damage(tmp_path):
    path = make_demo(tmp_path)
    stamp = path.stat().st_mtime_ns
    assert make_demo(tmp_path) == path and path.stat().st_mtime_ns == stamp
    path.with_suffix(".json").write_text("{}")
    make_demo(tmp_path)
    assert "sha256" in path.with_suffix(".json").read_text()


def test_the_search_finds_every_planted_burst(hermetic):
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    model = BurstSelectionModel()
    model.set_setup({**SETUP, "setup_name": ""})
    assert model.add_paths([make_demo(hermetic / "data")]) == 1
    assert model.prepare_run() is None
    model.run()
    rows = model.burst_rows()
    assert len(rows) == N_BURSTS
    photons = np.array([float(r["Number of Photons"]) for r in rows])
    assert photons.mean() == pytest.approx(PHOTONS_PER_BURST, rel=0.05)
    red = np.array([float(r["Number of Photons (red)"]) for r in rows])
    assert (red / photons).mean() == pytest.approx(RED_FRACTION, abs=0.05)


def test_load_example_adds_the_stream_and_the_tour_step_is_released(hermetic):
    from chisurf.plugins.burst.burst_selection.gui.native import BurstSelectionNativeApp

    app = BurstSelectionNativeApp(restore=False)
    try:
        app.example_folder = hermetic / "data"
        app.tour.start(1)
        assert app.tour.awaiting
        app.load_example()
        assert not app.tour.awaiting
        assert [p.name for p in app.model.files] == ["bs_demo.spc"]
        assert app.run()
    finally:
        app.close()
