"""The three-colour PDA read checks its PIE excitation periods against the measurement.

At three colours the reader's two micro-time windows are the excitation periods of the PIE cycle
and :meth:`Pda2cReader.burst_count_table` counts photons in them; at two colours the S1S2
histogram is built from the routing channels alone and the windows are only recorded. The
measurement is the simulated PIE demo of Excitation Windows (32 ps, 3125 channels, pulses at 2 and
52 ns; routing 0 donor, 1 acceptor), read with blue = routing 0 and green = routing 1.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.core.experiments.pda2c import Pda2cReader  # noqa: E402
from chisurf.core.experiments.pda2c.settings import PdaReaderSettings  # noqa: E402
from chisurf.plugins.core.excitation_windows.demo import make_demo  # noqa: E402

WRONG = [[0, 2047], [2048, 4095]]
MATCHING = [[50, 1612], [1613, 3124]]


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return make_demo(tmp_path_factory.mktemp("demo"))


@pytest.fixture(scope="module")
def donor_only(tmp_path_factory):
    from chisurf.plugins.core.excitation_windows import demo as d
    from chisurf.plugins.tttr import demo_lib

    macro, micro, routing = d.photon_stream(n_photons=100_000)
    keep = ~((routing == 1) & (micro.astype(float) * d.RESOLUTION_S * 1e9 > 51.0))
    path = tmp_path_factory.mktemp("donly") / "donor_only.ptu"
    cfg = demo_lib.config(macro_resolution_s=d.MACRO_S, micro_resolution_s=d.RESOLUTION_S,
                          n_micro=d.N_MICRO)
    demo_lib.write_ptu(path, cfg, macro[keep], micro[keep], np.asarray(routing)[keep])
    return path


def _reader(windows, n_colors=3):
    reader = Pda2cReader(channels=[[0], [1], [2]], micro_time_ranges=[list(w) for w in windows],
                         reading_routine="PTU")
    reader.n_colors = n_colors
    reader.channels = [[0], [1], [2]]
    reader.micro_time_ranges = [list(w) for w in windows]
    return reader


def test_periods_of_another_instrument_are_reported(demo):
    message = _reader(WRONG).windows_warning(str(demo))
    assert message and "do not match the data" in message and "1613" in message


def test_matching_periods_say_nothing(demo):
    assert _reader(MATCHING).windows_warning(str(demo)) is None


def test_two_colours_apply_no_window_and_are_not_checked(demo):
    assert _reader(WRONG, n_colors=2).windows_warning(str(demo)) is None


def test_a_donor_only_measurement_gives_the_note(donor_only):
    message = _reader(WRONG).windows_warning(str(donor_only))
    assert message and "One excitation pulse" in message


def test_the_read_carries_the_warning(demo, caplog):
    reader = _reader(WRONG)
    reader.tw_configs = [(5, 1e-3)]
    with caplog.at_level(logging.WARNING):
        group = reader.read(str(demo))
    assert len(group) == 1
    assert "do not match the data" in group[0].meta_data["warnings"][0]
    assert any("do not match the data" in r.getMessage() for r in caplog.records)
    reader = _reader(MATCHING)
    reader.tw_configs = [(5, 1e-3)]
    assert "warnings" not in reader.read(str(demo))[0].meta_data


def test_the_form_offers_the_detected_periods_and_takes_them(demo):
    reader = _reader(WRONG)
    settings = PdaReaderSettings(reader, setups={}, routines=["PTU"])
    reader.n_colors = 3
    reader.micro_time_ranges = [list(w) for w in WRONG]
    assert settings.add_paths([str(demo)]) == 1
    assert settings.windows_check_offer and "do not match" in settings.windows_check_text()
    assert settings.use_detected_windows()
    (blue_lo, blue_hi), (green_lo, green_hi) = reader.micro_time_ranges
    assert blue_lo <= 2e-9 / 32e-12 <= blue_hi < green_lo <= 52e-9 / 32e-12 <= green_hi
    assert reader.windows_warning(str(demo)) is None


def test_the_form_says_nothing_at_two_colours(demo):
    reader = _reader(WRONG, n_colors=2)
    settings = PdaReaderSettings(reader, setups={}, routines=["PTU"])
    settings.add_paths([str(demo)])
    assert settings.windows_check_quiet and not settings.windows_check_offer
