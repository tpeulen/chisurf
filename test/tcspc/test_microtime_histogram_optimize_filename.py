"""Native output names retain the established numbered acquisition suffix rule."""

from pathlib import Path

import pytest

from chisurf.plugins.tttr.microtime_histogram.gui.model import HistogramModel


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("m_000", "m"),
        ("sample_001", "sample"),
        ("data_123_456", "data_123"),
        ("experiment", "experiment"),
        ("test_1", "test_1"),
        ("file_12", "file"),
        ("data_0001", "data"),
        ("m_000_extra", "m_000_extra"),
        ("sample_42", "sample"),
        ("test_99_data", "test_99_data"),
        ("file_10_20", "file_10"),
        ("data_12345", "data_12345"),
    ],
)
def test_output_name_strips_only_the_final_two_to_four_digit_suffix(tmp_path, stem, expected):
    """Assert the generated save path, rather than printing a comparison result."""
    source = tmp_path / f"{stem}.ptu"
    source.write_bytes(b"fixture")
    model = HistogramModel()
    model.add_paths([source])
    assert Path(model.output) == tmp_path / f"{expected}_(0)-(1).dat"
