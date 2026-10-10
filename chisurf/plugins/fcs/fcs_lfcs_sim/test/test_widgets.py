"""Headless tests of the lifetime-FCS simulator's native app (the Qt widget tests, ported)."""

from __future__ import annotations

import time

import numpy as np
import pytest


def test_lfcs_app_builds_with_defaults():
    from chisurf.plugins.fcs.fcs_lfcs_sim.app import make_app

    app = make_app()
    try:
        assert app.model.tau1_ns == 1.0
        assert app.model.tau2_ns == 4.0
    finally:
        app.close()


def test_lfcs_app_simulate():
    pytest.importorskip("tttrlib")
    if not hasattr(pytest.importorskip("tttrlib"), "SimEngine"):
        pytest.skip("tttrlib build lacks SimEngine")
    from chisurf.plugins.fcs.fcs_lfcs_sim.app import make_app

    app = make_app()
    try:
        app.model.n_photons = 120_000  # keep the simulation quick for CI
        app.simulate()
        end = time.monotonic() + 120
        while app.running and time.monotonic() < end:
            time.sleep(0.05)
            app.poll()
        datasets = app.model.datasets
        # two species -> two auto-correlations + one cross-correlation
        assert {(d["species_a"], d["species_b"]) for d in datasets} == {(0, 0), (1, 1), (0, 1)}
        assert np.isfinite(app.model.condition_number)
    finally:
        app.close()
