"""Native FCS settings, ranges, cancellation and numerical results."""

import json
from concurrent.futures import CancelledError

import numpy as np

from chisurf.plugins.burst.burst_fcs_correlator.core import algorithms as core
from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app


def test_native_settings_pairs_and_actual_ranges_roundtrip(tmp_path):
    app = create_app()
    ctrl = app.controller
    try:
        raw = tmp_path / "measurement.ptu"
        raw.touch()
        bst = tmp_path / "measurement.ptu.bst"
        bst.write_text("0 100\n200 400\n")
        app.on_paths_dropped([bst])
        assert ctrl.resolve_files() == [(raw, [(0, 100), (200, 400)])]
        assert ctrl.apply_pairs('[{"pair_name":"cross","chs_a":[0],"chs_b":[1]}]')
        assert not ctrl.apply_pairs('[{"pair_name":"bad","chs_a":[],"chs_b":[1]}]')
        ctrl._model.n_bins = 5
        ctrl._model.maxent_log10_reg = -2
        settings = tmp_path / "settings.json"
        ctrl.save_settings(settings)
        ctrl._model.n_bins = 3
        ctrl.load_settings(settings)
        assert ctrl._model.n_bins == 5
        assert ctrl._model.maxent_log10_reg == -2
    finally:
        app.close()


def test_native_correlation_publishes_real_fits_and_preserves_on_cancel(tmp_path, monkeypatch):
    app = create_app()
    ctrl = app.controller
    raw = tmp_path / "measurement.ptu"
    raw.touch()
    bst = tmp_path / "measurement.ptu.bst"
    bst.write_text("0 100\n")
    ctrl.add_files([bst])
    tau = np.logspace(-3, 2, 60)
    g = 1 + 0.5 / (1 + tau) / np.sqrt(1 + tau / 3.5**2)
    fit = core.fit_curve(tau, g, core.BurstFcsSettings())

    def correlate(*args, **kwargs):
        return [
            {
                "file": "measurement.ptu",
                "pair_name": "donor_ACF",
                "burst_index": 0,
                "tau_raw": tau.tolist(),
                "g_raw": g.tolist(),
                **fit,
            }
        ]

    monkeypatch.setattr(core, "correlate_burst_file", correlate)
    try:
        ctrl._on_run()
        ctrl._future.result(timeout=5)
        ctrl.poll()
        assert 0.5 < ctrl._model._selected["td_mean"] < 2
        assert ctrl._model.corr_plot_series()
        output = tmp_path / "curves.json"
        ctrl.export_curves(output)
        assert json.loads(output.read_text())[0]["pair_name"] == "donor_ACF"
        previous = ctrl._curves
        ctrl._on_run()
        ctrl.stop()
        try:
            ctrl._future.result(timeout=5)
        except CancelledError:
            pass
        ctrl.poll()
        assert ctrl._curves is previous
    finally:
        app.close()
