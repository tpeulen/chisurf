"""``api.list_fits(statistics=True)``: every row carries the χ²ᵣ the fit window shows (found 2026-10-11).

The emtk shell's console reaches the session through ``api``; its ``list_fits()`` rows carried no
χ²ᵣ for a fit that had not been run (``chi2r`` is what the last run reached), so guide 59's
"compare χ² across every fit" had no one-liner there. ``statistics=True`` adds ``chi2r_current``.
"""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def fits(monkeypatch):
    """Two real lifetime fits (polarised description at magic angle) over simulated decays, never run."""
    import chisurf
    from chisurf.core.data import DataCurve, ExperimentDataCurveGroup
    from chisurf.core.experiments.tcspc.simulator import simulate_decay_channels
    from chisurf.core.models.description import for_family
    from chisurf.emtk.datasets import build_fit_group

    monkeypatch.setattr(chisurf, "fits", [])
    monkeypatch.setattr(chisurf, "imported_datasets", [])
    out = []
    for seed, tau in ((1, 2.0), (2, 4.0)):
        x, vv, _vh = simulate_decay_channels([1.0, tau], n_tac=256, dt=0.1, p0=5000.0, seed=seed)
        curve = DataCurve(
            x=x,
            y=vv,
            ey=np.sqrt(np.maximum(vv, 1.0)),
            name=f"decay{seed}",
            load_filename_on_init=False,
        )
        group = build_fit_group(ExperimentDataCurveGroup([curve]), for_family("tcspc_polarized"))
        group.fit_range = (10, 250)
        group.update()
        out.append(group)
    return out


def test_service_rows_carry_the_current_chi2r_on_request(fits):
    from chisurf.server.services.fits import list_fits
    from chisurf.server.session import SessionState

    state = SessionState(fits=fits)
    plain = list_fits(state)["fits"]
    assert [row["chi2r"] for row in plain] == [None, None]  # never run: nothing reached yet
    assert all("chi2r_current" not in row for row in plain)  # the default listing evaluates nothing
    rows = list_fits(state, statistics=True)["fits"]
    for fit, row in zip(fits, rows):
        assert row["chi2r_current"] == pytest.approx(fit.chi2r)
        assert row["chi2r_current"] > 0


def test_the_api_in_both_modes_answers_the_one_liner(fits):
    """Local mode lists what the server lists; ``statistics`` reaches the server through the client."""
    from chisurf.core.api import ChiSurfAPI
    from chisurf.server.services.fits import list_fits
    from chisurf.server.session import SessionState

    state = SessionState(fits=fits)
    api = ChiSurfAPI(mode="local")
    api._state = state
    local = [(f["name"], f["chi2r_current"]) for f in api.list_fits(statistics=True)]
    assert [v for _, v in local] == pytest.approx([f.chi2r for f in fits])
    assert [f["chi2r"] for f in api.list_fits()] == [None, None]

    calls = []

    class Client:
        def fit__list(self, statistics=False):
            calls.append(statistics)
            return list_fits(state, statistics=statistics)["fits"]

    remote = ChiSurfAPI(mode="local")
    remote.mode, remote.client = "server", Client()
    rows = remote.list_fits(statistics=True)
    assert calls == [True]
    assert [r["chi2r_current"] for r in rows] == pytest.approx([f.chi2r for f in fits])
