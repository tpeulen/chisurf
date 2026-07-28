"""Unit tests for lightpath simulator physics logic."""

import numpy as np
import pytest
from chisurf.plugins.core.lightpath_simulator.backend.crosstalk import (
    WAVELENGTHS,
    as_transmission_fraction,
    calculate_r0,
    propagate_node,
)


class _BandpassDB:
    """Fake database serving one bandpass transmission curve.

    Parameters
    ----------
    values : numpy.ndarray
        The transmission curve to return for every probe, on
        :data:`WAVELENGTHS`.
    """

    def __init__(self, values):
        """Store the curve served by :meth:`get_probe_spectrum`."""
        self.values = values

    def __enter__(self):
        """Return the database itself, as the real adapter does."""
        return self

    def __exit__(self, *args):
        """Leave the (absent) transaction alone."""

    def get_probe_spectrum(self, probe_id, spectrum_type):
        """Return the stored curve as a ``(wavelengths, values)`` pair."""
        return WAVELENGTHS, self.values


def _bandpass(peak):
    """Return a 560 nm bandpass transmission curve with the given peak."""
    return peak * np.exp(-0.5 * ((WAVELENGTHS - 560) / 5) ** 2)


def test_calculate_r0_basic():
    """Test R0 calculation for overlapping box spectra."""
    # Create simple overlapping box spectra
    donor_em = np.zeros_like(WAVELENGTHS)
    donor_em[(WAVELENGTHS >= 480) & (WAVELENGTHS <= 520)] = 1.0
    
    acceptor_abs = np.zeros_like(WAVELENGTHS)
    acceptor_abs[(WAVELENGTHS >= 480) & (WAVELENGTHS <= 520)] = 1.0
    
    # Using typical values: QY=1, EC=100k
    r0 = calculate_r0(
        donor_em=donor_em,
        donor_qy=1.0,
        acceptor_abs=acceptor_abs,
        acceptor_ec_max=100000.0,
        kappa2=2/3,
        n=1.33
    )
    
    assert r0 > 0
    # For perfect overlap, R0 should be substantial
    assert 40 < r0 < 100


def test_calculate_r0_no_overlap():
    """Test R0 is zero when spectra do not overlap."""
    donor_em = np.zeros_like(WAVELENGTHS)
    donor_em[(WAVELENGTHS >= 350) & (WAVELENGTHS <= 400)] = 1.0
    
    acceptor_abs = np.zeros_like(WAVELENGTHS)
    acceptor_abs[(WAVELENGTHS >= 500) & (WAVELENGTHS <= 550)] = 1.0
    
    r0 = calculate_r0(
        donor_em=donor_em,
        donor_qy=1.0,
        acceptor_abs=acceptor_abs,
        acceptor_ec_max=100000.0,
        kappa2=2/3,
        n=1.33
    )
    
    assert r0 == 0.0


def test_calculate_r0_scaling():
    """Test that R0 scales correctly with QY and EC."""
    donor_em = np.zeros_like(WAVELENGTHS)
    donor_em[(WAVELENGTHS >= 480) & (WAVELENGTHS <= 520)] = 1.0
    
    acceptor_abs = np.zeros_like(WAVELENGTHS)
    acceptor_abs[(WAVELENGTHS >= 480) & (WAVELENGTHS <= 520)] = 1.0
    
    r0_ref = calculate_r0(donor_em, 1.0, acceptor_abs, 100000.0)
    
    # If QY is halved, R0 should decrease by factor of (1/2)^(1/6) approx 0.89
    r0_half_qy = calculate_r0(donor_em, 0.5, acceptor_abs, 100000.0)
    assert r0_half_qy < r0_ref
    assert pytest.approx(r0_half_qy / r0_ref, rel=1e-3) == (0.5)**(1/6)
    
    # Same for EC
    r0_half_ec = calculate_r0(donor_em, 1.0, acceptor_abs, 50000.0)
    assert pytest.approx(r0_half_ec / r0_ref, rel=1e-3) == (0.5)**(1/6)


def test_as_transmission_fraction_percent_curve_is_rescaled():
    """A curve stored in percent comes back as the matching fraction."""
    _, converted = as_transmission_fraction((WAVELENGTHS, _bandpass(58.19)))

    np.testing.assert_allclose(converted, _bandpass(0.5819), atol=1e-9)


def test_as_transmission_fraction_leaves_a_fraction_alone():
    """A curve already stored as a fraction is returned unchanged."""
    fraction = _bandpass(0.984)

    _, converted = as_transmission_fraction((WAVELENGTHS, fraction))
    np.testing.assert_allclose(converted, fraction)


def test_as_transmission_fraction_never_amplifies():
    """No transmission curve leaves the helper above unity."""
    for peak in (1.0111, 1.5, 58.19, 100.0):
        _, converted = as_transmission_fraction((WAVELENGTHS, _bandpass(peak)))
        assert converted.max() <= 1.0


def test_as_transmission_fraction_uses_the_whole_stored_range():
    """The convention is read off the stored curve, not the simulated window.

    A Thorlabs ND filter transmits a fraction of a percent and only exceeds the
    percent threshold in the near infrared, outside :data:`WAVELENGTHS`.
    """
    wavelengths = np.arange(300.0, 1101.0, 1.0)
    stored = np.full_like(wavelengths, 0.7)
    stored[wavelengths > 1000] = 1.5002

    _, converted = as_transmission_fraction((wavelengths, stored))
    assert converted.max() == pytest.approx(0.015002)


def test_filter_node_does_not_amplify_a_percent_curve():
    """A percent-stored bandpass attenuates exactly like its fraction twin.

    Pins RF-863: ``in_spec * t_y`` took the catalogue's percent curves at face
    value, so a passive Thorlabs ``FB560-10`` gained 58x instead of
    transmitting 58 %.
    """
    unit_in = {"In": {"src": np.ones_like(WAVELENGTHS)}}
    config = {"probe_id": 1201}

    percent, _ = propagate_node("filter", dict(config), unit_in, _BandpassDB(_bandpass(58.19)))
    fraction, _ = propagate_node("filter", dict(config), unit_in, _BandpassDB(_bandpass(0.5819)))

    out_percent = percent["Out"]["src"]
    np.testing.assert_allclose(out_percent, fraction["Out"]["src"], atol=1e-9)
    assert out_percent.max() <= 1.0


def test_splitter_reflects_what_a_percent_curve_does_not_transmit():
    """Reflection is ``1 - T`` rather than the clipped-to-zero remainder."""
    unit_in = {"In": {"src": np.ones_like(WAVELENGTHS)}}

    result, _ = propagate_node(
        "splitter", {"probe_id": 1201}, unit_in, _BandpassDB(_bandpass(58.19))
    )

    transmitted = result["Transmission"]["src"]
    reflected = result["Reflection"]["src"]
    np.testing.assert_allclose(transmitted + reflected, np.ones_like(WAVELENGTHS), atol=1e-9)
    assert reflected.min() == pytest.approx(1.0 - 0.5819, abs=1e-4)
