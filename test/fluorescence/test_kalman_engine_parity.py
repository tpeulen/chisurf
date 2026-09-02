"""Kalman burst search: the engine is primary, the Python recursion is the
fallback, and the two agree in kind on a real measurement.

The compiled ``tttrlib`` search became the path every caller takes
(``chisurf.core.fluorescence.burst.kalman.kalman_filter``); the in-tree Python
recursion is retained beneath it for a build whose ``tttrlib`` predates
``burst_search_kalman``, and is exercised here so it cannot rot unnoticed.

Parity is asserted *in kind*, not bin-for-bin, and that is a property of the
fallback rather than a tolerance chosen to make a test pass. The Python path
is handed per-channel float timestamps and

* bins with ``np.histogram(range=(0, tmax))``, whose width is
  ``tmax / ceil(tmax / dt)`` rather than the ``dt`` asked for, and
* recovers photon indices by ``searchsorted`` on float seconds.

Run on the bundled BH SPC132 single-molecule measurement (~174 k photons, real
burst counts) rather than a synthetic array.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
import tttrlib

from chisurf.core.fluorescence.burst import kalman as kalman_mod

_SPC = (
    pathlib.Path(__file__).resolve().parents[2]
    / "chisurf" / "plugins" / "burst" / "burst_selection" / "tests"
    / "data" / "bh_spc132_sm_dna" / "m000.spc"
)

_PARAMS = dict(min_ph=20, dt=1e-3, q=20.0, r_scale=1.0, z_thresh=3.0,
               min_len=2, merge_gap=20, per_channel=True)


@pytest.fixture(scope="module")
def tttr():
    assert _SPC.exists(), _SPC
    return tttrlib.TTTR(str(_SPC), "SPC-130")


def test_engine_is_the_primary_path(tttr, monkeypatch):
    """On a build with the engine, the Python recursion is never entered."""
    assert kalman_mod.engine_is_available()

    def _boom(*a, **kw):
        raise AssertionError("fallback ran while the engine was available")

    monkeypatch.setattr(kalman_mod, "_python_kalman_burst_search", _boom)
    bursts = kalman_mod.kalman_burst_search(tttr, **_PARAMS)
    assert bursts.ndim == 2 and bursts.shape[1] == 2


def test_engine_bursts_are_well_formed(tttr):
    """Inclusive ``[start, stop]`` photon indices, ordered and in range."""
    bursts = kalman_mod.kalman_burst_search(tttr, **_PARAMS)
    assert len(bursts) > 0
    assert (bursts[:, 0] <= bursts[:, 1]).all()
    assert bursts[:, 0].min() >= 0
    assert bursts[:, 1].max() < len(tttr)
    # ``Number of Photons == stop - start + 1``: the inclusive-stop convention
    # the .bur writer and the companion readers share.
    assert (bursts[:, 1] - bursts[:, 0] + 1 >= _PARAMS["min_ph"]).all()


def test_mask_matches_the_burst_ranges(tttr):
    """``kalman_filter`` is exactly ``kalman_burst_search`` as a photon mask."""
    bursts = kalman_mod.kalman_burst_search(tttr, **_PARAMS)
    mask = kalman_mod.kalman_filter(tttr, **_PARAMS)

    assert mask.dtype == np.bool_ and mask.shape == (len(tttr),)
    expected = np.zeros(len(tttr), dtype=bool)
    for start, stop in bursts:
        expected[start:stop + 1] = True  # inclusive stop
    np.testing.assert_array_equal(mask, expected)


def test_fallback_still_runs_and_agrees_in_kind(tttr, monkeypatch):
    """Forcing the engine away exercises the retained Python recursion."""
    monkeypatch.setattr(kalman_mod, "engine_is_available", lambda: False)
    fallback = kalman_mod.kalman_filter(tttr, **_PARAMS)

    monkeypatch.undo()
    engine = kalman_mod.kalman_filter(tttr, **_PARAMS)

    assert fallback.shape == engine.shape == (len(tttr),)
    assert fallback.any() and engine.any()

    # Same population, not the same bins: see the module docstring for why an
    # exact comparison would be pinning the fallback's binning bug.
    ratio = float(fallback.sum()) / float(engine.sum())
    assert 0.2 < ratio < 5.0, (int(fallback.sum()), int(engine.sum()))
    overlap = float((fallback & engine).sum()) / float((fallback | engine).sum())
    assert overlap > 0.3, overlap
