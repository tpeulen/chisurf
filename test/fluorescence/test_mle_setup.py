"""Tests for the shared detector-setup parser.

See :mod:`chisurf.core.fluorescence.mle.setup`. This is the one place that turns
a detector-definition payload into fit inputs, so the polarisation split and the
correction handling are pinned here rather than in any single consumer.

(Split out of ``test_mle_fit2x.py``: that suite covers the deprecated fit2x
harness, whereas the parser is shared by every MLE consumer.)
"""
import utils
import pathlib

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import pytest

from chisurf.core.fluorescence.mle import parse_detector_setup


def test_channels_range_and_polarisation_corrections_are_extracted():
    payload = {
        "detectors": {
            "green": {
                "chs": [0, 1],
                "mtr": [(10, 4000)],
                "g_factor": 1.15,
                "l1": 0.02,
                "l2": 0.04,
            }
        }
    }
    setup = parse_detector_setup(payload)
    assert setup.channels == [0, 1]
    assert setup.micro_range == (10, 4000)
    assert setup.g_factor == pytest.approx(1.15)
    assert setup.l1 == pytest.approx(0.02)
    assert setup.l2 == pytest.approx(0.04)


def test_corrections_absent_stay_none():
    """None, not 0.0 — so a caller keeps its own default rather than a forced one."""
    bare = parse_detector_setup({"detectors": {"g": {"chs": [0, 2]}}})
    assert bare.g_factor is None and bare.l1 is None and bare.l2 is None


def test_parse_detector_setup_tolerates_empty_input():
    assert parse_detector_setup(None).channels == []
    assert parse_detector_setup({}).channels == []
    assert parse_detector_setup({"detectors": {}}).channels == []


class TestPolarisationSplit:
    """The channel list alternates VV, VH, VV, ... — the split is POSITIONAL.

    It is not the parity of the channel number. The two agree only when the
    channels happen to run consecutively from an even start, which is why the
    parity implementation survived as long as it did.
    """

    def test_alternates_by_position(self):
        setup = parse_detector_setup({"detectors": {"g": {"chs": [0, 1]}}})
        assert setup.channels_parallel == [0]
        assert setup.channels_perpendicular == [1]

    def test_even_channel_numbers_still_alternate(self):
        # Both channel numbers are even; under the old parity rule both landed in
        # parallel and the perpendicular list came back empty.
        setup = parse_detector_setup({"detectors": {"g": {"chs": [0, 2]}}})
        assert setup.channels_parallel == [0]
        assert setup.channels_perpendicular == [2]

    def test_non_consecutive_channels(self):
        # chs = [8, 0, 3] is VV=8, VH=0, VV=3. Parity would say [8, 0] / [3].
        setup = parse_detector_setup({"detectors": {"g": {"chs": [8, 0, 3]}}})
        assert setup.channels_parallel == [8, 3]
        assert setup.channels_perpendicular == [0]

    def test_explicit_ch_p_ch_s_wins(self):
        setup = parse_detector_setup(
            {"detectors": {"g": {"chs": [8, 0, 3], "ch_p": [8], "ch_s": [0, 3]}}}
        )
        assert setup.channels_parallel == [8]
        assert setup.channels_perpendicular == [0, 3]

    def test_each_detector_alternates_independently(self):
        # The interleaving is a property of one detector's cable order, so it
        # restarts per detector rather than continuing across the merged list.
        setup = parse_detector_setup(
            {
                "detectors": {
                    "green": {"chs": [8, 0]},
                    "red": {"chs": [9, 1]},
                }
            }
        )
        assert setup.channels == [8, 0, 9, 1]
        assert setup.channels_parallel == [8, 9]
        assert setup.channels_perpendicular == [0, 1]

    def test_matches_the_imaging_convention(self):
        """Agree with pixel_maps.detector_ps_channels, the other split in chisurf."""
        from chisurf.core.fluorescence.imaging.pixel_maps import detector_ps_channels

        det = {"chs": [8, 0, 3]}
        expected_p, expected_s = detector_ps_channels(det)
        setup = parse_detector_setup({"detectors": {"g": det}})
        assert list(setup.channels_parallel) == list(expected_p)
        assert list(setup.channels_perpendicular) == list(expected_s)

class TestPolarizationResolvedFlag:
    """``polarization_resolved`` decides whether there is a VV/VH split at all."""

    def test_defaults_to_resolved_when_absent(self):
        setup = parse_detector_setup({"detectors": {"g": {"chs": [0, 1]}}})
        assert setup.polarization_resolved is True
        assert setup.channels_perpendicular == [1]

    def test_false_keeps_one_unpolarised_stream(self):
        payload = {
            "polarization_resolved": False,
            "detectors": {"g": {"chs": [0, 1, 2, 3]}},
        }
        setup = parse_detector_setup(payload)
        assert setup.polarization_resolved is False
        assert setup.channels_parallel == [0, 1, 2, 3]
        assert setup.channels_perpendicular == []

    def test_false_also_overrides_explicit_ch_p_ch_s(self):
        # The setup says it is not polarisation-resolved, so a leftover per
        # detector assignment must not resurrect a split.
        payload = {
            "polarization_resolved": False,
            "detectors": {"g": {"chs": [8, 0, 3], "ch_p": [8], "ch_s": [0, 3]}},
        }
        setup = parse_detector_setup(payload)
        assert setup.channels_parallel == [8, 0, 3]
        assert setup.channels_perpendicular == []

    def test_true_is_explicit_too(self):
        payload = {"polarization_resolved": True, "detectors": {"g": {"chs": [0, 2]}}}
        setup = parse_detector_setup(payload)
        assert setup.polarization_resolved is True
        assert setup.channels_parallel == [0]
        assert setup.channels_perpendicular == [2]

    def test_matches_the_wizard_when_not_resolved(self):
        """Same rule as the micro-time histogram wizard: all -> parallel, none -> perp."""
        payload = {
            "polarization_resolved": False,
            "detectors": {"green": {"chs": [8, 0]}, "red": {"chs": [9, 1]}},
        }
        setup = parse_detector_setup(payload)
        assert setup.channels_parallel == setup.channels == [8, 0, 9, 1]
        assert setup.channels_perpendicular == []

