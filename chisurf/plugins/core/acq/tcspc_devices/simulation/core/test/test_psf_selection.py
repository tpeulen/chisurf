"""``psf_type`` selects the excitation focus, or the call fails.

The four focus shapes used to be an ``elif <name> and hasattr(SimGrid, ...)``
chain ending in the plain 3-D Gaussian, so a typo or a photon library built
without one of the constructors simulated a *different optical model* than the
one asked for and reported nothing. That is invisible to a construction test —
the run succeeds and the numbers are simply from another PSF — so what is
asserted here is that the setting **changes the answer**, and that a name
nothing can build is rejected rather than substituted.

A missing constructor needs no test of its own: the call is now unguarded, so
it fails on the attribute.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
    build_engine,
    tttrlib_available,
)

pytestmark = pytest.mark.skipif(
    not tttrlib_available(), reason="tttrlib SimEngine not available"
)


def _params(**overrides):
    """A small, fast, single-species simulation; ``overrides`` go on top."""
    params = {
        "N_species": 1, "N_channels": 1, "q": [80.0], "D": [3.0], "M": [30.0],
        "N_tac_channels": 256, "tac_dt": 0.032, "laser_period": 16.0,
        "N_ph_max": 60000, "decay_lifetimes": [[1.0, 1.0]],
        "rmt1seed": 4242, "rmt2seed": 2424,
    }
    params.update(overrides)
    return params


def _arrival_times(psf_type):
    """Photon arrival times of one run — the PSF's fingerprint on the stream."""
    engine = build_engine(_params(psf_type=psf_type))
    engine.run()
    return np.asarray(engine.arrival_time()).astype(float)


def test_the_focus_shape_changes_the_photon_stream():
    """A Gauss-Lorentz focus is not a 3-D Gaussian focus, and it must show.

    Same seeds, same sample, same detector — only ``psf_type`` differs. If the
    two streams came out identical the selection did nothing, which is exactly
    what the old ``hasattr`` chain did whenever a constructor was missing.
    """
    gaussian = _arrival_times("gaussian3d")
    gauss_lorentz = _arrival_times("gaussian_lorentzian")
    assert gaussian.size > 100 and gauss_lorentz.size > 100
    assert gaussian.size != gauss_lorentz.size or not np.array_equal(
        gaussian, gauss_lorentz
    ), "psf_type did not change the simulation"


def test_an_unknown_psf_type_is_rejected():
    """A typo must not quietly become the default Gaussian."""
    with pytest.raises(ValueError, match="unknown psf_type"):
        build_engine(_params(psf_type="gauss3d"))
