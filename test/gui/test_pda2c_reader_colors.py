"""One PDA reader, two colour counts (PRD-65).

Three-colour PDA reads the same TTTR files as two-colour PDA and finds bursts
the same way; only the payload differs — an S1S2 histogram for two colours, a
per-burst photon table for three. These tests pin that shared path against real
TTTR data rather than a synthetic stand-in, because the things that go wrong
here (index conventions, micro-time gating, channel selection) are exactly the
things a synthetic file would be built to satisfy.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

TTTR_FILE = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
ROUTINE = "SPC-130"

pytestmark = pytest.mark.skipif(
    not TTTR_FILE.is_file(), reason=f"{TTTR_FILE} not available"
)


@pytest.fixture(scope="module")
def photons():
    import tttrlib

    return tttrlib.TTTR(str(TTTR_FILE), ROUTINE)


def _reader(**kwargs):
    from chisurf.core.experiments.pda2c import Pda2cReader

    settings = dict(
        channels=([0], [1]),
        micro_time_ranges=[(0, 4096)],
        reading_routine=ROUTINE,
        minimum_number_of_photons=20,
        minimum_time_window_length=2e-3,
        maximum_number_of_photons=200,
    )
    settings.update(kwargs)
    return Pda2cReader(**settings)


# ── the colour selector ────────────────────────────────────────────────────


def test_colour_count_defaults_to_the_detection_setup():
    """A three-colour setup should not have to be told it is three-colour."""
    assert _reader(channels=([0], [1])).n_colors == 2
    assert _reader(channels=([0], [1], [2])).n_colors == 3
    # An explicit setting still wins.
    assert _reader(channels=([0], [1], [2]), n_colors=2).n_colors == 2


def test_detection_windows_describe_the_physical_combinations():
    two = _reader().detection_windows()
    assert len(two) == 2

    three = _reader(
        channels=([0], [1], [2]), micro_time_ranges=[(0, 2048), (2048, 4096)]
    ).detection_windows()
    assert len(three) == 5
    # Blue excitation is visible in all three detectors...
    assert [w[1] for w in three[:3]] == [(0, 2048)] * 3
    assert [w[0] for w in three[:3]] == [[0], [1], [2]]
    # ... green excitation only in green and red: nothing emits blue after it.
    assert [w[1] for w in three[3:]] == [(2048, 4096)] * 2
    assert [w[0] for w in three[3:]] == [[1], [2]]


# ── burst counting on real photons ─────────────────────────────────────────


def test_counts_are_consistent_with_the_photon_stream(photons):
    """Every burst's counts must equal the photons its window actually holds."""
    reader = _reader(channels=([0, 8], [1, 9]))
    table = reader.burst_count_table(photons, 20, 2e-3)
    assert table.shape[0] > 100 and table.shape[1] == 2

    ranges = np.asarray(
        photons.get_ranges_by_time_window(2e-3, -1, 20, -1), dtype=np.int64
    ).reshape(-1, 2)
    routing = np.asarray(photons.routing_channels)

    # Spot-check a handful of bursts against a direct count.
    for row in (0, 5, 50, table.shape[0] - 1):
        start, stop = ranges[row]
        window = routing[start: stop + 1]  # inclusive, see burst_count_table
        assert table[row, 0] == np.isin(window, [0, 8]).sum()
        assert table[row, 1] == np.isin(window, [1, 9]).sum()


def test_the_stop_index_is_inclusive(photons):
    """Off-by-one guard, decided by measurement rather than by convention.

    A window is only ever at least ``minimum_time_window_length`` long when its
    stop photon is counted; with an exclusive stop *not one* of them reaches the
    requested duration. Getting this backwards loses the last photon of every
    burst — a small, uniform, easily-missed bias.
    """
    macro = np.asarray(photons.macro_times)
    resolution = photons.get_header().macro_time_resolution
    ranges = np.asarray(
        photons.get_ranges_by_time_window(2e-3, -1, 20, -1), dtype=np.int64
    ).reshape(-1, 2)

    inclusive = (macro[ranges[:, 1]] - macro[ranges[:, 0]]) * resolution
    exclusive = (macro[ranges[:, 1] - 1] - macro[ranges[:, 0]]) * resolution
    assert np.all(inclusive >= 2e-3 - 1e-12)
    assert not np.any(exclusive >= 2e-3)


def test_micro_time_gating_splits_the_excitation_periods(photons):
    """The two PIE halves must partition the photons, not overlap or drop any."""
    reader = _reader(
        channels=([0], [1], [8]),
        micro_time_ranges=[(0, 2047), (2048, 4095)],
        n_colors=3,
    )
    table = reader.burst_count_table(photons, 20, 2e-3)
    assert table.shape[1] == 5

    full = _reader(channels=([0], [1], [8]), micro_time_ranges=[(0, 4095)],
                   n_colors=3).burst_count_table(photons, 20, 2e-3)
    # Green detector: blue-period + green-period counts must equal the ungated
    # total for that detector.
    assert np.allclose(table[:, 1] + table[:, 3], full[:, 1])
    # Red detector likewise.
    assert np.allclose(table[:, 2] + table[:, 4], full[:, 2])


# ── the three-colour dataset ───────────────────────────────────────────────


def test_reading_a_file_as_three_colour_yields_a_fittable_dataset():
    """End of the shared path: a real file becomes a PDA3c dataset."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.pda3c.pda3c import Pda3cModel

    reader = _reader(
        channels=([0], [1], [8]),
        micro_time_ranges=[(0, 2047), (2048, 4095)],
        n_colors=3,
    )
    group = reader.read(str(TTTR_FILE))
    assert len(group) == 1

    curve = group[0]
    payload = curve.meta_data["pda3c"]
    assert payload["blue"].shape[1] == 3
    assert payload["green"].shape[1] == 2
    assert payload["n_bursts"] > 100
    assert payload["columns"] == ["F_BB", "F_BG", "F_BR", "F_GG", "F_GR"]

    fit = fit_mod.Fit(model_class=Pda3cModel, data=curve)
    fit.model.update()
    assert np.all(np.isfinite(fit.model.y))
    wres = np.asarray(fit.model.get_wres(fit))
    assert wres.size > 0 and np.all(np.isfinite(wres))


def test_two_colour_reading_still_produces_an_s1s2_dataset():
    """The existing path must be untouched by the colour branch."""
    reader = _reader(channels=([0, 8], [1, 9]))
    group = reader.read(str(TTTR_FILE))
    assert len(group) == 1
    curve = group[0]
    assert "pda" not in curve.meta_data  # two-colour payload rides on .pda
    assert curve.pda["s1s2"] is not None
    assert curve.pda["ndim"] == 2
