"""A curve written as a kristine ``.cor`` file must read back unchanged.

`write_kristine` used to transpose the uncertainty branch twice, so it wrote
``n_columns`` rows of ``n_points`` values: a 20-point curve came back as four
correlation points with an acquisition time of 0.0043 s instead of 10.0 s —
silent, total corruption of a saved dataset. Passing a mask on top of that
raised a shape error from ``np.vstack``. Both paths are live (`write_single_fcs`
always passes ``ey``, and the ``fcs_convert`` CLI routes user conversions
through it), so the guardrail is a writer -> reader round trip.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fio.fluorescence.fcs.kristine import read_kristine, write_kristine

N_POINTS = 20

KRISTINE_COR = (
    pathlib.Path(__file__).parent.parent / "data" / "fcs" / "kristine" / "Kristine_with_error.cor"
)


@pytest.fixture()
def curve():
    """Build a 20-point correlation curve with uncertainties and a mask."""
    correlation_time = np.logspace(-6, 1, N_POINTS)
    correlation_amplitude = 1.0 + 0.5 / (1.0 + correlation_time / 1e-3)
    uncertainty = 0.01 * correlation_amplitude
    mask = np.ones(N_POINTS)
    mask[3] = 0.0
    return correlation_time, correlation_amplitude, uncertainty, mask


def test_a_curve_with_uncertainties_round_trips(tmp_path, curve):
    """The four-column layout keeps every point and both metadata values."""
    correlation_time, correlation_amplitude, uncertainty, _ = curve
    filename = str(tmp_path / "with_error.cor")

    write_kristine(
        filename=filename,
        correlation_time=correlation_time,
        correlation_amplitude=correlation_amplitude,
        correlation_amplitude_uncertainty=uncertainty,
        acquisition_time=10.0,
        mean_countrate=50.0,
        verbose=False,
    )

    # One row per correlation point, not one row per column.
    assert np.loadtxt(filename).shape == (N_POINTS, 4)

    ds = read_kristine(filename)[0]
    assert len(ds["correlation_times"]) == N_POINTS
    assert ds["acquisition_time"] == pytest.approx(10.0)
    assert ds["mean_count_rate"] == pytest.approx(50.0)
    assert np.allclose(ds["correlation_times"], correlation_time)
    assert np.allclose(ds["correlation_amplitudes"], correlation_amplitude)
    assert np.allclose(ds["correlation_amplitude_weights"], 1.0 / uncertainty)


def test_a_mask_is_written_behind_the_uncertainties(tmp_path, curve):
    """The five-column layout puts the mask in the column the reader reads."""
    correlation_time, correlation_amplitude, uncertainty, mask = curve
    filename = str(tmp_path / "with_mask.cor")

    write_kristine(
        filename=filename,
        correlation_time=correlation_time,
        correlation_amplitude=correlation_amplitude,
        correlation_amplitude_uncertainty=uncertainty,
        mask=mask,
        acquisition_time=10.0,
        mean_countrate=50.0,
        verbose=False,
    )

    assert np.loadtxt(filename).shape == (N_POINTS, 5)

    ds = read_kristine(filename)[0]
    assert np.allclose(ds["mask"], mask)
    assert np.allclose(ds["correlation_amplitude_weights"], 1.0 / uncertainty)
    assert ds["acquisition_time"] == pytest.approx(10.0)


def test_a_curve_without_uncertainties_round_trips(tmp_path, curve):
    """The three-column layout was already correct and stays that way."""
    correlation_time, correlation_amplitude, _, _ = curve
    filename = str(tmp_path / "no_error.cor")

    write_kristine(
        filename=filename,
        correlation_time=correlation_time,
        correlation_amplitude=correlation_amplitude,
        acquisition_time=10.0,
        mean_countrate=50.0,
        verbose=False,
    )

    assert np.loadtxt(filename).shape == (N_POINTS, 3)

    ds = read_kristine(filename)[0]
    assert len(ds["correlation_times"]) == N_POINTS
    assert ds["acquisition_time"] == pytest.approx(10.0)
    assert ds["mean_count_rate"] == pytest.approx(50.0)


def test_a_measured_curve_survives_the_public_writer(tmp_path):
    """`write_fcs` -> `read_fcs` on a real file, the path the CLI converter uses.

    The curve carries both uncertainties and a mask, which is the combination
    that used to raise from ``np.vstack`` before anything was written.
    """
    import chisurf.core.fio.fluorescence.fcs as fcs

    if not KRISTINE_COR.exists():
        pytest.skip("Test data not found")
    original = fcs.read_fcs(filename=str(KRISTINE_COR), reader_name="kristine")
    filename = str(tmp_path / "converted.cor")

    fcs.write_fcs(original, filename, "kristine", verbose=False)

    written = fcs.read_fcs(filename=filename, reader_name="kristine")
    assert len(written[0].x) == len(original[0].x)
    assert np.allclose(written[0].x, original[0].x)
    assert np.allclose(written[0].y, original[0].y)


def test_a_zero_uncertainty_does_not_become_an_infinite_weight(tmp_path, curve):
    """A merged curve has exact zeros where its repeats agreed (RF-731).

    The reader inverts the uncertainty column elementwise, so those points used
    to come back as ``inf`` weights — with nothing but a stderr RuntimeWarning
    — and a fit consuming the dataset was then decided by them alone.
    """
    correlation_time, correlation_amplitude, uncertainty, _ = curve
    uncertainty = uncertainty.copy()
    uncertainty[[5, 11, 17]] = 0.0
    filename = str(tmp_path / "zero_error.cor")

    write_kristine(
        filename=filename,
        correlation_time=correlation_time,
        correlation_amplitude=correlation_amplitude,
        correlation_amplitude_uncertainty=uncertainty,
        acquisition_time=10.0,
        mean_countrate=50.0,
        verbose=False,
    )

    ds = read_kristine(filename)[0]
    w = np.asarray(ds["correlation_amplitude_weights"])
    assert np.all(np.isfinite(w))
    # The measured uncertainties are kept; only the zeros are filled in.
    kept = np.ones(N_POINTS, dtype=bool)
    kept[[5, 11, 17]] = False
    assert np.allclose(w[kept], 1.0 / uncertainty[kept])
    assert np.all(w[~kept] > 0.0)


def test_a_mask_without_uncertainties_is_refused(tmp_path, curve):
    """The format has no slot for a mask on its own — say so."""
    correlation_time, correlation_amplitude, _, mask = curve
    filename = str(tmp_path / "mask_only.cor")

    with pytest.raises(ValueError, match="fifth column"):
        write_kristine(
            filename=filename,
            correlation_time=correlation_time,
            correlation_amplitude=correlation_amplitude,
            mask=mask,
            acquisition_time=10.0,
            mean_countrate=50.0,
            verbose=False,
        )
