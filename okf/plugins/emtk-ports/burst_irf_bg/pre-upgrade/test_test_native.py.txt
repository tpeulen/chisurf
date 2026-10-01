"""Toolkit-free IRF actions retain numerical patterns and MLE handoff."""

import numpy as np

from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app
from chisurf.plugins.burst.burst_irf_bg.gui.view_model import IrfBackgroundViewModel


def test_native_irf_patterns_handoff_export_and_cancel(tmp_path, monkeypatch):
    received = []
    app = create_app(mle_receiver=lambda patterns: received.append(patterns) or len(patterns))
    app.model.add_files(["measurement.ptu"])

    def compute(snapshot, cancel_check=None):
        snapshot._display = {
            "green": {
                "time_ns": np.arange(4.0),
                "irf": np.array([0.0, 0.2, 0.6, 0.2]),
                "background_khz": 1.25,
            }
        }
        snapshot._mle = {"green": {"irf": np.array([0.0, 0.2, 0.6, 0.2]), "bg": np.ones(4)}}

    monkeypatch.setattr(IrfBackgroundViewModel, "compute", compute)
    try:
        assert not app.controller.send_to_mle()
        app.controller.run()
        app.controller._future.result(timeout=5)
        app.controller.poll()
        assert np.isclose(app.model.irf_series()[0]["y"].sum(), 1)
        assert app.controller.send_to_mle()
        assert received[0]["green"]["bg"].sum() == 4
        export = tmp_path / "patterns.npz"
        app.controller.export_patterns(export)
        with np.load(export) as patterns:
            np.testing.assert_allclose(patterns["green/irf"], [0.0, 0.2, 0.6, 0.2])
        previous = app.model._display
        app.controller.run()
        app.controller.stop()
        try:
            app.controller._future.result(timeout=5)
        except InterruptedError:
            pass
        app.controller.poll()
        assert app.model._display is previous
    finally:
        app.close()


def test_native_real_photon_results_match_direct_model():
    from pathlib import Path

    import pytest

    data = (
        Path(__file__).resolve().parents[3]
        / "burst"
        / "burst_selection"
        / "tests"
        / "data"
        / "bh_spc132_sm_dna"
        / "m000.spc"
    )
    if not data.exists():
        pytest.skip("sample SPC unavailable")
    app = create_app()
    direct = IrfBackgroundViewModel()
    direct.add_files([str(data)])
    direct.channels_provider = app.model.channels_provider
    direct.min_photons = app.model.min_photons = 20
    direct.compute()
    try:
        app.model.add_files([str(data)])
        app.controller.run()
        app.controller._future.result(timeout=30)
        app.controller.poll()
        for name, patterns in direct.mle_patterns().items():
            for key, expected in patterns.items():
                np.testing.assert_allclose(app.model.mle_patterns()[name][key], expected)
        assert app.model.results_rows() == direct.results_rows()
    finally:
        app.close()
