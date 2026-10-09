"""Excitation phase inference preserves every measured phase and the source stream."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.tttr.ptu_alex_creator import core


def phase_stream(windows, *, period=8000, grouped=False, seed=41):
    """Generate independently planted, unequal-width and unequal-power phases."""
    rng = np.random.default_rng(seed)
    phases, channels = [], []
    size = len(windows)
    for i, (lo, hi) in enumerate(windows):
        width = (hi - lo) % period
        count = int(width * (0.5 + i * 0.7))
        phases.append((rng.uniform(0, width, count) + lo) % period)
        probabilities = np.full(size, 0.15 / (size - 1))
        probabilities[i] = 0.85
        rc = rng.choice(size, count, p=probabilities)
        if grouped:
            rc = 2 * rc + rng.integers(0, 2, count)
        channels.append(rc)
    return np.concatenate(phases), np.concatenate(channels)


@pytest.mark.parametrize("size", [2, 3, 4, 5])
@pytest.mark.parametrize("gaps", [False, True])
def test_every_excitation_phase_is_retained(size, gaps):
    """All planted phases survive, including dim phases and unequal duty cycles."""
    edges = np.round(np.linspace(0, 8000, size + 1) ** 1.05 / 8000**0.05 / 40) * 40
    windows = [(edges[i] + (80 if gaps else 0), edges[i + 1]) for i in range(size)]
    phase, rc = phase_stream(windows)
    result = core.auto_excitation_regions(phase, rc, alex_period=8000, guard=0)
    assert len(result["regions"]) == size
    for region, (lo, hi) in zip(result["regions"], windows):
        assert abs(region["start"] - lo) <= 80
        assert abs(region["stop"] - hi) <= 80
    assert np.array_equal(result["phase_hist"], result["detector_hist"].sum(axis=0))
    assert result["phase_hist"].sum() == len(phase)


def test_wrapped_phase_is_one_region_with_two_reachable_ranges():
    """Crossing zero neither loses a region nor creates an inverted selection."""
    windows = [(7200, 1200), (1600, 3200), (3600, 6800)]
    phase, rc = phase_stream(windows)
    result = core.auto_excitation_regions(phase, rc, alex_period=8000)
    assert len(result["regions"]) == 3
    wrapped = [region for region in result["regions"] if region["wraps"]]
    assert len(wrapped) == 1
    assert len(wrapped[0]["ranges"]) == 2
    for lo, hi in wrapped[0]["ranges"]:
        assert 0 <= lo < hi <= 8000
    assert wrapped[0]["start"] > wrapped[0]["stop"]


def test_guard_can_trim_a_wrapped_run_to_one_nonwrapping_range():
    """Trimming across zero cannot cause unrelated phases to enter the candidate mask."""
    phase, rc = phase_stream([(7920, 2000), (2400, 4000), (4400, 7200)])
    result = core.auto_excitation_regions(phase, rc, alex_period=8000, guard=0.06)
    region = next(row for row in result["regions"] if row["start"] < 100)
    assert not region["wraps"]
    np.testing.assert_allclose(region["ranges"], [[44.8, 1875.2]])
    selected = (phase >= 44.8) & (phase < 1875.2)
    assert region["photon_count"] == selected.sum()
    assert all(lo < hi for row in result["regions"] for lo, hi in row["ranges"])


@pytest.mark.parametrize("value", [0, -1, 65537, 8000.5, float("nan"), float("inf"), True])
def test_invalid_fold_period_fails_before_mutating_arrays_or_header(value):
    """The uint16 phase representation requires a finite integer period in1..65536."""
    import tttrlib

    stream = tttrlib.TTTR()
    stream.append_events(
        np.array([7, 13], dtype=np.uint64),
        np.array([2, 3], dtype=np.uint16),
        np.array([0, 1], dtype=np.int8),
        np.zeros(2, dtype=np.int8),
        False,
        0,
    )
    before = stream.micro_times.copy(), stream.macro_times.copy(), stream.header.json
    with pytest.raises(ValueError, match="period"):
        core.apply_alex(stream, value, -23)
    np.testing.assert_array_equal(stream.micro_times, before[0])
    np.testing.assert_array_equal(stream.macro_times, before[1])
    assert stream.header.json == before[2]


def test_maximum_phase_period_and_negative_shift_are_valid():
    """The full65536-bin phase domain and signed shifts remain supported."""
    assert core.validate_alex_period(65536) == 65536
    assert core.validate_alex_period(65536.0) == 65536
    import tttrlib

    stream = tttrlib.TTTR()
    stream.append_events(
        np.array([7, 13], dtype=np.uint64),
        np.array([2, 3], dtype=np.uint16),
        np.array([0, 1], dtype=np.int8),
        np.zeros(2, dtype=np.int8),
        False,
        0,
    )
    core.apply_alex(stream, 65536, -23)
    np.testing.assert_array_equal(stream.micro_times, [30, 36])


@pytest.mark.parametrize("value", [0, 65537, 8000.5, float("nan"), float("inf"), True])
def test_payload_period_is_validated_before_integer_coercion(value):
    """Transport payloads must not silently truncate fractional or invalid periods."""
    from chisurf.plugins.tttr.ptu_alex_creator.api.contract import request_from_payload

    with pytest.raises(ValueError, match="period"):
        request_from_payload({"alex_period": value})


@pytest.mark.parametrize("command", ["convert", "merge"])
@pytest.mark.parametrize("value", ["0", "65537", "8000.5", "nan"])
def test_cli_rejects_unrepresentable_or_noninteger_periods(command, value):
    """CLI validation rejects invalid periods before invoking any converter."""
    from click.testing import CliRunner

    from chisurf.plugins.tttr.ptu_alex_creator.cli.main import cli

    result = CliRunner().invoke(cli, [command, "--period", value])
    assert result.exit_code == 2
    assert "--period" in result.output


def test_polarization_groups_use_every_channel_without_changing_inputs():
    """Physical detector groups sum polarization channels without dropping data."""
    phase, rc = phase_stream([(0, 1600), (1600, 4000), (4000, 8000)], grouped=True)
    original = phase.copy(), rc.copy()
    phase.flags.writeable = rc.flags.writeable = False
    result = core.auto_excitation_regions(
        phase, rc, alex_period=8000, channel_groups=[[0, 1], [2, 3], [4, 5]]
    )
    assert len(result["regions"]) == 3
    assert result["detector_channels"] == [[0, 1], [2, 3], [4, 5]]
    assert result["phase_hist"].sum() == phase.size
    assert np.array_equal(phase, original[0])
    assert np.array_equal(rc, original[1])
    for region in result["regions"]:
        assert sum(region["detector_counts"]) == region["photon_count"]


def test_missing_or_overlapping_channel_groups_are_rejected():
    """An explicit grouping cannot silently discard or double-count a detector."""
    phase, rc = phase_stream([(0, 2400), (2400, 4800), (4800, 8000)])
    for groups in ([[0], [1]], [[0, 1], [1, 2]]):
        with pytest.raises(ValueError, match="channel"):
            core.auto_excitation_regions(phase, rc, alex_period=8000, channel_groups=groups)


def test_non_alternating_noise_has_no_excitation_regions():
    """Counting noise must not be advertised as a laser phase boundary."""
    rng = np.random.default_rng(43)
    with pytest.raises(ValueError, match="alternation|region"):
        core.auto_excitation_regions(
            rng.uniform(0, 8000, 100000), rng.integers(0, 4, 100000), alex_period=8000
        )


def test_intensity_variation_without_composition_changes_is_ambiguous():
    """Brightness alone cannot identify contiguous laser-on phases of one colour."""
    phase, rc = phase_stream([(0, 2400), (2400, 4800), (4800, 8000)])
    rng = np.random.default_rng(47)
    rc = rng.choice(3, rc.size, p=[0.6, 0.3, 0.1])
    with pytest.raises(ValueError, match="alternation"):
        core.auto_excitation_regions(phase, rc, alex_period=8000)


@pytest.mark.parametrize("kwargs", [{"alex_period": 0}, {"guard": 0.5}, {"n_bins": 2}])
def test_invalid_inference_settings_are_rejected(kwargs):
    """Invalid resolution and guard settings fail before producing regions."""
    phase, rc = phase_stream([(200, 3600), (4400, 7600)])
    with pytest.raises(ValueError):
        core.auto_excitation_regions(phase, rc, **({"alex_period": 8000} | kwargs))


def test_single_detector_can_resolve_separated_excitation_regions():
    """Laser-off gaps retain their information even with one detector."""
    phase, rc = phase_stream([(200, 2400), (2800, 4800), (5200, 7600)])
    result = core.auto_excitation_regions(phase, np.zeros_like(rc), alex_period=8000)
    assert len(result["regions"]) == 3


def test_binary_assignment_does_not_silently_drop_extra_detectors():
    """The legacy binary helper clearly rejects a genuinely multicolor stream."""
    phase, rc = phase_stream([(0, 2400), (2400, 4800), (4800, 8000)])
    with pytest.raises(ValueError, match="two|multi"):
        core.detect_alex_channels(phase, rc, alex_period=8000)


def test_detection_leaves_tttr_arrays_and_header_untouched():
    """Inference is read-only, including the TTTR header and physical clocks."""
    import tttrlib

    phase, rc = phase_stream([(0, 2400), (2400, 4800), (4800, 8000)])
    stream = tttrlib.TTTR()
    stream.append_events(
        np.arange(phase.size, dtype=np.uint64),
        phase.astype(np.uint16),
        rc.astype(np.int8),
        np.zeros(phase.size, dtype=np.int8),
        False,
        0,
    )
    stream.header.set_tag("User_RegionDetectionMarker", "read-only", 1073872895)
    before = [
        np.array(getattr(stream, name), copy=True)
        for name in ("macro_times", "micro_times", "routing_channels", "event_types")
    ]
    header = stream.header.json
    core.auto_excitation_regions(stream.micro_times, stream.routing_channels, alex_period=8000)
    assert stream.header.json == header
    for name, array in zip(
        ("macro_times", "micro_times", "routing_channels", "event_types"), before
    ):
        assert np.array_equal(getattr(stream, name), array)


def test_binary_assignment_preserves_two_physical_polarized_detector_groups():
    """Four routing channels still form a valid, explicitly grouped binary input."""
    phase, rc = phase_stream([(200, 3600), (4400, 7600)], grouped=True)
    assignment = core.detect_alex_channels(
        phase, rc, alex_period=8000, channel_groups=[[0, 1], [2, 3]]
    )
    assert sorted(assignment["donor"] + assignment["acceptor"]) == [0, 1, 2, 3]
    windows = core.auto_alex_windows(
        phase,
        rc,
        alex_period=8000,
        donor_channels=assignment["donor"],
        acceptor_channels=assignment["acceptor"],
    )
    assert set(windows) == {"green", "red", "phase_hist", "phase_edges"}
    assert windows["phase_hist"].sum() == phase.size


def test_real_switching_transition_candidates_are_explicit_and_never_discarded():
    """Real, continuously occupied phases require review rather than laser labels."""
    from chisurf.plugins.burst.alex_suite.tests.test_alternation import REAL_FILE

    if not REAL_FILE.is_file():
        pytest.skip("real calibration measurement unavailable")
    folded = core.apply_alex(core.load(str(REAL_FILE), "SM"), 8000, 0)
    result = core.auto_excitation_regions(
        folded.micro_times, folded.routing_channels, alex_period=8000
    )
    assert result["phase_hist"].sum() == len(folded.micro_times)
    assert len(result["regions"]) >= 2
    assert result["warnings"]
    assert any(region["ambiguous"] for region in result["regions"])
    assert all(region["name"].startswith("excitation_") for region in result["regions"])
