"""Native configuration, workflow and toolkit boundary tests."""

import subprocess
import sys

import numpy as np

from chisurf.plugins.burst.burst_background.gui.app import create_app
from chisurf.plugins.burst.burst_background.gui.controller import BackgroundController
from chisurf.plugins.burst.burst_background.view_model import BackgroundViewModel


def test_noqt_factories():
    code = """
import sys
from chisurf.plugins.burst.burst_background.gui.app import create_app as bg
from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app as irf
for factory in (bg, irf):
    app = factory()
    assert callable(app.draw)
    app.close()
assert not [m for m in sys.modules if m.startswith(('qtpy', 'PyQt', 'PySide'))]
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def test_files_detectors_setup_roundtrip(tmp_path):
    app = create_app()
    try:
        path = tmp_path / "measurement.ptu"
        path.touch()
        app.on_paths_dropped([path, path])
        assert app.model.files == [str(path)]
        assert app.controller.apply_detectors('{"blue":{"chs":[2],"micro_time_ranges":[[5,10]]}}')
        assert not app.controller.apply_detectors('{"bad":{"chs":[-1]}}')
        setup = tmp_path / "setup.json"
        app.controller.save_setup(setup)
        assert app.controller.load_setup(setup)
        assert app.model._channels()["blue"]["chs"] == [2]
        app.controller.clear()
        assert app.model.files == []
    finally:
        app.close()


def test_async_background_matches_direct_numerics_and_cancel(monkeypatch):
    from chisurf.core.fluorescence.burst.background import interphoton_time_diagnostics

    model = BackgroundViewModel()
    model.add_files(["measurement.ptu"])
    ctrl = BackgroundController(model)
    dt = np.random.default_rng(4).exponential(0.8, 10000)
    expected = interphoton_time_diagnostics(
        dt, binsize_ms=model.binsize_ms, tail_range_ms=(1.0, 4.0)
    ).rate_khz

    def estimate(snapshot, cancel_check=None):
        snapshot._interphoton = {"measurement.ptu": {"green": dt}}
        snapshot.fit_from_ms, snapshot.fit_to_ms = 1.0, 4.0
        snapshot.refit()

    monkeypatch.setattr(BackgroundViewModel, "estimate", estimate)
    monkeypatch.setattr(model, "_write_containers", lambda: None)
    try:
        ctrl.run()
        ctrl._future.result(timeout=5)
        ctrl.poll()
        assert np.isclose(model.backgrounds["measurement.ptu"]["green"], expected)
        previous = model.backgrounds
        ctrl.run()
        ctrl.stop()
        try:
            ctrl._future.result(timeout=5)
        except InterruptedError:
            pass
        ctrl.poll()
        assert model.backgrounds is previous
        assert "cancelled" in ctrl.status
    finally:
        ctrl.close()


def test_unreadable_measurement_is_reported(monkeypatch):
    import pytest

    from chisurf.core.fio import staging

    model = BackgroundViewModel()
    model.add_files(["missing.ptu"])
    model.channels_provider = lambda: {"green": {"chs": [0]}}

    def fail(path):
        raise OSError("missing measurement")

    monkeypatch.setattr(staging, "open_tttr", fail)
    with pytest.raises(ValueError, match="No readable TTTR"):
        model.estimate()
