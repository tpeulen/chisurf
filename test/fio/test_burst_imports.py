"""The burst-search modules expose one shape, and it forwards to the engine.

This file used to be a script that printed the two ``convert_bursts_to_start_stop``
functions to prove a name collision had been resolved -- it had no assertions and
pinned nothing about what the modules compute. The property worth pinning is that
each search module is a wrapper over its ``tttrlib`` engine entry point rather
than a second implementation of the algorithm.
"""

import inspect
import pathlib

import numpy as np
import pytest
import tttrlib

import chisurf.core.fluorescence.burst as burstmod

_SPC_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "chisurf" / "plugins" / "burst" / "burst_selection" / "tests"
    / "data" / "bh_spc132_sm_dna" / "m000.spc"
)


def test_each_search_module_exposes_a_filter():
    """Every search in the package is reached the same way."""
    for name in ("bocpd_filter", "cusum_filter", "count_rate_filter", "kalman_filter"):
        assert callable(getattr(burstmod, name)), name


@pytest.mark.parametrize(
    "module, entry_point",
    [
        ("bocpd", "burst_search_bocpd"),
        ("cusum", "burst_search"),
        ("kalman", "burst_search_kalman"),
        ("count_rate", "get_selection_by_count_rate"),
    ],
)
def test_search_modules_call_the_engine(module, entry_point):
    """The module body names the tttrlib entry point it forwards to.

    A reimplementation would not need to, which is what makes this a useful
    tripwire against the Python arithmetic creeping back in.
    """
    mod = getattr(burstmod, module)
    assert entry_point in inspect.getsource(mod)
    assert hasattr(tttrlib.TTTR, entry_point)


def test_kalman_entry_points_prefer_the_engine():
    """``kalman_filter`` reaches the engine first, not the Python recursion.

    The recursion is still there -- it is the fallback for a tttrlib that
    predates ``burst_search_kalman``, and deleting it is the fallback audit's
    call, not the forwarding change's. What this pins is the *order*: on a
    build that has the engine, the Python path must not run.
    """
    src = inspect.getsource(burstmod.kalman.kalman_burst_search)
    assert "burst_search_kalman" in src
    # The fallback is retained and reachable, not deleted.
    assert callable(burstmod.kalman.KalmanBurstDetector)
    assert callable(burstmod.kalman.kalman_burst_detection_multi)
    assert callable(burstmod.kalman._python_kalman_burst_search)


def test_kalman_engine_is_used_when_available(monkeypatch):
    """With the engine present the fallback is not entered."""
    assert burstmod.kalman.engine_is_available()

    def _boom(*a, **kw):
        raise AssertionError("Python fallback ran while the engine was available")

    monkeypatch.setattr(burstmod.kalman, "_python_kalman_burst_search", _boom)
    tttr = tttrlib.TTTR(str(_SPC_FIXTURE), "SPC-130")
    mask = burstmod.kalman_filter(tttr, min_ph=20, dt=1e-3, q=20.0, z_thresh=3.0)
    assert mask.shape == (len(tttr),)


def test_bva_module_is_only_the_static_line():
    """BVA itself is ``tttrlib.BVA``; the core module keeps the reference line."""
    from chisurf.core.fluorescence.burst import bva

    assert not hasattr(bva, "compute_bva")
    assert callable(bva.compute_static_bva_line)


def test_kalman_filter_returns_a_photon_mask():
    """The forwarder returns a boolean mask the length of the photon stream."""
    tttr = tttrlib.TTTR(str(_SPC_FIXTURE), "SPC-130")
    mask = burstmod.kalman_filter(tttr, min_ph=20, dt=1e-3, q=20.0, z_thresh=3.0)
    assert mask.dtype == np.bool_
    assert mask.shape == (len(tttr),)
    assert mask.any()
