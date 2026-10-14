"""The FCS YAML reader reads what the YAML writer wrote.

``read_yaml`` was an empty stub returning ``None`` while ``read_fcs`` offered it
as the ``"yaml"`` reader, so such a file could be written but not read back.
"""

from __future__ import annotations

import numpy as np
import pytest


def _dataset(i: int) -> dict:
    t = np.logspace(-3, 2, 16)
    return {
        "filename": "curves.yaml",
        "measurement_id": f"curve_{i}",
        "correlation_times": t,
        "correlation_amplitudes": 1.0 + 0.5 * np.exp(-t / (1.0 + i)),
        "correlation_amplitude_weights": np.ones_like(t),
    }


def test_write_then_read_gives_the_same_curves(tmp_path):
    from chisurf.core.fio.fluorescence.fcs.fcs_yaml import read_yaml, write_yaml

    path = str(tmp_path / "curves.yaml")
    written = [_dataset(0), _dataset(1)]
    write_yaml(path, written)
    read = read_yaml(path)
    assert [d["measurement_id"] for d in read] == ["curve_0", "curve_1"]
    for a, b in zip(written, read):
        np.testing.assert_allclose(b["correlation_times"], a["correlation_times"])
        np.testing.assert_allclose(b["correlation_amplitudes"], a["correlation_amplitudes"])


def test_a_dataset_without_its_curve_is_refused(tmp_path):
    from chisurf.core.fio.fluorescence.fcs.fcs_yaml import read_yaml

    path = tmp_path / "broken.yaml"
    path.write_text("- measurement_id: x\n")
    with pytest.raises(ValueError, match="correlation_amplitudes"):
        read_yaml(str(path))
