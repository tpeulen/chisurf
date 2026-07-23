"""Tests for the RCM (routing-correction-matrix) calibration from dye solutions."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fret.calibration import rcm_from_dye_solutions


def test_two_channel_shape_and_normalisation():
    # ch0 = acceptor detector, ch1 = donor detector, mild cross-talk.
    donor = [0.1, 1.0]        # donor solution leaks a bit into the A channel
    acceptor = [1.0, 0.05]    # acceptor solution leaks a bit into the D channel
    rcm = rcm_from_dye_solutions(donor, acceptor, absorbance_ratio=1.0,
                                 detector_assignment=[("A", "P"), ("D", "P")])
    assert rcm.shape == (2, 2)
    # normalised so the first ordered (A) element is 1.
    assert rcm[0, 0] == pytest.approx(1.0)


def test_no_crosstalk_gives_diagonal():
    """Clean channels (no leakage) -> a diagonal correction matrix."""
    donor = [0.0, 2.0]
    acceptor = [1.0, 0.0]
    rcm = rcm_from_dye_solutions(donor, acceptor, absorbance_ratio=1.0,
                                 detector_assignment=[("A", "P"), ("D", "P")])
    assert abs(rcm[0, 1]) < 1e-12 and abs(rcm[1, 0]) < 1e-12


def test_four_channel_polarised():
    # A-P, D-P, A-S, D-S
    assignment = [("A", "P"), ("D", "P"), ("A", "S"), ("D", "S")]
    donor = [0.05, 1.0, 0.05, 1.0]
    acceptor = [1.0, 0.05, 1.0, 0.05]
    rcm = rcm_from_dye_solutions(donor, acceptor, absorbance_ratio=1.2,
                                 detector_assignment=assignment,
                                 anisotropy=(0.2, 0.15))
    assert rcm.shape == (4, 4)
    assert np.all(np.isfinite(rcm))


def test_validation_errors():
    with pytest.raises(ValueError):
        rcm_from_dye_solutions([1, 2], [1, 2], 1.0, [("A", "P")])  # length mismatch
    with pytest.raises(ValueError):
        rcm_from_dye_solutions([1, 2], [1, 2], 1.0,
                               [("A", "P"), ("A", "P")])           # no D channel
