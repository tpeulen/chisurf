"""ALEX export refuses phase loss before creating a file."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.tttr.ptu_alex_creator import core


class Stream:
    """Record the write boundary without involving a binary encoder."""

    def __init__(self, container, record, phase):
        self.header = SimpleNamespace(tttr_container_type=container, tttr_record_type=record)
        self.micro_times = np.array(phase, dtype=np.uint16)
        self.writes = []

    def write(self, *args):
        self.writes.append(args)
        return True


@pytest.mark.parametrize(
    "record,limit",
    [
        (3, 32767),
        (4, 32767),
        (5, 4095),
        (7, 4095),
        (8, 255),
        (9, 4095),
        (12, 32767),
        (14, 32767),
        (15, 4095),
        (16, 4095),
    ],
)
def test_record_width_rejects_overflow_before_any_write(tmp_path, record, limit):
    """The actual record width governs export, including unchanged containers."""
    stream = Stream(0, record, [0, limit + 1])
    output = tmp_path / "new" / "invalid.ptu"
    with pytest.raises(ValueError, match="microtime|phase"):
        core._write(stream, str(output), "Auto", "Auto")
    assert not stream.writes
    assert not output.parent.exists()


@pytest.mark.parametrize("record", [1, 2, 6, 10, 11, 13])
def test_no_microtime_records_reject_nonzero_phase(tmp_path, record):
    """T2, SM and CZ exports cannot represent nonzero excitation phases."""
    stream = Stream(0, record, [0, 1])
    with pytest.raises(ValueError, match="microtime|phase"):
        core._write(stream, str(tmp_path / "invalid"), "Auto", "Auto")
    assert not stream.writes


@pytest.mark.parametrize(
    "container,record,phase",
    [
        (0, 4, [0, 32767]),
        (0, 5, [0, 4095]),
        (3, 8, [0, 255]),
        (5, 4, [0, 65535]),
        (7, 11, [0]),
        (0, 4, []),
    ],
)
def test_representable_phase_reaches_writer(tmp_path, container, record, phase):
    """Supported endpoints and full-width HDF5 remain available."""
    stream = Stream(container, record, phase)
    core._write(stream, str(tmp_path / "valid"), "Auto", "Auto")
    assert len(stream.writes) == 1


def test_failed_writer_is_not_reported_as_success(tmp_path):
    """A native False result must propagate rather than return an output path."""
    stream = Stream(0, 4, [2])
    stream.write = lambda *args: False
    with pytest.raises(OSError, match="write"):
        core._write(stream, str(tmp_path / "failed"), "Auto", "Auto")


def test_unknown_output_does_not_silently_become_ptu(tmp_path):
    """An unsupported target cannot silently write a different format."""
    stream = Stream(0, 4, [2])
    with pytest.raises(ValueError, match="Unsupported ALEX output format"):
        core._write(stream, str(tmp_path / "invalid"), "unknown", "PTU")
    assert not stream.writes


def test_transcoding_header_does_not_mutate_loaded_measurement():
    """Output metadata changes belong to a copied header, not the source."""
    sample = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    source = tttrlib.TTTR(str(sample))[:1]
    before = source.header.json
    output = core._prepare_output_header(source, "SPC-130", "PTU")
    assert output.tttr_container_type == 2
    assert output.tttr_record_type == 7
    assert source.header.json == before


@pytest.mark.parametrize("mode", ["single", "merge"])
def test_real_conversion_refuses_unrepresentable_phases(tmp_path, mode):
    """Both public workflows reject a full-width phase that T3 would truncate."""
    sample = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    source = tttrlib.TTTR(str(sample))[:0]
    source.append_events(
        np.array([10, 40000], dtype=np.uint64),
        np.zeros(2, dtype=np.uint16),
        np.zeros(2, dtype=np.int8),
        np.zeros(2, dtype=np.int8),
        False,
        0,
    )
    path = tmp_path / "source.ptu"
    assert source.write(str(path))
    before = path.read_bytes()
    output = tmp_path / "new" / "invalid.ptu"
    with pytest.raises(ValueError, match="microtime phase"):
        if mode == "single":
            core.convert_file(str(path), str(output), 65536, 0)
        else:
            core.merge_files([str(path)], str(output), 65536, 0)
    assert not output.parent.exists()
    assert path.read_bytes() == before


def test_real_three_detector_conversion_matches_integer_reference(tmp_path):
    """Negative intermediate phases round-trip with all detector identities."""
    sample = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    source = tttrlib.TTTR(str(sample))[:0]
    macro = np.array([1, 23, 8001, 11000, 22000], dtype=np.uint64)
    routing = np.array([0, 1, 2, 0, 2], dtype=np.int8)
    source.append_events(
        macro, np.zeros(5, dtype=np.uint16), routing, np.zeros(5, dtype=np.int8), False, 0
    )
    path, output = tmp_path / "source.ptu", tmp_path / "converted.ptu"
    assert source.write(str(path))
    before = path.read_bytes()
    core.convert_file(str(path), str(output), 8000, 23)
    actual = tttrlib.TTTR(str(output))
    np.testing.assert_array_equal(actual.micro_times, [(int(t) - 23) % 8000 for t in macro])
    np.testing.assert_array_equal(actual.macro_times, macro)
    np.testing.assert_array_equal(actual.routing_channels, routing)
    np.testing.assert_array_equal(actual.event_types, np.zeros(5, dtype=np.int8))
    assert path.read_bytes() == before
